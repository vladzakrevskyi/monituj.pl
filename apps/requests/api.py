import json

from django.core.exceptions import ValidationError as DjangoValidationError
from django.core.validators import validate_email
from django.views.decorators.http import require_http_methods

from apps.clients.services import ClientService
from apps.common import throttle
from apps.common.decorators import api_login_required
from apps.common.exceptions import ValidationAppError
from apps.common.responses import success_response
from apps.requests.forms import RequestEditForm, RequestForm
from apps.requests.serializers import serialize_request
from apps.requests.services import RequestService

SEND_LINK_PER_DAY = 50


def _parse_json_body(request):
    if not request.body:
        return {}
    try:
        return json.loads(request.body)
    except ValueError as exc:
        raise ValidationAppError(
            "Nieprawidłowe dane JSON.", code="INVALID_JSON"
        ) from exc


def _first_form_error(form):
    for errors in form.errors.values():
        return errors[0]
    return "Nieprawidłowe dane."


@api_login_required
@require_http_methods(["GET", "POST"])
def requests_collection(request):
    if request.method == "POST":
        data = _parse_json_body(request)
        form = RequestForm(data, owner=request.user)
        item_names = [
            str(name).strip() for name in data.get("items", []) if str(name).strip()
        ]
        if not item_names:
            raise ValidationAppError("Dodaj co najmniej jeden dokument do listy.")
        if not form.is_valid():
            raise ValidationAppError(_first_form_error(form))

        if form.cleaned_data.get("client"):
            client_id = form.cleaned_data["client"].pk
        else:
            new_client = ClientService.get_or_create_by_email(
                owner=request.user,
                email=form.cleaned_data["new_client_email"],
                name=form.cleaned_data.get("new_client_name", ""),
                request=request,
            )
            client_id = new_client.pk

        request_obj = RequestService.create(
            owner=request.user,
            client_id=client_id,
            name=form.cleaned_data["name"],
            description=form.cleaned_data["description"],
            deadline=form.cleaned_data["deadline"],
            item_names=item_names,
            password=form.cleaned_data["password"],
            reminder_settings=form.reminder_settings(),
            request=request,
        )
        request_obj = RequestService.get_owned_request(request.user, request_obj.pk)
        return success_response(serialize_request(request_obj), status=201)

    search = request.GET.get("q", "").strip()
    status_filter = request.GET.get("status", "").strip() or None
    page = request.GET.get("page", 1)
    page_obj = RequestService.list_for_owner(
        request.user, search=search, status_filter=status_filter, page=page
    )
    return success_response(
        {
            "results": [serialize_request(r) for r in page_obj.object_list],
            "page": page_obj.number,
            "num_pages": page_obj.paginator.num_pages,
            "count": page_obj.paginator.count,
        }
    )


@api_login_required
@require_http_methods(["GET", "PATCH"])
def request_detail(request, request_id):
    request_obj = RequestService.get_owned_request(request.user, request_id)

    if request.method == "PATCH":
        data = _parse_json_body(request)
        form = RequestEditForm(data)
        if not form.is_valid():
            raise ValidationAppError(_first_form_error(form))

        RequestService.update(
            request_obj,
            name=form.cleaned_data["name"],
            description=form.cleaned_data["description"],
            deadline=form.cleaned_data["deadline"],
            reminder_settings=form.reminder_settings(),
            request=request,
        )
        request_obj = RequestService.get_owned_request(request.user, request_id)

    return success_response(serialize_request(request_obj))


@api_login_required
@require_http_methods(["POST"])
def send_link(request, request_id):
    request_obj = RequestService.get_owned_request(request.user, request_id)
    if request_obj.awaiting_confirmation:
        raise ValidationAppError(
            "Najpierw potwierdź wysłanie prośby linkiem z maila.",
            code="AWAITING_CONFIRMATION",
        )
    data = _parse_json_body(request)
    email = str(data.get("email", "")).strip()

    if not email:
        raise ValidationAppError("Podaj adres email.", code="EMAIL_REQUIRED")
    try:
        validate_email(email)
    except DjangoValidationError as exc:
        raise ValidationAppError(
            "Nieprawidłowy adres email.", code="INVALID_EMAIL"
        ) from exc

    throttle.consume(
        f"send-link:{request.user.pk}",
        SEND_LINK_PER_DAY,
        throttle.DAY,
        "Dzisiaj wysłano już bardzo dużo linków. Spróbuj ponownie jutro.",
        code="SEND_LINK_LIMIT_REACHED",
    )
    RequestService.send_invitation(
        request_obj, email, actor=request.user, django_request=request
    )
    return success_response({"sent": True, "email": email})
