"""Test environment.

Required settings are injected as environment variables at import time, before
any test module imports the application. Environment variables take precedence
over a .env file, so these tests behave the same on a machine that has a real
.env and one that does not. None of these values reach any external service.
"""

import os

import pytest

FAKE_ENV = {
    "FOUNDRY_ENDPOINT": "https://example-endpoint.invalid",
    "FOUNDRY_API_VERSION": "test-api-version",
    "FOUNDRY_CHAT_DEPLOYMENT": "test-chat-deployment",
    "FOUNDRY_EMBEDDING_DEPLOYMENT": "test-embedding-deployment",
    "SUPABASE_URL": "https://example-project.invalid",
    "SUPABASE_ANON_KEY": "test-anon-key",
    "SUPABASE_SERVICE_ROLE_KEY": "test-service-role-key",
    "APP_ENV": "test",
    "CORS_ALLOWED_ORIGINS": "http://localhost:5173",
}

for _key, _value in FAKE_ENV.items():
    os.environ.setdefault(_key, _value)


@pytest.fixture(autouse=True)
def _clear_config_caches():
    """get_settings and get_pipeline_config are cached; tests must not share state."""
    from backend.config import get_pipeline_config, get_settings

    get_settings.cache_clear()
    get_pipeline_config.cache_clear()
    yield
    get_settings.cache_clear()
    get_pipeline_config.cache_clear()
