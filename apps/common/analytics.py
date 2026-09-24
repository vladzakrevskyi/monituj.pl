"""Google Tag Manager, switched on by GTM_ID.

GTM runs only where it can't do harm and only with permission:
- on public, indexable pages - never in the panel or on token links, whose
  addresses (/d/<token>/, reset links...) must not reach any third party;
- only after the visitor accepts analytics cookies (Google Consent Mode v2,
  static/js/consent.js), as Polish law requires for non-essential cookies.
"""

import re

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

GTM_PATTERN = re.compile(r"^GTM-[A-Z0-9]{4,12}$")

# What GTM and Google Analytics 4 need from the browser.
GTM_SOURCES = {
    "script-src": ["https://www.googletagmanager.com"],
    "img-src": [
        "https://www.googletagmanager.com",
        "https://*.google-analytics.com",
    ],
    "connect-src": [
        "https://www.googletagmanager.com",
        "https://*.google-analytics.com",
        "https://*.analytics.google.com",
    ],
}


def gtm_id():
    value = (getattr(settings, "GTM_ID", "") or "").strip()
    if value and not GTM_PATTERN.match(value):
        # It ends up in a script URL - refuse anything but a container id.
        raise ImproperlyConfigured(f"GTM_ID {value!r} is not a GTM container id")
    return value


def content_security_policy():
    policy = dict(settings.CONTENT_SECURITY_POLICY)
    if gtm_id():
        for directive, sources in GTM_SOURCES.items():
            policy[directive] = " ".join([policy.get(directive, ""), *sources]).strip()
    return policy
