import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from apps.common.site import absolute_url
from apps.common.typography import fix_orphans, fix_orphans_text
from apps.notifications.models import EmailLog, EmailStatus
from apps.requests.models import RequestItemStatus

logger = logging.getLogger("monituj")

NOT_DELIVERED = [
    RequestItemStatus.BRAK,
    RequestItemStatus.W_TRAKCIE,
    RequestItemStatus.ODRZUCONY,
]


def _base_context():
    return {
        "site_url": absolute_url("/"),
        "privacy_url": absolute_url(reverse("legal:privacy")),
        "terms_url": absolute_url(reverse("legal:terms")),
    }


def _request_context(request):
    """Everything a request-related email may show: who is asking, for what,
    by when, what is still missing and where to upload or review it."""
    return {
        "sender_name": request.created_by.display_name or "",
        "request_name": request.name,
        "deadline": request.deadline,
        "retention_days": request.retention_days,
        "link": absolute_url(f"/d/{request.public_token}/"),
        "panel_link": absolute_url(reverse("requests:detail", args=[request.pk])),
        "missing_items": list(
            request.items.filter(status__in=NOT_DELIVERED)
            .order_by("id")
            .values_list("name", flat=True)
        ),
    }


def _is_demo(to_email, request):
    """Demo accounts must never send real email - otherwise anyone could use
    a throwaway demo to mail arbitrary addresses."""
    from apps.demo.models import DEMO_EMAIL_DOMAIN, is_demo_user

    if to_email.lower().endswith("@" + DEMO_EMAIL_DOMAIN):
        return True
    return request is not None and is_demo_user(request.created_by)


def _default_reply_to(to_email, request):
    """Emails come from the no-reply address, so Reply-To decides where an
    answer lands. A client answering a request email is talking to the firm
    that asked for the documents; everything else goes to the Monituj team."""
    if request is not None and to_email.lower() == request.client.email.lower():
        owner = request.created_by
        # The shared account behind no-account requests is inactive.
        if owner.is_active and owner.email:
            return [owner.email]
    return [settings.CONTACT_EMAIL]


class EmailService:
    @staticmethod
    def send(template, to_email, context=None, request=None, log=True, reply_to=None):
        """Renders and sends one email. log=False sends without leaving an
        EmailLog row - used when the data it would describe is being erased."""
        full_context = _base_context()
        if request is not None:
            full_context.update(_request_context(request))
        full_context.update(context or {})

        subject = render_to_string(
            f"notifications/emails/{template}_subject.txt", full_context
        ).strip()
        text_body = fix_orphans_text(
            render_to_string(
                f"notifications/emails/{template}_body.txt", full_context
            ).strip()
        )
        html_body = fix_orphans(
            render_to_string(
                f"notifications/emails/{template}_body.html",
                {**full_context, "subject": subject},
            )
        )

        if _is_demo(to_email, request):
            if not log:
                return None
            return EmailLog.objects.create(
                recipient_email=to_email,
                template=template,
                request=request,
                status=EmailStatus.SKIPPED,
            )

        try:
            message = EmailMultiAlternatives(
                subject,
                text_body,
                settings.DEFAULT_FROM_EMAIL,
                [to_email],
                reply_to=reply_to or _default_reply_to(to_email, request),
            )
            message.attach_alternative(html_body, "text/html")
            message.send(using="default")
            status = EmailStatus.SENT
            sent_at = timezone.now()
        except Exception:
            logger.exception("Failed to send email template=%s", template)
            status = EmailStatus.FAILED
            sent_at = None

        if not log:
            return None
        return EmailLog.objects.create(
            recipient_email=to_email,
            template=template,
            request=request,
            status=status,
            sent_at=sent_at,
        )
