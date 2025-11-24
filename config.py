"""Application configuration loaded from environment variables."""

from __future__ import annotations

from typing import List

from pydantic import Field, ValidationError, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Settings for the Telegram bot loaded from ``.env`` file."""

    bot_token: str = Field(..., alias="BOT_TOKEN")
    admin_ids: List[int] = Field(default_factory=list, alias="ADMIN_IDS")

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("admin_ids", mode="before")
    @classmethod
    def _parse_admin_ids(cls, raw: str | list[int] | None) -> list[int]:
        """Parse comma-separated or list-based admin ids from env."""
        if raw is None:
            return []
        if isinstance(raw, list):
            return [int(item) for item in raw if isinstance(item, (str, int))]
        values = [part.strip() for part in str(raw).split(",") if part.strip()]
        admin_ids: list[int] = []
        for value in values:
            try:
                admin_ids.append(int(value))
            except ValueError:
                continue
        return admin_ids


def load_settings() -> Settings:
    """Load settings with a friendly error if mandatory variables are missing."""

    try:
        return Settings()
    except ValidationError as exc:  # pragma: no cover - defensive user guidance
        missing_fields = ", ".join(err["loc"][0] for err in exc.errors())
        message = (
            "Не удалось загрузить конфигурацию. "
            "Проверьте, что в .env указаны обязательные переменные: "
            f"{missing_fields}.\n"
            "Создайте файл .env на основе .env.example и задайте BOT_TOKEN."
        )
        raise SystemExit(message) from exc


settings = load_settings()
