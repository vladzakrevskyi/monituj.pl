from django import forms


class LegalAcceptanceForm(forms.Form):
    accept_terms = forms.BooleanField(
        label="Akceptuję Regulamin wraz z umową powierzenia przetwarzania danych",
        required=True,
        error_messages={"required": "Musisz zaakceptować regulamin."},
    )
    accept_privacy_policy = forms.BooleanField(
        label="Zapoznałem się z Polityką prywatności",
        required=True,
        error_messages={"required": "Musisz zaakceptować politykę prywatności."},
    )
