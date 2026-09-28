import logging

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from apps.accounts.sender import sender_context
from apps.common.link_titles import add_link_titles
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


def _request_context(request, to_email):
    """Everything a request-related email may show: who is asking, for what,
    by when, what is still missing and where to upload or review it."""
    from apps.requests.links import owner_link, recipient_portal_url

    to_recipient = to_email.lower() == request.client.email.lower()
    return {
        **sender_context(request.created_by),
        "request_name": request.name,
        "deadline": request.deadline,
        "retention_days": request.retention_days,
        "link": absolute_url(f"/d/{request.public_token}/"),
        "panel_link": owner_link(
            request.created_by, reverse("requests:detail", args=[request.pk])
        ),
        # Every request to this address, from any sender, on one page.
        "portal_link": recipient_portal_url(to_email) if to_recipient else "",
        "promo_url": _promo_url(request.created_by) if to_recipient else "",
        "missing_items": list(
            request.items.filter(status__in=NOT_DELIVERED)
            .order_by("id")
            .values_list("name", flat=True)
        ),
    }


PROMO_TEXT = (
    "Zbierasz dokumenty od klientów? Monituj przypomni o nich za Ciebie – "
    "zacznij za darmo:"
)


def _promo_url(owner):
    """Emails to recipients of free-plan senders end with a line about
    Monituj; paid plans (and the trial) send them without it."""
    from apps.billing.services import plan_for

    _plan, source = plan_for(owner)
    return absolute_url("/") if source == "free" else ""


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
    def send(
        template,
        to_email,
        context=None,
        request=None,
        log=True,
        reply_to=None,
        attachments=None,
    ):
        """Renders and sends one email. log=False sends without leaving an
        EmailLog row - used when the data it would describe is being erased.
        attachments: (filename, bytes, mimetype) tuples, e.g. an invoice PDF."""
        full_context = _base_context()
        if request is not None:
            full_context.update(_request_context(request, to_email))
        full_context.update(context or {})

        subject = render_to_string(
            f"notifications/emails/{template}_subject.txt", full_context
        ).strip()
        text_body = fix_orphans_text(
            render_to_string(
                f"notifications/emails/{template}_body.txt", full_context
            ).strip(),
            keep_lines=True,
        )
        if full_context.get("promo_url"):
            text_body += f"\n\n{PROMO_TEXT} {full_context['promo_url']}"
        html_body = add_link_titles(
            fix_orphans(
                render_to_string(
                    f"notifications/emails/{template}_body.html",
                    {**full_context, "subject": subject},
                )
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
            for filename, content, mimetype in attachments or ():
                message.attach(filename, content, mimetype)
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
