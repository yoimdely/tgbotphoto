from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from PIL import Image


@dataclass
class UserHistoryItem:
    platform: str
    title: str
    processed_at: datetime
    url: str


@dataclass
class UserState:
    last_images: List[Image.Image] = field(default_factory=list)
    last_description: str = ""
    last_title: str = ""
    last_url: str = ""
    platform: str = ""
    history: List[UserHistoryItem] = field(default_factory=list)


class StateStorage:
    """Память состояний пользователей в оперативной памяти."""

    def __init__(self) -> None:
        self._storage: Dict[int, UserState] = {}
        self._lock = asyncio.Lock()

    async def get_state(self, user_id: int) -> UserState:
        async with self._lock:
            return self._storage.setdefault(user_id, UserState())

    async def update_last_result(
        self,
        user_id: int,
        images: List[Image.Image],
        description: str,
        title: str,
        url: str,
        platform: str,
    ) -> None:
        async with self._lock:
            state = self._storage.setdefault(user_id, UserState())
            state.last_images = images
            state.last_description = description
            state.last_title = title
            state.last_url = url
            state.platform = platform
            state.history.insert(
                0,
                UserHistoryItem(
                    platform=platform,
                    title=title,
                    processed_at=datetime.utcnow(),
                    url=url,
                ),
            )
            state.history = state.history[:10]

    async def get_history(self, user_id: int) -> List[UserHistoryItem]:
        state = await self.get_state(user_id)
        return state.history

    async def get_last_images(self, user_id: int) -> List[Image.Image]:
        state = await self.get_state(user_id)
        return state.last_images

    async def get_last_description(self, user_id: int) -> str:
        state = await self.get_state(user_id)
        return state.last_description

    async def get_last_title(self, user_id: int) -> str:
        state = await self.get_state(user_id)
        return state.last_title

    async def get_platform(self, user_id: int) -> str:
        state = await self.get_state(user_id)
        return state.platform

    async def get_last_url(self, user_id: int) -> str:
        state = await self.get_state(user_id)
        return state.last_url


state_storage = StateStorage()
