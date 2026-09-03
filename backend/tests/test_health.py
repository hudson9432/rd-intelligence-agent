"""Smoke tests for the initial FastAPI application."""

from app.api.health import health_check
from app.main import app


def test_health_check() -> None:
    response = health_check()

    assert response.model_dump() == {
        "status": "ok",
        "service": "rd-intelligence-agent-backend",
    }


def test_openapi_contains_health_route() -> None:
    schema = app.openapi()

    assert app.title == "R&D Intelligence Agent API"
    assert "/health" in schema["paths"]
