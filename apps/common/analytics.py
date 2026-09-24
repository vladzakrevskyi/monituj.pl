"""Google Tag Manager, switched on by GTM_ID.

GTM runs only where it can't do harm and only with permission:
- on public, indexable pages - never in the panel or on token links, whose
  addresses (/d/<token>/, reset links...) must not reach any third party;
- only after the visitor accepts at least one optional cookie category
  (Google Consent Mode v2, static/js/consent.js), as Polish law requires;
  each tag then checks the consent of its own category.
Which tools run inside GTM, and what the policies say about them, is set in
apps/common/cookies.py and TRACKING_SERVICES.
"""

import re

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

GTM_PATTERN = re.compile(r"^GTM-[A-Z0-9]{4,12}$")

def gtm_id():
    value = (getattr(settings, "GTM_ID", "") or "").strip()
    if value and not GTM_PATTERN.match(value):
        # It ends up in a script URL - refuse anything but a container id.
        raise ImproperlyConfigured(f"GTM_ID {value!r} is not a GTM container id")
    return value


def content_security_policy():
    from apps.common.cookies import csp_sources

    policy = dict(settings.CONTENT_SECURITY_POLICY)
    for directive, sources in csp_sources().items():
        # A directive the base policy leaves out falls back to default-src.
        base = policy.get(directive, policy.get("default-src", ""))
        policy[directive] = " ".join([base, *sources]).strip()
    return policy
