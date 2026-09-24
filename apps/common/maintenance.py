"""Maintenance mode: while MAINTENANCE_MODE is on, every visitor gets a
"prace techniczne" page (503) - except addresses listed in
MAINTENANCE_ALLOWED_IPS, who use the site normally and see a reminder bar."""

import ipaddress

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.shortcuts import render

from apps.common.responses import error_response
from apps.common.security import get_client_ip

MESSAGE = "Trwają prace techniczne. Spróbuj ponownie za chwilę."
# Load balancers and uptime checks keep working during maintenance.
EXEMPT_PATHS = ("/api/health/",)
RETRY_AFTER_SECONDS = 600


def parse_networks(entries):
    """Accepts single addresses (IPv4/IPv6) and ranges like 10.0.0.0/24."""
    networks = []
    for entry in entries:
        try:
            networks.append(ipaddress.ip_network(entry.strip(), strict=False))
        except ValueError as exc:
            raise ImproperlyConfigured(
                f"MAINTENANCE_ALLOWED_IPS: {entry!r} is not an IP address or range"
            ) from exc
    return networks


def is_allowed(ip, networks):
    try:
        address = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return any(address in network for network in networks)


class MaintenanceModeMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.networks = parse_networks(settings.MAINTENANCE_ALLOWED_IPS)

    def __call__(self, request):
        request.maintenance_bypass = False
        if not settings.MAINTENANCE_MODE or request.path in EXEMPT_PATHS:
            return self.get_response(request)
        if is_allowed(get_client_ip(request), self.networks):
            request.maintenance_bypass = True
            return self.get_response(request)

        if request.path.startswith("/api/"):
            response = error_response("MAINTENANCE", MESSAGE, status=503)
        else:
            response = render(request, "maintenance.html", status=503)
        response["Retry-After"] = str(RETRY_AFTER_SECONDS)
        response["Cache-Control"] = "no-store"
        return response
