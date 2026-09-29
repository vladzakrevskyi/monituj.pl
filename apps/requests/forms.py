from datetime import datetime, time, timedelta
from itertools import zip_longest

from django import forms
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.utils import timezone as django_timezone

from apps.accounts.sender import suggested_name, validate_sender_name
from apps.clients.models import Client
from apps.requests.models import (
    DEFAULT_RETENTION_DAYS,
    LAST_DAY_OF_MONTH,
    MAX_RETENTION_DAYS,
    RecurringInterval,
)

REQUIRED_MESSAGE = "To pole jest wymagane."


NO_ITEMS_MESSAGE = "Dodaj co najmniej jeden dokument do listy."
# New clients typed in at once on the "many clients" form.
MAX_NEW_CLIENTS = 100

RETENTION_PRESETS = [30, 90, 180, 365]
RETENTION_CUSTOM = "custom"
RETENTION_CHOICES = [
    ("30", "30 dni"),
    ("90", "90 dni (domyślnie)"),
    ("180", "180 dni"),
    ("365", "1 rok (365 dni)"),
    (RETENTION_CUSTOM, "Własny okres"),
]


# Reminder rhythms to pick from: (first after days, every days, how many).
REMINDER_PRESETS = {
    "gentle": (3, 5, 2),
    "standard": (2, 3, 3),
    "frequent": (1, 2, 5),
}
REMINDER_PRESET_CHOICES = [
    ("gentle", "Łagodne"),
    ("standard", "Standardowe"),
    ("frequent", "Częste"),
    ("custom", "Własne"),
    ("off", "Bez przypomnień"),
]


def reminder_preset_of(enabled, first, every, count):
    """The preset these settings match - "custom" when none does."""
    if not enabled:
        return "off"
    for key, values in REMINDER_PRESETS.items():
        if values == (first, every, count):
            return key
    return "custom"


def _deadline_to_end_of_day(value):
    if value is None:
        return None
    return django_timezone.make_aware(datetime.combine(value, time.max))


class _RequestDetailsFieldsMixin(forms.Form):
    name = forms.CharField(
        label="Nazwa",
        max_length=255,
        error_messages={"required": REQUIRED_MESSAGE},
    )
    description = forms.CharField(label="Opis", required=False, widget=forms.Textarea)
    deadline = forms.DateField(
        label="Termin",
        required=False,
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
        input_formats=["%Y-%m-%d"],
    )

    reminder_preset = forms.ChoiceField(
        label="Przypomnienia",
        choices=REMINDER_PRESET_CHOICES,
        initial="standard",
        required=False,
    )
    reminders_enabled = forms.BooleanField(
        label="Włącz automatyczne przypomnienia", required=False, initial=True
    )
    first_reminder_after_days = forms.IntegerField(
        label="Pierwsze przypomnienie po (dni)", required=False, min_value=1, initial=2
    )
    reminder_frequency_days = forms.IntegerField(
        label="Częstotliwość przypomnień (dni)", required=False, min_value=1, initial=3
    )
    max_reminders = forms.IntegerField(
        label="Maksymalna liczba przypomnień", required=False, min_value=1, initial=3
    )

    retention_choice = forms.ChoiceField(
        label="Przechowuj przesłane pliki przez",
        choices=RETENTION_CHOICES,
        initial=str(DEFAULT_RETENTION_DAYS),
        required=False,
    )
    retention_custom_days = forms.IntegerField(
        label="Liczba dni (1-365)",
        required=False,
        min_value=1,
        max_value=MAX_RETENTION_DAYS,
        error_messages={
            "min_value": "Podaj co najmniej 1 dzień.",
            "max_value": "Pliki można przechowywać maksymalnie 365 dni.",
            "invalid": "Podaj liczbę dni.",
        },
    )

    def clean_name(self):
        # The name goes into email subjects, where a line break would stop
        # the email from being sent at all.
        return " ".join(self.cleaned_data["name"].split())

    def clean_deadline(self):
        return _deadline_to_end_of_day(self.cleaned_data.get("deadline"))

    def clean(self):
        cleaned_data = super().clean()
        choice = cleaned_data.get("retention_choice") or str(DEFAULT_RETENTION_DAYS)
        if choice == RETENTION_CUSTOM:
            if cleaned_data.get("retention_custom_days") is None and (
                "retention_custom_days" not in self.errors
            ):
                self.add_error("retention_custom_days", "Podaj liczbę dni.")
        return cleaned_data

    def retention_days(self):
        choice = self.cleaned_data.get("retention_choice") or str(
            DEFAULT_RETENTION_DAYS
        )
        if choice == RETENTION_CUSTOM:
            return self.cleaned_data["retention_custom_days"]
        return int(choice)

    def request_settings(self):
        return {**self.reminder_settings(), "retention_days": self.retention_days()}

    @staticmethod
    def retention_initial(days):
        if days in RETENTION_PRESETS:
            return {"retention_choice": str(days)}
        return {"retention_choice": RETENTION_CUSTOM, "retention_custom_days": days}

    def reminder_settings(self):
        preset = self.cleaned_data.get("reminder_preset")
        if preset == "off":
            return {
                "reminders_enabled": False,
                **self._numbers(*REMINDER_PRESETS["standard"]),
            }
        if preset in REMINDER_PRESETS:
            return {
                "reminders_enabled": True,
                **self._numbers(*REMINDER_PRESETS[preset]),
            }
        if preset == "custom":
            return {
                **self._custom_reminders(),
                "reminders_enabled": True,
            }
        return self._custom_reminders()

    @staticmethod
    def _numbers(first, every, count):
        return {
            "first_reminder_after_days": first,
            "reminder_frequency_days": every,
            "max_reminders": count,
        }

    def _custom_reminders(self):
        return {
            "reminders_enabled": self.cleaned_data.get("reminders_enabled", False),
            "first_reminder_after_days": self.cleaned_data.get(
                "first_reminder_after_days"
            )
            or 2,
            "reminder_frequency_days": self.cleaned_data.get("reminder_frequency_days")
            or 3,
            "max_reminders": self.cleaned_data.get("max_reminders") or 3,
        }


