"""Простейшая заглушка эквайринга и тарифов."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import date
from typing import Dict, Tuple

TARIFFS = {
    "free": {"limit_per_day": 5},
    "pro": {"limit_per_day": 100},
}


@dataclass
class UserUsage:
    """Хранение статистики пользователя."""

    daily: Dict[date, int]
    total: int


class PaymentStorage:
    """In-memory хранилище тарифов и счётчиков запросов."""

    def __init__(self) -> None:
        self._counters: Dict[Tuple[int, date], int] = {}
        self._totals: Dict[int, int] = {}
        self._tariffs: Dict[int, str] = {}
        self._lock = asyncio.Lock()

    async def get_user_tariff(self, user_id: int) -> str:
        async with self._lock:
            return self._tariffs.get(user_id, "free")

    async def set_user_tariff(self, user_id: int, tariff_code: str) -> None:
        async with self._lock:
            self._tariffs[user_id] = tariff_code

    async def get_usage(self, user_id: int) -> UserUsage:
        async with self._lock:
            daily_counts: Dict[date, int] = {}
            for (uid, day), count in self._counters.items():
                if uid == user_id:
                    daily_counts[day] = count
            return UserUsage(daily=daily_counts, total=self._totals.get(user_id, 0))

    async def can_process_request(self, user_id: int) -> bool:
        tariff = await self.get_user_tariff(user_id)
        limit = TARIFFS.get(tariff, TARIFFS["free"])['limit_per_day']
        today = date.today()
        async with self._lock:
            count = self._counters.get((user_id, today), 0)
            return count < limit

    async def register_successful_request(self, user_id: int) -> None:
        today = date.today()
        async with self._lock:
            key = (user_id, today)
            self._counters[key] = self._counters.get(key, 0) + 1
            self._totals[user_id] = self._totals.get(user_id, 0) + 1

    async def create_payment_link(self, user_id: int, tariff_code: str) -> str:
        """Возвращает заглушку ссылки на оплату."""
        await asyncio.sleep(0)  # сохранить асинхронный интерфейс
        return f"https://example.com/pay?user={user_id}&plan={tariff_code}"


storage = PaymentStorage()


async def get_user_tariff(user_id: int) -> str:
    return await storage.get_user_tariff(user_id)


async def can_process_request(user_id: int) -> bool:
    return await storage.can_process_request(user_id)


async def register_successful_request(user_id: int) -> None:
    await storage.register_successful_request(user_id)


async def create_payment_link(user_id: int, tariff_code: str) -> str:
    return await storage.create_payment_link(user_id, tariff_code)


async def get_usage(user_id: int) -> UserUsage:
    """Возвращает статистику запросов пользователя."""
    return await storage.get_usage(user_id)
