"""Encryption at rest for uploaded documents (envelope encryption).

- Every file gets its own random 256-bit key and is encrypted with
  AES-256-GCM. The file's storage path is authenticated with it, so an
  encrypted file moved to another document's place won't open.
- That per-file key is itself encrypted ("wrapped") with the master key and
  stored next to the document in the database. The master key lives only in
  the environment (DOCUMENTS_ENCRYPTION_KEY) - never in the database, the
  storage volume or the hosting backups. A copied disk or backup without it
  is unreadable.
- Rotating the master key: put the new one in DOCUMENTS_ENCRYPTION_KEY, the
  old one in DOCUMENTS_ENCRYPTION_OLD_KEYS, run `manage.py
  rewrap_document_keys` (re-wraps the small per-file keys, the files stay
  as they are), then drop the old key.

Lose the master key and the documents are gone - keep a copy outside the
server (README: "Szyfrowanie dokumentów").
"""

import base64
import hashlib
import os

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

MAGIC = b"MONITUJ-ENC-1\n"
NONCE_SIZE = 12
KEY_WRAP_AAD = b"monituj-document-key"


class DecryptionError(Exception):
    """Wrong key, a changed file or a file from another document."""


def generate_key():
    return base64.urlsafe_b64encode(AESGCM.generate_key(bit_length=256)).decode()


def _decode(raw, name):
    try:
        key = base64.urlsafe_b64decode(raw.strip().encode())
    except (ValueError, TypeError) as exc:
        raise ImproperlyConfigured(f"{name} is not valid base64") from exc
    if len(key) != 32:
        raise ImproperlyConfigured(f"{name} must be 32 bytes (256 bits)")
    return key


def key_id(key):
    return hashlib.sha256(b"monituj-key-id" + key).hexdigest()[:16]


def _keyring():
    """(current key or None, {key id: key} for everything that may decrypt)."""
    current_raw = getattr(settings, "DOCUMENTS_ENCRYPTION_KEY", "") or ""
    current = _decode(current_raw, "DOCUMENTS_ENCRYPTION_KEY") if current_raw else None
    ring = {}
    for index, raw in enumerate(getattr(settings, "DOCUMENTS_ENCRYPTION_OLD_KEYS", [])):
        if raw.strip():
            key = _decode(raw, f"DOCUMENTS_ENCRYPTION_OLD_KEYS[{index}]")
            ring[key_id(key)] = key
    if current is not None:
        ring[key_id(current)] = current
    return current, ring


def enabled():
    return _keyring()[0] is not None


def current_key_id():
    current, _ = _keyring()
    return key_id(current) if current else ""


def encrypt(plaintext, aad):
    """-> (bytes to store, wrapped file key, master key id)."""
    current, _ = _keyring()
    if current is None:
        raise ImproperlyConfigured("DOCUMENTS_ENCRYPTION_KEY is not set")
    file_key = AESGCM.generate_key(bit_length=256)
    nonce = os.urandom(NONCE_SIZE)
    blob = MAGIC + nonce + AESGCM(file_key).encrypt(nonce, plaintext, aad)
    return blob, wrap(file_key, current), key_id(current)


def wrap(file_key, master_key):
    nonce = os.urandom(NONCE_SIZE)
    sealed = AESGCM(master_key).encrypt(nonce, file_key, KEY_WRAP_AAD)
    return base64.b64encode(nonce + sealed).decode()


def unwrap(wrapped, wrapping_key_id):
    _, ring = _keyring()
    master_key = ring.get(wrapping_key_id)
    if master_key is None:
        raise DecryptionError(f"No master key with id {wrapping_key_id}")
    raw = base64.b64decode(wrapped)
    try:
        return AESGCM(master_key).decrypt(
            raw[:NONCE_SIZE], raw[NONCE_SIZE:], KEY_WRAP_AAD
        )
    except InvalidTag as exc:
        raise DecryptionError("Wrapped key does not match the master key") from exc


def decrypt(blob, wrapped, wrapping_key_id, aad):
    if not blob.startswith(MAGIC):
        raise DecryptionError("Not an encrypted document")
    body = blob[len(MAGIC) :]
    file_key = unwrap(wrapped, wrapping_key_id)
    try:
        return AESGCM(file_key).decrypt(body[:NONCE_SIZE], body[NONCE_SIZE:], aad)
    except InvalidTag as exc:
        raise DecryptionError("File was changed or belongs elsewhere") from exc
