from django import forms

REQUIRED_MESSAGE = "To pole jest wymagane."

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
            "min_length": "Napisz nieco więcej – co najmniej 10 znaków.",
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

    def clean_name(self):
        return _single_line(self.cleaned_data["name"])

    def clean_company(self):
        return _single_line(self.cleaned_data["company"])

    def is_spam(self):
        return bool(self.cleaned_data.get("website"))

    def topic_label(self):
        return dict(TOPIC_CHOICES)[self.cleaned_data["topic"]]
