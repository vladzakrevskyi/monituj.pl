from datetime import datetime, time

from django import forms
from django.utils import timezone as django_timezone

from apps.clients.models import Client
from apps.requests.models import DEFAULT_RETENTION_DAYS, MAX_RETENTION_DAYS

REQUIRED_MESSAGE = "To pole jest wymagane."


NO_ITEMS_MESSAGE = "Dodaj co najmniej jeden dokument do listy."

RETENTION_PRESETS = [30, 90, 180, 365]
RETENTION_CUSTOM = "custom"
RETENTION_CHOICES = [
    ("30", "30 dni"),
    ("90", "90 dni (domyślnie)"),
    ("180", "180 dni"),
    ("365", "1 rok (365 dni)"),
    (RETENTION_CUSTOM, "Własny okres"),
]


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
    reminder_send_hour = forms.IntegerField(
        label="Godzina wysyłki",
        required=False,
        min_value=0,
        max_value=23,
        initial=9,
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
        return {
            "reminders_enabled": self.cleaned_data.get("reminders_enabled", False),
            "first_reminder_after_days": self.cleaned_data.get(
                "first_reminder_after_days"
            )
            or 2,
            "reminder_frequency_days": self.cleaned_data.get("reminder_frequency_days")
            or 3,
            "max_reminders": self.cleaned_data.get("max_reminders") or 3,
            "reminder_send_hour": self.cleaned_data.get("reminder_send_hour")
            if self.cleaned_data.get("reminder_send_hour") is not None
            else 9,
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


class RequestForm(_ItemsFieldMixin, _RequestDetailsFieldsMixin, forms.Form):
    client = forms.ModelChoiceField(
        label="Istniejący klient",
        queryset=Client.objects.none(),
        required=False,
        empty_label="-- wybierz klienta --",
        error_messages={"invalid_choice": "Nieprawidłowy klient."},
    )
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

    def __init__(self, *args, owner=None, **kwargs):
        super().__init__(*args, **kwargs)
        if owner is not None:
            self.fields["client"].queryset = Client.objects.filter(
                owner=owner
            ).order_by("name")

    def clean(self):
        cleaned_data = super().clean()
        has_client = cleaned_data.get("client") or cleaned_data.get("new_client_email")
        if not has_client and "new_client_email" not in self.errors:
            self.add_error(
                "client", "Wybierz istniejącego klienta lub podaj email nowego klienta."
            )
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
        return " ".join(self.cleaned_data["sender_name"].split())

    accept_terms = forms.BooleanField(
        label="Akceptuję Regulamin i Politykę prywatności",
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
