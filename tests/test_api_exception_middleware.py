import json

from django.test import RequestFactory

from apps.common.exceptions import NotFoundAppError, ValidationAppError
from apps.common.middleware import ApiExceptionMiddleware


def _api_request(path="/api/clients/"):
    request = RequestFactory().get(path)
    request.request_id = "req-abc"
    return request


def test_ignores_non_api_paths():
    middleware = ApiExceptionMiddleware(get_response=lambda r: None)
    request = RequestFactory().get("/panel/")
    request.request_id = "req-abc"

    result = middleware.process_exception(request, ValidationAppError("bad"))

    assert result is None


def test_application_error_returns_its_own_code_and_status():
    middleware = ApiExceptionMiddleware(get_response=lambda r: None)
    request = _api_request()

    response = middleware.process_exception(
        request, NotFoundAppError("Nie znaleziono.")
    )
    payload = json.loads(response.content)

    assert response.status_code == 404
    assert payload == {
        "success": False,
        "error": {"code": "NOT_FOUND", "message": "Nie znaleziono."},
    }


def test_unexpected_exception_returns_generic_error_without_leaking_details():
    middleware = ApiExceptionMiddleware(get_response=lambda r: None)
    request = _api_request()

    response = middleware.process_exception(
        request, RuntimeError("db password=hunter2 leaked")
    )
    payload = json.loads(response.content)

    assert response.status_code == 500
    assert payload["error"]["code"] == "INTERNAL_ERROR"
    assert "hunter2" not in json.dumps(payload)
