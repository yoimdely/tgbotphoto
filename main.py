"""Entry point for the Telegram bot."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from config import settings
from handlers import callbacks, commands
from utils.state import state_storage

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger(__name__)


def register_middlewares(dp: Dispatcher) -> None:
    """Register custom middlewares if needed."""
    return None


def register_routers(dp: Dispatcher) -> None:
    """Register all routers."""
    dp.include_router(commands.router)
    dp.include_router(callbacks.router)


class CustomBot(Bot):
    """Bot with lightweight context storage accessible via item syntax."""

    __slots__ = ("_context",)

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._context: dict[str, Any] = {}

    def __getitem__(self, key: str) -> Any:
        return self._context[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._context[key] = value

    def get(self, key: str, default: Any | None = None) -> Any:
        return self._context.get(key, default)


async def main() -> None:
    """Create bot instance and start polling."""
    bot = CustomBot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()

    bot["admin_ids"] = settings.admin_ids
    bot["state_storage"] = state_storage

    register_middlewares(dp)
    register_routers(dp)

    logger.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
