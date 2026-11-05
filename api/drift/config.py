import os
from dataclasses import dataclass, field
from pathlib import Path

DATA_DIR = Path(os.getenv("DRIFT_DATA_DIR", Path(__file__).resolve().parent.parent / "data"))


@dataclass(frozen=True)
class Settings:
    db_path: str = str(DATA_DIR / "drift.db")
    catalog_path: str = str(DATA_DIR / "catalog.db")
    secret: str = os.getenv("DRIFT_SECRET", "drift-dev-secret")
    poll_seconds: int = int(os.getenv("DRIFT_POLL_SECONDS", "30"))

    # TriggerWare: set TRIGGERWARE_ADDRESS (host:port, local Docker) or
    # TRIGGERWARE_URL + TRIGGERWARE_API_KEY (cloud). Unset means built-in local engine.
    tw_address: str | None = os.getenv("TRIGGERWARE_ADDRESS")
    tw_url: str | None = os.getenv("TRIGGERWARE_URL")
    tw_api_key: str | None = os.getenv("TRIGGERWARE_API_KEY")
    tw_schedule: str = os.getenv("TRIGGERWARE_SCHEDULE", "*/1 * * * *")
    tw_table: str = os.getenv("TRIGGERWARE_TABLE", "service_catalog")
    tw_deps_table: str = os.getenv("TRIGGERWARE_DEPS_TABLE", "service_dependencies")

    anthropic_key: str | None = os.getenv("ANTHROPIC_API_KEY")
    anthropic_model: str = os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-5")
    openai_key: str | None = os.getenv("OPENAI_API_KEY")
    openai_model: str = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
    openai_embed_model: str = os.getenv("OPENAI_EMBED_MODEL", "text-embedding-3-small")

    cors_origins: list[str] = field(
        default_factory=lambda: os.getenv("DRIFT_CORS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
    )

    @property
    def llm_provider(self) -> str | None:
        if self.anthropic_key:
            return "anthropic"
        if self.openai_key:
            return "openai"
        return None


settings = Settings()
DATA_DIR.mkdir(parents=True, exist_ok=True)
