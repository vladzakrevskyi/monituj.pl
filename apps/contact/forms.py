import time
from datetime import timedelta

from django import forms
from django.core import signing

REQUIRED_MESSAGE = "To pole jest wymagane."

# Bots against the form (a bot gets "Dziękujemy" and nothing is sent - it
# has no reason to try anything else):
# - the time trap: the page hands out a signed "opened at" (issued); a
#   message sent sooner than MIN_SECONDS after opening, or without one, or
#   with a forged one, is a script - nobody types a message that fast;
# - the browser check: static/js/contact.js copies issued, reversed, into
#   `human` on the first key, click or touch in the form. A script posting
#   straight to the address never runs it.
# Plus the hidden field (website) that only bots fill in.
TOKEN_SALT = "contact-form"
MIN_SECONDS = 3
# A page left open longer gets a "reload" message, not a silent drop - and a
# stolen token isn't reusable for ever.
MAX_AGE = timedelta(days=7)
EXPIRED_MESSAGE = (
    "Formularz był otwarty bardzo długo. Odśwież stronę i wyślij wiadomość jeszcze raz."
)


def new_token():
    return signing.dumps(int(time.time()), salt=TOKEN_SALT)


TOPIC_CHOICES = [
    ("pytanie", "Pytanie o Monituj"),
    ("pomoc", "Pomoc w korzystaniu z konta"),
    ("wspolpraca", "Współpraca lub wdrożenie w firmie"),
    ("rodo", "Dane osobowe (RODO)"),
    ("naduzycie", "Zgłoszenie nadużycia"),
    ("inne", "Inna sprawa"),
]


def _single_line(value):
    # Names end up in email subjects, where a line break is not allowed.
    return " ".join(value.split())


class ContactForm(forms.Form):
    name = forms.CharField(
        label="Imię i nazwisko",
        max_length=120,
        error_messages={"required": REQUIRED_MESSAGE},
    )
    email = forms.EmailField(
        label="Adres email",
        error_messages={
            "required": REQUIRED_MESSAGE,
            "invalid": "Nieprawidłowy adres email.",
        },
    )
    company = forms.CharField(
        label="Firma (opcjonalnie)", max_length=160, required=False
    )
    topic = forms.ChoiceField(
        label="Temat",
        choices=TOPIC_CHOICES,
        initial="pytanie",
        error_messages={"invalid_choice": "Wybierz temat z listy."},
    )
    message = forms.CharField(
        label="Wiadomość",
        min_length=10,
        max_length=5000,
        widget=forms.Textarea(attrs={"rows": 7}),
        error_messages={
            "required": REQUIRED_MESSAGE,
            "min_length": "Napisz nieco więcej - co najmniej 10 znaków.",
            "max_length": "Wiadomość może mieć najwyżej 5000 znaków.",
        },
    )
    consent = forms.BooleanField(
        label=(
            "Wyrażam zgodę na przetwarzanie moich danych osobowych podanych "
            "w formularzu w celu udzielenia odpowiedzi na wiadomość."
        ),
        error_messages={
            "required": "Zaznacz zgodę na przetwarzanie danych, aby wysłać wiadomość."
        },
    )
    # Honeypot: hidden from people, but bots fill in every field they find.
    website = forms.CharField(required=False)
    issued = forms.CharField(required=False)
    human = forms.CharField(required=False)

    def clean_name(self):
        return _single_line(self.cleaned_data["name"])

    def clean_company(self):
        return _single_line(self.cleaned_data["company"])

    def clean(self):
        cleaned = super().clean()
        try:
            self._issued_at = signing.loads(
                cleaned.get("issued") or "",
                salt=TOKEN_SALT,
                max_age=MAX_AGE.total_seconds(),
            )
        except signing.SignatureExpired:
            self._issued_at = 0
        except signing.BadSignature:
            self._issued_at = None
        if self._issued_at is not None and (
            time.time() - self._issued_at > MAX_AGE.total_seconds()
        ):
            self.add_error(None, EXPIRED_MESSAGE)
        return cleaned

    def spam_reason(self):
        """Why this is a bot, or "" for a person."""
        data = self.cleaned_data
        if data.get("website"):
            return "hidden field filled"
        issued_at = getattr(self, "_issued_at", None)
        if not isinstance(issued_at, int):
            return "no or forged time token"
        if time.time() - issued_at < MIN_SECONDS:
            return "sent too fast"
        if data.get("human") != data.get("issued", "")[::-1]:
            return "page script never ran"
        return ""

    def is_spam(self):
        return bool(self.spam_reason())

    def topic_label(self):
        return dict(TOPIC_CHOICES)[self.cleaned_data["topic"]]
