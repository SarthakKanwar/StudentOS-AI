"""Configuration loading.

Two sources, kept deliberately separate (ADR-012):
  - config/retrieval.yaml  version-controlled tuning that changes what answer
                           the system produces; must be reproducible from a
                           git checkout
  - .env                   secrets and deployment-specific values; gitignored
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, SecretStr, ValidationError, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[1]
RETRIEVAL_CONFIG_PATH = REPO_ROOT / "config" / "retrieval.yaml"


class ConfigurationError(RuntimeError):
    """Raised when configuration is missing or invalid. Never carries values."""


# ---------------------------------------------------------------- retrieval.yaml


class ChunkingConfig(BaseModel):
    tokenizer: str
    encoding: str
    chunk_size_tokens: int
    chunk_overlap_tokens: int

    @model_validator(mode="after")
    def overlap_fits_inside_chunk(self) -> ChunkingConfig:
        if self.chunk_overlap_tokens >= self.chunk_size_tokens:
            raise ValueError(
                "chunk_overlap_tokens must be smaller than chunk_size_tokens; "
                "an overlap at or above the chunk size cannot advance through a document"
            )
        return self


class RetrievalConfig(BaseModel):
    top_k: int
    max_context_chunks: int

    # Hybrid retrieval. Dense cosine alone under-ranks rare literal tokens
    # (course codes, regulation numbers, table values), so a keyword ranking is
    # fused with it. See config/retrieval.yaml for why rrf_k is not the usual 60.
    hybrid_enabled: bool = True
    rrf_k: int = 5
    keyword_candidates: int = 25

    @model_validator(mode="after")
    def context_fits_inside_retrieved_set(self) -> RetrievalConfig:
        if self.max_context_chunks > self.top_k:
            raise ValueError("max_context_chunks cannot exceed top_k; only retrieved chunks can be sent to the model")
        return self


class GroundingConfig(BaseModel):
    tau_min: float
    tau_support: float

    @model_validator(mode="after")
    def support_threshold_is_the_looser_one(self) -> GroundingConfig:
        if self.tau_support > self.tau_min:
            raise ValueError(
                "tau_support must not exceed tau_min; supporting evidence is a looser bar than the best-chunk gate"
            )
        return self


class CalibrationConfig(BaseModel):
    status: str
    calibrated_on: str | None = None
    corpus: str | None = None
    embedding_model: str | None = None
    notes: str | None = None


class PipelineConfig(BaseModel):
    chunking: ChunkingConfig
    retrieval: RetrievalConfig
    grounding: GroundingConfig
    calibration: CalibrationConfig


def load_pipeline_config(path: Path = RETRIEVAL_CONFIG_PATH) -> PipelineConfig:
    if not path.is_file():
        raise ConfigurationError(f"Retrieval configuration not found at {path}")
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ConfigurationError(f"Retrieval configuration at {path} is not valid YAML: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigurationError(f"Retrieval configuration at {path} must be a YAML mapping")
    try:
        return PipelineConfig.model_validate(raw)
    except ValidationError as exc:
        raise ConfigurationError(f"Retrieval configuration at {path} is invalid:\n{exc}") from exc


# ---------------------------------------------------------------------- .env


class Settings(BaseSettings):
    """Secrets and deployment-specific values.

    Secret fields use SecretStr so they cannot be printed by accident: repr and
    str render as '**********', and reading the value requires an explicit
    .get_secret_value() call.
    """

    model_config = SettingsConfigDict(
        env_file=REPO_ROOT / ".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",  # .env also carries VITE_* values for the frontend build
    )

    # Foundry — required. Credentials are preferably Entra-based, so the API
    # key is optional (security.md section 4, rule 3).
    foundry_endpoint: str
    foundry_api_version: str
    foundry_chat_deployment: str
    foundry_embedding_deployment: str
    foundry_api_key: SecretStr | None = None

    # OCR fallback for scanned PDFs. Served by Azure AI Document Intelligence on
    # the same AIServices resource as the chat and embedding deployments, so no
    # separate resource or credential is involved. Set OCR_ENABLED=false to turn
    # the fallback off; scanned PDFs then fail as they did before.
    ocr_enabled: bool = True
    ocr_api_version: str = "2024-11-30"
    ocr_model: str = "prebuilt-read"
    ocr_timeout_seconds: int = 180

    # Supabase — required.
    supabase_url: str
    supabase_anon_key: SecretStr
    supabase_service_role_key: SecretStr

    # Application.
    app_env: str = "development"
    port: int = 8000
    log_level: str = "info"
    cors_allowed_origins: str = "http://localhost:5173"

    # Operational limits (security.md section 5).
    daily_token_budget: int | None = None
    rate_limit_per_minute: int = 20
    rate_limit_per_day: int = 200
    max_upload_size_mb: int = 20
    max_question_length: int = 1000

    @field_validator("cors_allowed_origins")
    @classmethod
    def reject_wildcard_origin(cls, value: str) -> str:
        if "*" in value:
            raise ValueError("CORS_ALLOWED_ORIGINS must be an explicit allow-list; wildcards are not permitted")
        return value

    @property
    def cors_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_allowed_origins.split(",") if origin.strip()]


def _missing_field_names(exc: ValidationError) -> list[str]:
    return sorted(
        str(error["loc"][0]).upper() for error in exc.errors() if error["type"] == "missing" and error.get("loc")
    )


def load_settings() -> Settings:
    try:
        return Settings()
    except ValidationError as exc:
        missing = _missing_field_names(exc)
        if missing:
            raise ConfigurationError(
                "Missing required environment variables: "
                + ", ".join(missing)
                + ". Copy .env.example to .env and fill in your own values."
            ) from exc
        # Only field names and rule text reach the message — never input values,
        # which for a malformed secret would be the secret itself.
        rules = "; ".join(f"{str(e['loc'][0]).upper()}: {e['msg']}" for e in exc.errors() if e.get("loc"))
        raise ConfigurationError(f"Invalid environment configuration: {rules}") from exc


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return load_settings()


@lru_cache(maxsize=1)
def get_pipeline_config() -> PipelineConfig:
    return load_pipeline_config()
