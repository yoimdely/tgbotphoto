import os
from pydantic import BaseSettings, Field
from typing import List


class Settings(BaseSettings):
    """Настройки приложения, загружаемые из переменных окружения."""

    bot_token: str = Field(..., env="BOT_TOKEN")
    admin_ids: List[int] = Field(default_factory=list, env="ADMIN_IDS")

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


def _parse_admin_ids(raw: List[int]) -> List[int]:
    """Преобразует строковый список ID в числовой."""
    parsed = []
    for value in raw:
        if isinstance(value, int):
            parsed.append(value)
            continue
        try:
            parsed.append(int(value))
        except (TypeError, ValueError):
            continue
    return parsed


settings = Settings()
settings.admin_ids = _parse_admin_ids(settings.admin_ids)
