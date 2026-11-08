"""Runtime settings loaded from environment / .env files."""
from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", ".env.local", "../../.env", "../../.env.local"),
        extra="ignore",
    )

    anthropic_api_key: str = ""
    adaption_api_key: str = ""
    adaption_base_url: str = "https://api.prod.adaptionlabs.ai"
    stentor_renderer: Literal["adaption", "llm"] = "llm"
    stentor_model_id: str = ""
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