class _ItemsFieldMixin(forms.Form):
    """The document list is posted as repeated "items" values by the item
    builder widget. The field exists so errors about the list can be keyed to
    it (and shown next to the builder); views read the values via getlist()."""

    items = forms.CharField(required=False)

    def item_names(self):
        if not self.is_bound:
            return []
        names = [n.strip() for n in self.data.getlist("items") if n.strip()]
        if not names:
            self.add_error("items", NO_ITEMS_MESSAGE)
        return names


DEADLINE_MONTH_DAY = "day10"
DEADLINE_DAY = 10
DEADLINE_CHOICES = [
    ("7", "7 dni"),
    ("14", "14 dni"),
    (DEADLINE_MONTH_DAY, f"Do {DEADLINE_DAY}. dnia miesiąca"),
    ("date", "Wybierz datę"),
    ("days", "Inna liczba dni"),
    ("none", "Bez terminu"),
]


def next_month_day(after, day):
    """The next `day` of a month after `after` - this month's if still ahead."""
    candidate = after.replace(day=day)
    if candidate <= after:
        candidate = (after.replace(day=1) + timedelta(days=32)).replace(day=day)
    return candidate


WEEKDAY_CHOICES = [
    (0, "poniedziałek"),
    (1, "wtorek"),
    (2, "środa"),
    (3, "czwartek"),
    (4, "piątek"),
    (5, "sobota"),
    (6, "niedziela"),
]
MONTH_DAY_CHOICES = [(day, f"{day}.") for day in range(1, 29)] + [
    (LAST_DAY_OF_MONTH, "ostatni dzień miesiąca")
]


class _TimingFieldsMixin(forms.Form):
    """When a recurring request goes out (apps/requests/recurring.py)."""

    interval = forms.ChoiceField(
        label="Jak często",
        choices=RecurringInterval.choices,
        initial=RecurringInterval.MONTHLY,
        required=False,
    )
    month_day = forms.TypedChoiceField(
        label="Dzień miesiąca",
        choices=MONTH_DAY_CHOICES,
        coerce=int,
        initial=1,
        required=False,
    )
    weekday = forms.TypedChoiceField(
        label="Dzień tygodnia",
        choices=WEEKDAY_CHOICES,
        coerce=int,
        initial=0,
        required=False,
    )
    workdays_only = forms.BooleanField(
        label="Tylko dni robocze", required=False, initial=True
    )
    deadline_days = forms.IntegerField(
        label="Termin: dni po wysłaniu",
        required=False,
        min_value=1,
        max_value=90,
        initial=10,
    )

    def clean_timing(self, cleaned_data):
        interval = cleaned_data.get("interval") or RecurringInterval.MONTHLY
        cleaned_data["interval"] = interval
        if interval == RecurringInterval.MONTHLY and not cleaned_data.get("month_day"):
            self.add_error("month_day", "Wybierz dzień miesiąca.")
        if interval in (RecurringInterval.WEEKLY, RecurringInterval.BIWEEKLY) and (
            cleaned_data.get("weekday") in (None, "")
        ):
            self.add_error("weekday", "Wybierz dzień tygodnia.")

    def timing(self):
        data = self.cleaned_data
        interval = data["interval"]
        return {
            "interval": interval,
            "month_day": data.get("month_day")
            if interval == RecurringInterval.MONTHLY
            else None,
            "weekday": data.get("weekday")
            if interval in (RecurringInterval.WEEKLY, RecurringInterval.BIWEEKLY)
            else None,
            "workdays_only": bool(data.get("workdays_only")),
        }


