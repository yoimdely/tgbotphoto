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
    # Здесь можно добавить middleware для логирования/лимитов.
    return None


def register_routers(dp: Dispatcher) -> None:
    dp.include_router(commands.router)
    dp.include_router(callbacks.router)


async def main() -> None:
    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    bot["admin_ids"] = settings.admin_ids
    bot["state_storage"] = state_storage

    register_middlewares(dp)
    register_routers(dp)

    logger.info("Бот запущен")
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
