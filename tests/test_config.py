"""Backlog integration settings from .env.test."""

from app.config import get_backlog_integration_settings


def test_backlog_settings_from_env_test():
    settings = get_backlog_integration_settings()
    assert settings.rest_url == "http://127.0.0.1:4010/axis/restservices/griddata"
    assert settings.api_key == "test-not-a-secret"
    assert settings.http_timeout_seconds == 5
    assert settings.tenant_id == "TEST_TENANT"
    assert settings.organization == "Test Org"
    assert settings.grid_id == 999999
    assert settings.dataspy_id == 1
    assert settings.backlog_endpoint == ""
    assert settings.schedule_endpoint == "http://127.0.0.1:4010/api/workorders"


def test_rest_url_prefers_explicit_over_base_and_path(monkeypatch):
    monkeypatch.setenv("BACKLOG_REST_URL", "http://example.com/full")
    monkeypatch.setenv("BACKLOG_INTEGRATION_BASE_URL", "http://ignored")
    monkeypatch.setenv("BACKLOG_BACKLOG_PATH", "ignored/path")
    settings = get_backlog_integration_settings()
    assert settings.rest_url == "http://example.com/full"
