import pytest
from fastapi.testclient import TestClient

from backend import SERVICE_NAME, __version__
from backend.main import create_app


@pytest.fixture
def client():
    with TestClient(create_app()) as test_client:
        yield test_client


def test_health_returns_ok(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "service": SERVICE_NAME, "version": __version__}


def test_health_is_deterministic(client):
    """No timestamps, no counters — two calls must be byte-identical."""
    assert client.get("/api/health").json() == client.get("/api/health").json()


def test_health_needs_no_authentication(client):
    """architecture.md section 9 lists /api/health as the one unauthenticated route."""
    assert client.get("/api/health").status_code == 200


def test_health_exposes_no_configuration(client):
    """A liveness probe must not leak endpoints, deployment names or secrets."""
    body = response_text = client.get("/api/health").text
    for leaked in ("supabase", "foundry", "key", "endpoint", "invalid"):
        assert leaked not in body.lower()
    assert "example" not in response_text.lower()


def test_unknown_route_is_not_served(client):
    assert client.get("/api/does-not-exist").status_code == 404
