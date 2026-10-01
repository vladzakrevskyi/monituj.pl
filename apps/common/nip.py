"""Polish NIP: typed in many shapes, stored as 10 digits."""

import re

WEIGHTS = (6, 5, 7, 2, 3, 4, 5, 6, 7)


def clean(value):
    """'PL 521-301-72-28' -> '5213017228'."""
    value = re.sub(r"[\s-]", "", value or "").upper()
    return value[2:] if value.startswith("PL") else value


def is_valid(nip):
    """10 digits, the last one a checksum."""
    if len(nip) != 10 or not nip.isdigit():
        return False
    check = sum(int(d) * w for d, w in zip(nip, WEIGHTS, strict=False)) % 11
    return check != 10 and check == int(nip[9])
