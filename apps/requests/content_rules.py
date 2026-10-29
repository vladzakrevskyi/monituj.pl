"""What no office ever needs from a client - and a fraudster always asks
for: a PIN, a card number or its CVV, a BLIK or SMS code, the password to a
bank. A request asking for any of them is refused while the account hasn't
paid (the trial included): a fraudster signs up for free, while a firm that
pays is known by its invoice. Checked in the request's name, description,
document list and question (apps/requests/forms.py), read the way
apps/accounts/sender.py reads names - "P1N" and "kod 5MS" count too.

Not "hasło" on its own: offices do ask for a KSeF token or a password to an
accounting program's export, which is none of the above."""

import re

from django.core.exceptions import ValidationError

from apps.accounts.sender import spellings

FORBIDDEN = [
    (r"pin(u|em|y|ow)?", "kod PIN"),
    (r"blik\w*", "kod BLIK"),
    (r"cvv\d?|cvc\d?", "kod CVV"),
    (
        r"(numer\w*|nr|dane) (pelny |pelne |cal\w* )?kart\w* "
        r"(platnicz|kredytow|debetow|bankow)\w*",
        "numer karty",
    ),
    (r"kod\w* (z )?(sms\w*|autoryzacyjn\w*)", "kod SMS"),
    (
        r"(hasl\w*|hasel|login\w*|dane (do )?logowania) do "
        r"(banku|bankowosci\w*|kont\w* bankow\w*|serwisu bankow\w*|"
        r"aplikacji bankow\w*)",
        "hasło do banku",
    ),
]
_FORBIDDEN = [(re.compile(rf"\b({pattern})\b"), label) for pattern, label in FORBIDDEN]


def found_in(text):
    """The label of what the text asks for, or None."""
    for spelling in spellings(text):
        for pattern, label in _FORBIDDEN:
            if pattern.search(spelling):
                return label
    return None


def applies_to(owner):
    """Every account until it pays; the no-account form (owner None) too."""
    if owner is None:
        return True
    from apps.billing.services import account_for, is_subscribed

    return not is_subscribed(account_for(owner))


def message(label):
    return (
        f"Prośba o {label} wygląda jak próba wyłudzenia - takich danych biuro "
        "nigdy nie potrzebuje od klienta, więc nie można o nie prosić przez "
        "Monituj. Usuń to z treści. Jeśli to pomyłka, napisz do nas."
    )


def check(text):
    label = found_in(text or "")
    if label:
        raise ValidationError(message(label), code="forbidden_content")
