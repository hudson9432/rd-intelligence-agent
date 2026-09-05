"""Environment-based application configuration."""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime settings loaded from environment variables or backend/.env."""

    app_env: str = "development"
    log_level: str = "INFO"
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    database_url: str = f"sqlite:///{BACKEND_DIR / 'data' / 'rd_intelligence.db'}"
    database_echo: bool = False

    llm_base_url: str | None = None
    llm_api_key: SecretStr | None = None
    llm_model: str | None = None
    llm_min_request_interval_seconds: float = Field(default=0, ge=0, le=60)
    github_token: SecretStr | None = None

    source_min_request_interval_seconds: float = 3.0
    """Seconds between requests to one research source.

    arXiv asks for roughly three seconds and enforces it by stalling replies
    until they time out. GitHub's unauthenticated search allows ten requests a
    minute, thirty with a token, so it is the tighter limit when no
    `GITHUB_TOKEN` is set.
    """

    llm_request_timeout_seconds: float = Field(default=30.0, gt=0, le=600)
    """Seconds to wait for one provider response.

    Raise it for a slower model, or one that reasons before answering: the
    analysis prompts ask for the largest structured output in the workflow and
    are the first to exceed a short timeout.
    """

    llm_max_output_tokens: int | None = Field(default=None, gt=0, le=32768)
    """Cap on one provider response, or None to accept the provider's own.

    Provider defaults differ and are easy to exceed: the critique prompt can
    ask for a dozen questions at once, which one provider truncated at its
    4096-token default about two thirds of the time.
    """

    mock_llm: bool = True
    mock_external_apis: bool = True
    demo_mode: bool = False

    workflow_max_iterations: int = Field(default=2, ge=0, le=8)
    """How many times the Critic may send the run back for more evidence.

    Each round costs a search, an extraction pass over everything it returns,
    and a full analysis, so this is the single largest lever on how long a run
    takes. Lower it for a live demonstration someone is watching; leave it for
    an analysis someone will act on.
    """

    search_max_results_per_source: int = Field(default=8, ge=1, le=50)
    """How many results to keep from each source, for each query.

    Extraction runs one model call per retrieved source and is over half the
    wall-clock of a full run, so this multiplies out faster than it looks:
    four queries across two sources at eight results is up to 64 sources in a
    single round.
    """

    model_config = SettingsConfigDict(
        env_file=BACKEND_DIR / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )


@lru_cache
def get_settings() -> Settings:
    """Return the process-wide configuration instance."""

    return Settings()
