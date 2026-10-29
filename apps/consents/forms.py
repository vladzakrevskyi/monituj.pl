from django import forms


class SignupConsentForm(forms.Form):
    """Signing up (email, Google, a team invitation): one checkbox for the
    Terms with the DPA and the Privacy policy."""

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
