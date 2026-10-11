"""Two kinds of things a request can ask for: a file to send, or something
to do and confirm - "Nadaj biuru uprawnienia w KSeF", "Podpisz UPL-1 w
e-Urzędzie" - where there is no file, only "Zrobione".

A request's items carry the kind in their own field (RequestItem.kind).
Everywhere a list is kept as plain names - the request form, own templates,
recurring requests - a confirm-only item is the name with " (bez pliku)" at
the end: one string through every form and list, turned into the field when
the request is made (split) and back when a request becomes a template
(joined)."""

CONFIRM_SUFFIX = " (bez pliku)"


def split(text):
    """ "Nadaj uprawnienia (bez pliku)" -> ("Nadaj uprawnienia", True)."""
    text = (text or "").strip()
    if text.lower().endswith(CONFIRM_SUFFIX.strip().lower()):
        name = text[: -len(CONFIRM_SUFFIX.strip())].rstrip()
        if name:
            return name, True
    return text, False


def joined(name, confirm):
    return f"{name}{CONFIRM_SUFFIX}" if confirm else name
