from django.views.decorators.http import require_http_methods

from apps.common.decorators import api_login_required
from apps.common.responses import success_response
from apps.reminders.services import ReminderService
from apps.requests.services import RequestService


@api_login_required
@require_http_methods(["POST"])
def send_manual_reminder(request, request_id):
    request_obj = RequestService.get_owned_request(request.user, request_id)
    ReminderService.send_manual(request_obj, actor=request.user, django_request=request)
    return success_response({"sent": True})
