"""Sign in with Google - the OpenID Connect part: sending the visitor to
Google and checking, beyond doubt, who came back.

- Authorization code flow with PKCE (S256), a one-time `state` bound to this
  browser's session (no login CSRF: a code from someone else's browser is
  refused) and a `nonce` checked inside the ID token (no token replay).
- The code is exchanged server to server; the ID token's signature is
  verified against Google's published keys, together with issuer, audience,
  expiry and nonce. Nothing from the browser is trusted on its own.
- Only the `openid email` scopes: the account needs an address, nothing more.

What to do with the verified identity (log in, sign up, link) lives in
apps/accounts/google_auth.py (GoogleAuthService).
"""

import base64
import hashlib
import hmac
import json
import logging
import secrets
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass

import jwt
from django.conf import settings
from django.urls import reverse

from apps.common.exceptions import ValidationAppError
from apps.common.site import absolute_url

logger = logging.getLogger("monituj")

AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
CERTS_URL = "https://www.googleapis.com/oauth2/v3/certs"
ISSUERS = ["https://accounts.google.com", "accounts.google.com"]
SESSION_KEY = "google_oauth"
FLOW_MAX_AGE = 10 * 60  # seconds from the button to Google's answer
HTTP_TIMEOUT = 10

FAILED_MESSAGE = "Nie udało się zalogować przez Google. Spróbuj ponownie."
EXPIRED_MESSAGE = (
    "Logowanie przez Google trwało zbyt długo albo zostało otwarte w innej "
    "przeglądarce. Spróbuj ponownie."
)

# Google's signing keys, fetched once and cached by the client.
_jwks = jwt.PyJWKClient(
    CERTS_URL, cache_keys=True, lifespan=6 * 3600, timeout=HTTP_TIMEOUT
)


@dataclass(frozen=True)
class GoogleIdentity:
    subject: str  # Google's permanent account id - the only stable key
    email: str
    # Google itself runs this mailbox (Gmail or Google Workspace), so the
    # person signing in controls the address right now. For a Google account
    # made on some other address, Google only checked it once, long ago.
    authoritative: bool


def enabled():
    return bool(settings.GOOGLE_OAUTH_CLIENT_ID and settings.GOOGLE_OAUTH_CLIENT_SECRET)


def redirect_uri():
    return absolute_url(reverse("accounts:google-callback"))


def _b64(raw):
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def authorization_url(request, intent, user=None):
    """Where the button sends the browser. `intent` is "login" (also signs
    up) or "connect" (adds Google to the signed-in account)."""
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    request.session[SESSION_KEY] = {
        "state": state,
        "nonce": nonce,
        "verifier": verifier,
        "intent": intent,
        "user": user.pk if user is not None else None,
        "started": int(time.time()),
    }
    params = {
        "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "redirect_uri": redirect_uri(),
        "response_type": "code",
        "scope": "openid email",
        "state": state,
        "nonce": nonce,
        "code_challenge": _b64(hashlib.sha256(verifier.encode()).digest()),
        "code_challenge_method": "S256",
        # Always let the person pick the account - no silent sign-in.
        "prompt": "select_account",
    }
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def take_flow(request):
    """The pending flow of this browser, removed so it can't be used twice."""
    return request.session.pop(SESSION_KEY, None)


def check_state(flow, returned_state):
    if not flow or not returned_state:
        raise ValidationAppError(EXPIRED_MESSAGE, code="GOOGLE_STATE")
    if not hmac.compare_digest(flow["state"], returned_state):
        raise ValidationAppError(EXPIRED_MESSAGE, code="GOOGLE_STATE")
    if time.time() - flow["started"] > FLOW_MAX_AGE:
        raise ValidationAppError(EXPIRED_MESSAGE, code="GOOGLE_STATE")


def _exchange_code(code, verifier):
    body = urllib.parse.urlencode(
        {
            "code": code,
            "client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
            "client_secret": settings.GOOGLE_OAUTH_CLIENT_SECRET,
            "redirect_uri": redirect_uri(),
            "grant_type": "authorization_code",
            "code_verifier": verifier,
        }
    ).encode()
    http_request = urllib.request.Request(
        TOKEN_URL,
        data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(http_request, timeout=HTTP_TIMEOUT) as response:  # noqa: S310
            payload = json.loads(response.read())
    except (OSError, ValueError) as exc:  # network, HTTP 4xx/5xx, bad JSON
        # The error body may carry details, never the secret - log the type only.
        logger.warning("Google token exchange failed: %s", type(exc).__name__)
        raise ValidationAppError(FAILED_MESSAGE, code="GOOGLE_EXCHANGE") from exc
    id_token = payload.get("id_token")
    if not id_token:
        raise ValidationAppError(FAILED_MESSAGE, code="GOOGLE_EXCHANGE")
    return id_token


def verify_id_token(id_token, nonce):
    try:
        key = _jwks.get_signing_key_from_jwt(id_token)
        claims = jwt.decode(
            id_token,
            key.key,
            algorithms=["RS256"],
            audience=settings.GOOGLE_OAUTH_CLIENT_ID,
            issuer=ISSUERS,
            leeway=60,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
        )
    except jwt.PyJWTError as exc:
        logger.warning("Google ID token rejected: %s", type(exc).__name__)
        raise ValidationAppError(FAILED_MESSAGE, code="GOOGLE_TOKEN") from exc

    if not hmac.compare_digest(str(claims.get("nonce", "")), nonce):
        raise ValidationAppError(FAILED_MESSAGE, code="GOOGLE_TOKEN")
    azp = claims.get("azp")
    if azp and azp != settings.GOOGLE_OAUTH_CLIENT_ID:
        raise ValidationAppError(FAILED_MESSAGE, code="GOOGLE_TOKEN")
    email = str(claims.get("email", "")).strip()
    if not email or claims.get("email_verified") not in (True, "true"):
        raise ValidationAppError(
            "Twoje konto Google nie ma potwierdzonego adresu email. Potwierdź go "
            "w Google albo zarejestruj się adresem email i hasłem.",
            code="GOOGLE_EMAIL_UNVERIFIED",
        )
    # Google's rule: a @gmail.com address, or a Workspace account (hd).
    authoritative = email.lower().endswith("@gmail.com") or bool(claims.get("hd"))
    return GoogleIdentity(
        subject=str(claims["sub"]), email=email, authoritative=authoritative
    )


def identity_from_callback(flow, code):
    if not code:
        raise ValidationAppError(FAILED_MESSAGE, code="GOOGLE_EXCHANGE")
    return verify_id_token(_exchange_code(code, flow["verifier"]), flow["nonce"])