class RequestForm(
    _TimingFieldsMixin, _ItemsFieldMixin, _RequestDetailsFieldsMixin, forms.Form
):
    client = forms.ModelChoiceField(
        label="Istniejący klient",
        queryset=Client.objects.none(),
        required=False,
        empty_label="-- wybierz klienta --",
        error_messages={"invalid_choice": "Nieprawidłowy klient."},
    )
    send_first_now = forms.BooleanField(
        label="Wyślij pierwszą już teraz", required=False, initial=True
    )
    deadline_choice = forms.ChoiceField(
        label="Termin",
        choices=DEADLINE_CHOICES,
        required=False,
    )
    # Several clients at once: the same request to each of them.
    clients = forms.ModelMultipleChoiceField(
        label="Klienci",
        queryset=Client.objects.none(),
        required=False,
        error_messages={"invalid_choice": "Nieprawidłowy klient."},
    )
    # New clients typed in on the "many clients" form: repeated
    # new_clients_name / new_clients_email values, read by new_clients();
    # the field exists so errors about them have a place.
    new_clients = forms.CharField(required=False)
    new_client_name = forms.CharField(
        label="Nazwa nowego klienta", required=False, max_length=255
    )
    new_client_email = forms.EmailField(
        label="Email nowego klienta",
        required=False,
        error_messages={"invalid": "Nieprawidłowy adres email."},
    )
    password = forms.CharField(
        label="Hasło (opcjonalnie)",
        required=False,
        widget=forms.PasswordInput,
        help_text="Zostaw puste, aby nie zabezpieczać linku hasłem.",
    )

    sender_name = forms.CharField(
        label="Jak przedstawić Cię klientowi?",
        max_length=255,
        required=False,
        help_text=(
            "Twoje imię i nazwisko albo nazwa firmy – odbiorca zobaczy ją razem "
            "z Twoim adresem email. Zmienisz ją w Ustawieniach."
        ),
    )

    def __init__(self, *args, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        # Asked for once: until the account has a name to show recipients.
        self.asks_name = owner is not None and not owner.display_name
        if not self.asks_name:
            del self.fields["sender_name"]
        else:
            self.fields["sender_name"].required = True
            self.fields["sender_name"].error_messages["required"] = (
                "Podaj, jak przedstawić Cię klientowi."
            )
            self.fields["sender_name"].initial = suggested_name(owner)
        if owner is not None:
            own = Client.objects.filter(owner=owner).order_by("name")
            self.fields["client"].queryset = own
            self.fields["clients"].queryset = own

    def clean_sender_name(self):
        name = " ".join(self.cleaned_data["sender_name"].split())
        validate_sender_name(name)
        return name

    def save_sender_name(self, user):
        """The name recipients will see, asked for with the first request."""
        if self.asks_name and self.cleaned_data.get("sender_name"):
            user.display_name = self.cleaned_data["sender_name"]
            user.save(update_fields=["display_name"])

    @property
    def is_recurring(self):
        """Sent again and again ("Cyklicznie"), not once."""
        return self.data.get("schedule") == "recurring"

    @property
    def to_many(self):
        """More than one client: each gets its own request (create_many)."""
        if hasattr(self, "cleaned_data") and "recipient_count" in self.cleaned_data:
            return self.cleaned_data["recipient_count"] > 1
        return self.data.get("recipients") == "many"

    def _values(self, name):
        """Repeated values of a field (a plain dict in tests has no getlist)."""
        if hasattr(self.data, "getlist"):
            return self.data.getlist(name)
        value = self.data.get(name) or []
        return value if isinstance(value, list) else [value]

    def _new_clients(self):
        """[(name, email)] from the rows typed in - empty rows skipped, the
        same address once. Adds an error for a row that can't be used."""
        names = self._values("new_clients_name")
        emails = self._values("new_clients_email")
        found, seen, problems = [], set(), []
        for name, email in zip_longest(names, emails, fillvalue=""):
            name, email = " ".join(name.split())[:255], email.strip()
            if not name and not email:
                continue
            if not email:
                problems.append(f"Podaj adres email klienta „{name}”.")
                continue
            try:
                validate_email(email)
            except ValidationError:
                problems.append(f"Nieprawidłowy adres email: {email}")
                continue
            if email.lower() not in seen:
                seen.add(email.lower())
                found.append((name, email))
        if len(found) > MAX_NEW_CLIENTS:
            problems.append(f"Naraz dodasz najwyżej {MAX_NEW_CLIENTS} nowych klientów.")
        for problem in problems:
            self.add_error("new_clients", problem)
        return found

    def _recipients(self, cleaned_data):
        """The clients picked and the new ones typed in - one field for one
        client or many (the old single-client fields are read too)."""
        picked = list(cleaned_data.get("clients") or [])
        if cleaned_data.get("client") and cleaned_data["client"] not in picked:
            picked.append(cleaned_data["client"])
        new = self._new_clients()
        if cleaned_data.get("new_client_email"):
            email = cleaned_data["new_client_email"]
            if email.lower() not in {e.lower() for _, e in new}:
                new.append((cleaned_data.get("new_client_name", ""), email))
        known = {c.email.lower() for c in picked}
        new = [(n, e) for n, e in new if e.lower() not in known]
        cleaned_data["client_ids"] = [c.pk for c in picked]
        cleaned_data["new_clients_list"] = new
        cleaned_data["recipient_count"] = len(picked) + len(new)
        if not cleaned_data["recipient_count"] and not {
            "clients",
            "client",
            "new_clients",
            "new_client_email",
        } & set(self.errors):
            self.add_error("clients", "Wybierz klienta albo wpisz adres e-mail nowego.")

    def _deadline_choice(self, cleaned_data):
        """The deadline picked with a button: a date for a one-off request,
        days (or a day of the month) after each sending for a recurring one."""
        choice = cleaned_data.get("deadline_choice")
        today = django_timezone.localdate()
        cleaned_data["deadline_month_day"] = None
        if self.is_recurring:
            cleaned_data["deadline"] = None
            if choice in ("7", "14"):
                cleaned_data["deadline_days"] = int(choice)
            elif choice == DEADLINE_MONTH_DAY:
                cleaned_data["deadline_days"] = None
                cleaned_data["deadline_month_day"] = DEADLINE_DAY
            elif choice == "none":
                cleaned_data["deadline_days"] = None
            elif choice == "days" and not cleaned_data.get("deadline_days"):
                self.add_error("deadline_days", "Podaj liczbę dni.")
            return
        if choice in ("7", "14"):
            cleaned_data["deadline"] = _deadline_to_end_of_day(
                today + timedelta(days=int(choice))
            )
        elif choice == DEADLINE_MONTH_DAY:
            cleaned_data["deadline"] = _deadline_to_end_of_day(
                next_month_day(today, DEADLINE_DAY)
            )
        elif choice == "none":
            cleaned_data["deadline"] = None
        elif choice == "date" and not cleaned_data.get("deadline"):
            self.add_error("deadline", "Wybierz datę.")

    def clean(self):
        cleaned_data = super().clean()
        self._recipients(cleaned_data)
        self._deadline_choice(cleaned_data)
        if self.is_recurring:
            self.clean_timing(cleaned_data)
            if cleaned_data.get("password"):
                self.add_error(
                    "password",
                    "Prośba cykliczna nie może mieć hasła – przy każdej wysyłce "
                    "trzeba by je przekazywać od nowa.",
                )
        elif self.to_many and cleaned_data.get("password"):
            self.add_error(
                "password",
                "Hasło ustawisz tylko w prośbie do jednego klienta – jedno "
                "hasło znane wielu osobom niczego nie chroni.",
            )
        return cleaned_data


class RecurringRequestForm(
    _TimingFieldsMixin, _ItemsFieldMixin, _RequestDetailsFieldsMixin, forms.Form
):
    """Editing a recurring request: what goes out, to whom and when. The
    changes apply from the next run; requests already sent stay as they are."""

    clients = forms.ModelMultipleChoiceField(
        label="Klienci",
        queryset=Client.objects.none(),
        error_messages={
            "required": "Zaznacz co najmniej jednego klienta.",
            "invalid_choice": "Nieprawidłowy klient.",
        },
    )

    def __init__(self, *args, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        del self.fields["deadline"]
        if owner is not None:
            self.fields["clients"].queryset = Client.objects.filter(
                owner=owner
            ).order_by("name")

    def clean_deadline(self):
        return None

    def clean(self):
        cleaned_data = super().clean()
        self.clean_timing(cleaned_data)
        return cleaned_data


class PublicRequestForm(_ItemsFieldMixin, _RequestDetailsFieldsMixin, forms.Form):
    """Lets a visitor send a request without registering. Besides the
    recipient, it asks for the sender: their address receives the
    confirmation link and then the permanent link to their panel."""

    sender_name = forms.CharField(
        label="Twoje imię i nazwisko lub nazwa firmy",
        max_length=255,
        help_text="Odbiorca zobaczy, od kogo jest prośba.",
        error_messages={"required": REQUIRED_MESSAGE},
    )
    sender_email = forms.EmailField(
        label="Twój adres email",
        help_text="Wyślemy tu link do potwierdzenia, a potem stały link do panelu.",
        error_messages={
            "required": REQUIRED_MESSAGE,
            "invalid": "Nieprawidłowy adres email.",
        },
    )
    client_name = forms.CharField(
        label="Imię i nazwisko lub nazwa firmy",
        max_length=255,
        error_messages={"required": REQUIRED_MESSAGE},
    )
    client_email = forms.EmailField(
        label="Adres email odbiorcy",
        error_messages={
            "required": REQUIRED_MESSAGE,
            "invalid": "Nieprawidłowy adres email.",
        },
    )
    password = forms.CharField(
        label="Hasło (opcjonalnie)",
        required=False,
        widget=forms.PasswordInput,
        help_text="Zostaw puste, aby nie zabezpieczać linku hasłem.",
    )

    def clean_sender_name(self):
        # Shown in email subjects and headers, where line breaks can't go.
        name = " ".join(self.cleaned_data["sender_name"].split())
        validate_sender_name(name)
        return name

    accept_terms = forms.BooleanField(
        label=(
            "Akceptuję Regulamin wraz z umową powierzenia przetwarzania danych "
            "i Politykę prywatności"
        ),
        required=True,
        error_messages={
            "required": "Musisz zaakceptować regulamin i politykę prywatności."
        },
    )


class RequestEditForm(_RequestDetailsFieldsMixin, forms.Form):
    pass


class PublicPasswordForm(forms.Form):
    password = forms.CharField(
        label="Hasło",
        widget=forms.PasswordInput,
        error_messages={"required": REQUIRED_MESSAGE},
    )


class RequestFilterForm(forms.Form):
    """GET filters for the reminders list. Invalid values are ignored rather
    than reported, so a hand-edited URL never breaks the page."""

    STATUS_CHOICES = [
        ("", "Wszystkie"),
        ("brak_dokumentow", "Brakujące"),
        ("w_trakcie", "W trakcie"),
        ("kompletny", "Kompletne"),
        ("po_terminie", "Po terminie"),
        ("zamkniety", "Zamknięte"),
    ]
    REMINDER_CHOICES = [
        ("", "Wszystkie"),
        ("on", "Włączone"),
        ("off", "Wyłączone"),
    ]
    SORT_CHOICES = [
        ("newest", "Najnowsze"),
        ("oldest", "Najstarsze"),
        ("deadline", "Najbliższy termin"),
        ("name", "Nazwa A-Z"),
    ]

    q = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "type": "search",
                "placeholder": "Szukaj po nazwie, kliencie lub emailu...",
                "aria-label": "Szukaj",
            }
        ),
    )
    client = forms.ModelChoiceField(
        label="Klient",
        queryset=Client.objects.none(),
        required=False,
        empty_label="Wszyscy klienci",
    )
    status = forms.ChoiceField(choices=STATUS_CHOICES, required=False)
    deadline_from = forms.DateField(
        label="Termin od",
        required=False,
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    deadline_to = forms.DateField(
        label="Termin do",
        required=False,
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    reminders = forms.ChoiceField(
        label="Przypomnienia", choices=REMINDER_CHOICES, required=False
    )
    sort = forms.ChoiceField(label="Sortowanie", choices=SORT_CHOICES, required=False)

    def __init__(self, *args, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        if owner is not None:
            self.fields["client"].queryset = Client.objects.filter(
                owner=owner
            ).order_by("name")

    def value(self, name):
        self.is_valid()
        return self.cleaned_data.get(name)
