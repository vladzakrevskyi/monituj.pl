import hashlib
import secrets


def generate_public_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def get_client_ip(django_request) -> str:
    forwarded = django_request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return django_request.META.get("REMOTE_ADDR", "")


def hash_ip(ip: str) -> str:
    return hash_token(f"ip:{ip}")
