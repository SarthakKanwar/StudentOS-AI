import pytest
import yaml

from backend.config import (
    RETRIEVAL_CONFIG_PATH,
    ConfigurationError,
    Settings,
    load_pipeline_config,
    load_settings,
)

VALID_YAML = {
    "chunking": {
        "tokenizer": "tiktoken",
        "encoding": "cl100k_base",
        "chunk_size_tokens": 800,
        "chunk_overlap_tokens": 150,
    },
    "retrieval": {"top_k": 8, "max_context_chunks": 5},
    "grounding": {"tau_min": 0.35, "tau_support": 0.30},
    "calibration": {"status": "uncalibrated"},
}


def write_yaml(tmp_path, data):
    path = tmp_path / "retrieval.yaml"
    path.write_text(yaml.safe_dump(data), encoding="utf-8")
    return path


# ------------------------------------------------------------ retrieval.yaml


def test_committed_config_matches_the_documented_decisions():
    """The real config/retrieval.yaml must carry the values the docs specify."""
    config = load_pipeline_config()

    assert config.chunking.tokenizer == "tiktoken"
    assert config.chunking.encoding == "cl100k_base"
    assert config.chunking.chunk_size_tokens == 800
    assert config.chunking.chunk_overlap_tokens == 150
    assert config.retrieval.top_k == 8
    assert config.retrieval.max_context_chunks == 5
    assert config.grounding.tau_min == 0.35
    assert config.grounding.tau_support == 0.30


def test_committed_config_declares_thresholds_uncalibrated():
    """Guards against presenting guessed thresholds as measured ones."""
    assert load_pipeline_config().calibration.status == "uncalibrated"


def test_config_file_is_committed():
    assert RETRIEVAL_CONFIG_PATH.is_file()


def test_overlap_at_or_above_chunk_size_is_rejected(tmp_path):
    data = {**VALID_YAML, "chunking": {**VALID_YAML["chunking"], "chunk_overlap_tokens": 800}}
    with pytest.raises(ConfigurationError, match="chunk_overlap_tokens"):
        load_pipeline_config(write_yaml(tmp_path, data))


def test_context_chunks_above_top_k_is_rejected(tmp_path):
    data = {**VALID_YAML, "retrieval": {"top_k": 4, "max_context_chunks": 5}}
    with pytest.raises(ConfigurationError, match="max_context_chunks"):
        load_pipeline_config(write_yaml(tmp_path, data))


def test_support_threshold_above_min_threshold_is_rejected(tmp_path):
    data = {**VALID_YAML, "grounding": {"tau_min": 0.30, "tau_support": 0.40}}
    with pytest.raises(ConfigurationError, match="tau_support"):
        load_pipeline_config(write_yaml(tmp_path, data))


def test_missing_config_file_is_reported(tmp_path):
    with pytest.raises(ConfigurationError, match="not found"):
        load_pipeline_config(tmp_path / "absent.yaml")


def test_malformed_yaml_is_reported(tmp_path):
    path = tmp_path / "retrieval.yaml"
    path.write_text("chunking: [unclosed", encoding="utf-8")
    with pytest.raises(ConfigurationError, match="not valid YAML"):
        load_pipeline_config(path)


def test_missing_section_is_reported(tmp_path):
    data = {k: v for k, v in VALID_YAML.items() if k != "grounding"}
    with pytest.raises(ConfigurationError, match="invalid"):
        load_pipeline_config(write_yaml(tmp_path, data))


# --------------------------------------------------------------------- .env


def test_settings_load_from_environment():
    settings = load_settings()
    assert settings.foundry_endpoint == "https://example-endpoint.invalid"
    assert settings.app_env == "test"


def test_missing_required_variable_fails_fast(monkeypatch):
    # Disable .env so the result does not depend on the developer's machine.
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    monkeypatch.delenv("FOUNDRY_ENDPOINT", raising=False)

    with pytest.raises(ConfigurationError) as exc_info:
        load_settings()

    message = str(exc_info.value)
    assert "FOUNDRY_ENDPOINT" in message
    assert ".env.example" in message


def test_failure_message_names_every_missing_variable(monkeypatch):
    monkeypatch.setitem(Settings.model_config, "env_file", None)
    for name in ("FOUNDRY_ENDPOINT", "SUPABASE_URL", "SUPABASE_ANON_KEY"):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(ConfigurationError) as exc_info:
        load_settings()

    message = str(exc_info.value)
    assert "FOUNDRY_ENDPOINT" in message
    assert "SUPABASE_URL" in message
    assert "SUPABASE_ANON_KEY" in message


def test_foundry_api_key_is_optional_because_entra_auth_is_preferred(monkeypatch):
    monkeypatch.delenv("FOUNDRY_API_KEY", raising=False)
    assert load_settings().foundry_api_key is None


def test_secret_values_never_appear_in_repr_or_str(monkeypatch):
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "super-secret-value")
    monkeypatch.setenv("FOUNDRY_API_KEY", "another-secret-value")
    settings = load_settings()

    for rendering in (repr(settings), str(settings), str(settings.model_dump())):
        assert "super-secret-value" not in rendering
        assert "another-secret-value" not in rendering

    # The value is still reachable deliberately.
    assert settings.supabase_service_role_key.get_secret_value() == "super-secret-value"


def test_wildcard_cors_origin_is_rejected(monkeypatch):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "*")
    with pytest.raises(ConfigurationError, match="CORS_ALLOWED_ORIGINS"):
        load_settings()


def test_cors_origins_parse_into_an_allow_list(monkeypatch):
    monkeypatch.setenv("CORS_ALLOWED_ORIGINS", "http://localhost:5173, https://app.example.com")
    assert load_settings().cors_origins == ["http://localhost:5173", "https://app.example.com"]
