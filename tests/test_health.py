import pytest


@pytest.mark.django_db
def test_health_check_returns_ok(client):
    response = client.get("/api/health/")

    assert response.status_code == 200
    assert response.json() == {"success": True, "data": {"status": "ok"}}


@pytest.mark.django_db
def test_health_check_sets_security_headers(client):
    response = client.get("/api/health/")

    assert response["X-Frame-Options"] == "DENY"
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Referrer-Policy"] == "same-origin"
    assert "default-src 'self'" in response["Content-Security-Policy"]
    assert "camera=()" in response["Permissions-Policy"]
    assert response["X-Request-ID"]
