import json

from django.views.decorators.http import require_http_methods

from apps.clients.forms import ClientForm
from apps.clients.serializers import serialize_client
from apps.clients.services import ClientService
from apps.common.decorators import api_login_required
from apps.common.exceptions import ValidationAppError
from apps.common.responses import success_response


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
def clients_collection(request):
    if request.method == "POST":
        form = ClientForm(_parse_json_body(request))
        if not form.is_valid():
            raise ValidationAppError(_first_form_error(form))

        client = ClientService.create(
            owner=request.user,
            name=form.cleaned_data["name"],
            email=form.cleaned_data["email"],
            phone=form.cleaned_data["phone"],
            note=form.cleaned_data["note"],
            request=request,
        )
        client = ClientService.get_owned_client(request.user, client.pk)
        return success_response(serialize_client(client), status=201)

    search = request.GET.get("q", "").strip()
    page = request.GET.get("page", 1)
    page_obj = ClientService.list_for_owner(request.user, search=search, page=page)
    return success_response(
        {
            "results": [serialize_client(c) for c in page_obj.object_list],
            "page": page_obj.number,
            "num_pages": page_obj.paginator.num_pages,
            "count": page_obj.paginator.count,
        }
    )


@api_login_required
@require_http_methods(["GET", "PATCH", "DELETE"])
def client_detail(request, client_id):
    client = ClientService.get_owned_client(request.user, client_id)

    if request.method == "GET":
        return success_response(serialize_client(client))

    if request.method == "PATCH":
        form = ClientForm(_parse_json_body(request))
        if not form.is_valid():
            raise ValidationAppError(_first_form_error(form))

        ClientService.update(
            client,
            name=form.cleaned_data["name"],
            email=form.cleaned_data["email"],
            phone=form.cleaned_data["phone"],
            note=form.cleaned_data["note"],
            request=request,
        )
        client = ClientService.get_owned_client(request.user, client_id)
        return success_response(serialize_client(client))

    ClientService.delete(client, request=request)
    return success_response({"deleted": True})
