import json

from apps.common.responses import error_response, success_response


def test_success_response_default_shape():
    response = success_response({"status": "ok"})
    payload = json.loads(response.content)

    assert response.status_code == 200
    assert payload == {"success": True, "data": {"status": "ok"}}


def test_success_response_without_data_defaults_to_empty_object():
    response = success_response()
    payload = json.loads(response.content)

    assert payload == {"success": True, "data": {}}


def test_error_response_shape():
    response = error_response("VALIDATION_ERROR", "Nieprawidłowe dane.", status=400)
    payload = json.loads(response.content)

    assert response.status_code == 400
    assert payload == {
        "success": False,
        "error": {"code": "VALIDATION_ERROR", "message": "Nieprawidłowe dane."},
    }
