import hashlib
import hmac
import secrets

from django.conf import settings


def generate_public_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def get_client_ip(django_request) -> str:
    """The visitor's address as seen by our own proxy. nginx (deploy/) sets
    X-Forwarded-For to exactly that address; if some other proxy appends to
    the header instead, only its last entry was added by a proxy - anything
    before it came from the visitor and could be made up."""
    forwarded = django_request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[-1].strip()
    return django_request.META.get("REMOTE_ADDR", "")


def hash_ip(ip: str) -> str:
    """Keyed hash: without the secret key there are too few IPv4 addresses
    for a plain hash to hide them."""
    return hmac.new(
        settings.SECRET_KEY.encode(), f"ip:{ip}".encode(), hashlib.sha256
    ).hexdigest()
