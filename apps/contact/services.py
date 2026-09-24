from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.common.exceptions import RateLimitedAppError
from apps.common.security import get_client_ip, hash_ip
from apps.contact.models import ContactThrottle
from apps.notifications.models import EmailTemplate
from apps.notifications.services import EmailService

LIMIT_PER_HOUR = 5
LIMIT_MESSAGE = (
    "Wysłano już kilka wiadomości w krótkim czasie. Spróbuj ponownie za godzinę "
    f"albo napisz bezpośrednio na {settings.CONTACT_EMAIL}."
)


class ContactService:
    @staticmethod
    def send(form, django_request):
        """Mails the message to the team (replies go to the sender) and a
        short confirmation to the sender (replies go to the team). The
        confirmation deliberately doesn't repeat the message: anyone can type
        any address here, and echoing their text would turn the form into a
        way of sending arbitrary mail from our domain."""
        now = timezone.now()
        ip_hash = hash_ip(get_client_ip(django_request))
        ContactThrottle.objects.filter(created_at__lt=now - timedelta(days=1)).delete()
        recent = ContactThrottle.objects.filter(
            ip_hash=ip_hash, created_at__gte=now - timedelta(hours=1)
        ).count()
        if recent >= LIMIT_PER_HOUR:
            raise RateLimitedAppError(LIMIT_MESSAGE, code="CONTACT_LIMIT_REACHED")
        ContactThrottle.objects.create(ip_hash=ip_hash)

        if form.is_spam():
            return

        data = form.cleaned_data
        context = {
            "contact_name": data["name"],
            "contact_email": data["email"],
            "contact_company": data["company"],
            "contact_topic": form.topic_label(),
            "contact_message": data["message"],
            "team_email": settings.CONTACT_EMAIL,
        }
        EmailService.send(
            EmailTemplate.CONTACT_MESSAGE,
            to_email=settings.CONTACT_EMAIL,
            context=context,
            reply_to=[data["email"]],
        )
        EmailService.send(
            EmailTemplate.CONTACT_CONFIRMATION,
            to_email=data["email"],
            context=context,
            reply_to=[settings.CONTACT_EMAIL],
        )
