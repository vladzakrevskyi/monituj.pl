from django import forms

REQUIRED_MESSAGE = "To pole jest wymagane."


class ClientForm(forms.Form):
    name = forms.CharField(
        label="Nazwa klienta",
        max_length=255,
        error_messages={"required": REQUIRED_MESSAGE},
    )
    email = forms.EmailField(
        label="Email",
        error_messages={
            "required": REQUIRED_MESSAGE,
            "invalid": "Nieprawidłowy adres email.",
        },
    )
    phone = forms.CharField(label="Telefon", max_length=32, required=False)
    note = forms.CharField(label="Notatka", required=False, widget=forms.Textarea)


class ClientFilterForm(forms.Form):
    """GET filters for the clients list; invalid values are ignored."""

    STATUS_CHOICES = [
        ("", "Wszyscy"),
        ("aktywny", "Aktywni"),
        ("brak_dokumentow", "Brak dokumentów"),
        ("wszystko_dostarczone", "Komplet"),
        ("nieaktywny", "Nieaktywni"),
    ]
    MISSING_CHOICES = [
        ("", "Wszyscy"),
        ("yes", "Z brakującymi dokumentami"),
        ("no", "Bez braków"),
    ]
    SORT_CHOICES = [
        ("name", "Nazwa A-Z"),
        ("name_desc", "Nazwa Z-A"),
        ("activity", "Ostatnia aktywność"),
        ("missing", "Najwięcej braków"),
        ("newest", "Najnowsi"),
    ]

    q = forms.CharField(
        required=False,
        widget=forms.TextInput(
            attrs={
                "type": "search",
                "placeholder": "Szukaj po nazwie, emailu lub telefonie...",
                "aria-label": "Szukaj klienta",
            }
        ),
    )
    status = forms.ChoiceField(choices=STATUS_CHOICES, required=False)
    missing = forms.ChoiceField(
        label="Brakujące dokumenty", choices=MISSING_CHOICES, required=False
    )
    activity_from = forms.DateField(
        label="Aktywność od",
        required=False,
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    activity_to = forms.DateField(
        label="Aktywność do",
        required=False,
        input_formats=["%Y-%m-%d"],
        widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
    )
    sort = forms.ChoiceField(label="Sortowanie", choices=SORT_CHOICES, required=False)

    def value(self, name):
        self.is_valid()
        return self.cleaned_data.get(name)
