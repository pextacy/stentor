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
    gemini_api_key: str = ""
    # Which LLM provider to use: auto | anthropic | gemini | off.
    # auto prefers Anthropic when its key is set, then Gemini. off keeps the deterministic path.
    stentor_llm: Literal["auto", "anthropic", "gemini", "off"] = "auto"
    # Gemini models. The back parser must be a different model from the renderer.
    stentor_gemini_model: str = "gemini-3.5-flash"
    stentor_gemini_backparse_model: str = "gemini-3.1-flash-lite"
    adaption_api_key: str = ""
    adaption_base_url: str = "https://api.prod.adaptionlabs.ai"
    stentor_renderer: Literal["adaption", "llm"] = "llm"
    stentor_model_id: str = ""
    stentor_tz: str = "UTC"  # time zone used to turn alert times into CAP datetimes
    public_base_url: str = "http://localhost:3000"  # where the public alert page lives (CAP <web>)
    cors_origins: str = "http://localhost:3000,http://127.0.0.1:3000"
    api_public_url: str = "http://localhost:8000"  # where this API is reachable (feed links)
    stentor_operator_token: str = ""  # if set, every write endpoint needs "Authorization: Bearer <token>"
    stentor_rate_limit: int = 120  # write requests per minute per client; 0 turns it off
    stentor_duplicate_minutes: int = 30  # warn when the same text was compiled this recently

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
