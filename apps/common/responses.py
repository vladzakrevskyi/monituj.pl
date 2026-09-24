from django.http import JsonResponse


def success_response(data=None, status=200):
    return JsonResponse(
        {"success": True, "data": data if data is not None else {}}, status=status
    )


def error_response(code, message, status=400, fields=None):
    error = {"code": code, "message": message}
    if fields is not None:
        error["fields"] = fields
    return JsonResponse({"success": False, "error": error}, status=status)


def is_ajax_request(request) -> bool:
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def form_errors_payload(form) -> dict:
    """Django's own bound-form errors dict already has the shape we want:
    per-field message lists, with non-field errors under "__all__"."""
    return {field: list(errors) for field, errors in form.errors.items()}


def first_form_error(form) -> str:
    for errors in form.errors.values():
        return errors[0]
    return "Nieprawidłowe dane."


def ajax_form_error_response(form, status=400):
    return error_response(
        "VALIDATION_ERROR",
        first_form_error(form),
        status=status,
        fields=form_errors_payload(form),
    )
