from django import forms

REQUIRED_MESSAGE = "To pole jest wymagane."


class RegistrationForm(forms.Form):
    email = forms.EmailField(
        label="Adres email",
        error_messages={
            "required": REQUIRED_MESSAGE,
            "invalid": "Nieprawidłowy adres email.",
        },
    )
    password = forms.CharField(
        label="Hasło",
        widget=forms.PasswordInput,
        error_messages={"required": REQUIRED_MESSAGE},
    )
    password_confirm = forms.CharField(
        label="Powtórz hasło",
        widget=forms.PasswordInput,
        error_messages={"required": REQUIRED_MESSAGE},
    )
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

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")
        if password and password_confirm and password != password_confirm:
            self.add_error("password_confirm", "Hasła nie są identyczne.")
        return cleaned_data


class LoginForm(forms.Form):
    email = forms.EmailField(
        label="Adres email",
        error_messages={
            "required": REQUIRED_MESSAGE,
            "invalid": "Nieprawidłowy adres email.",
        },
    )
    password = forms.CharField(
        label="Hasło",
        widget=forms.PasswordInput,
        error_messages={"required": REQUIRED_MESSAGE},
    )


class PasswordResetRequestForm(forms.Form):
    email = forms.EmailField(
        label="Adres email",
        error_messages={
            "required": REQUIRED_MESSAGE,
            "invalid": "Nieprawidłowy adres email.",
        },
    )


class PasswordResetConfirmForm(forms.Form):
    password = forms.CharField(
        label="Nowe hasło",
        widget=forms.PasswordInput,
        error_messages={"required": REQUIRED_MESSAGE},
    )
    password_confirm = forms.CharField(
        label="Powtórz hasło",
        widget=forms.PasswordInput,
        error_messages={"required": REQUIRED_MESSAGE},
    )

    def clean(self):
        cleaned_data = super().clean()
        password = cleaned_data.get("password")
        password_confirm = cleaned_data.get("password_confirm")
        if password and password_confirm and password != password_confirm:
            self.add_error("password_confirm", "Hasła nie są identyczne.")
        return cleaned_data


class ProfileForm(forms.Form):
    display_name = forms.CharField(
        label="Nazwa widoczna dla klientów (np. nazwa firmy)",
        required=False,
        max_length=255,
    )

    def clean_display_name(self):
        # Used in email subjects, where a line break stops the email entirely.
        return " ".join(self.cleaned_data["display_name"].split())


class PasswordChangeForm(forms.Form):
    current_password = forms.CharField(
        label="Obecne hasło",
        widget=forms.PasswordInput,
        error_messages={"required": REQUIRED_MESSAGE},
    )
    new_password = forms.CharField(
        label="Nowe hasło",
        widget=forms.PasswordInput,
        error_messages={"required": REQUIRED_MESSAGE},
    )
    new_password_confirm = forms.CharField(
        label="Powtórz nowe hasło",
        widget=forms.PasswordInput,
        error_messages={"required": REQUIRED_MESSAGE},
    )

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get("new_password")
        new_password_confirm = cleaned_data.get("new_password_confirm")
        if (
            new_password
            and new_password_confirm
            and new_password != new_password_confirm
        ):
            self.add_error("new_password_confirm", "Hasła nie są identyczne.")
        return cleaned_data


class EmailChangeForm(forms.Form):
    new_email = forms.EmailField(
        label="Nowy adres email",
        error_messages={
            "required": REQUIRED_MESSAGE,
            "invalid": "Nieprawidłowy adres email.",
        },
    )
    current_password = forms.CharField(
        label="Obecne hasło",
        widget=forms.PasswordInput,
        error_messages={"required": REQUIRED_MESSAGE},
    )


class SetPasswordForm(forms.Form):
    """For accounts created without a password (requests sent without
    registering): there is no current password to confirm."""

    new_password = forms.CharField(
        label="Nowe hasło",
        widget=forms.PasswordInput,
        error_messages={"required": REQUIRED_MESSAGE},
    )
    new_password_confirm = forms.CharField(
        label="Powtórz nowe hasło",
        widget=forms.PasswordInput,
        error_messages={"required": REQUIRED_MESSAGE},
    )

    def clean(self):
        cleaned_data = super().clean()
        new_password = cleaned_data.get("new_password")
        confirm = cleaned_data.get("new_password_confirm")
        if new_password and confirm and new_password != confirm:
            self.add_error("new_password_confirm", "Hasła nie są identyczne.")
        return cleaned_data


class AccountDeletionForm(forms.Form):
    current_password = forms.CharField(
        label="Obecne hasło",
        widget=forms.PasswordInput,
        error_messages={"required": REQUIRED_MESSAGE},
    )
    understood = forms.BooleanField(
        label=(
            "Rozumiem, że konto, klienci, prośby i wszystkie przesłane pliki "
            "zostaną trwale usunięte"
        ),
        label_suffix="",
        error_messages={"required": "Potwierdź, że rozumiesz skutki usunięcia."},
    )

    def __init__(self, *args, require_password=True, **kwargs):
        super().__init__(*args, **kwargs)
        if not require_password:
            del self.fields["current_password"]
