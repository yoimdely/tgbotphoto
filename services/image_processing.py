"""Функции обработки изображений."""

from __future__ import annotations

import asyncio
import inspect
import logging
from typing import Callable, Iterable, List

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

try:  # pragma: no cover - опциональная зависимость
    import cv2
except Exception:  # noqa: BLE001
    cv2 = None  # type: ignore

logger = logging.getLogger(__name__)

MAX_SIDE = 2000


async def remove_watermark(image: Image.Image) -> Image.Image:
    """Простейшее удаление водяных знаков через размытие углов или inpaint."""
    return await asyncio.to_thread(_remove_watermark_sync, image)


def _remove_watermark_sync(image: Image.Image) -> Image.Image:
    img = image.convert("RGB")
    if cv2:
        try:
            arr = cv2.cvtColor(np.array(img), cv2.COLOR_RGB2BGR)
            h, w, _ = arr.shape
            mask = np.zeros((h, w), dtype=np.uint8)
            size = max(50, min(h, w) // 6)
            mask[h - size : h, w - size : w] = 255
            mask[0:size, 0:size] = 255
            cleaned = cv2.inpaint(arr, mask, 3, cv2.INPAINT_TELEA)
            return Image.fromarray(cv2.cvtColor(cleaned, cv2.COLOR_BGR2RGB))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Inpaint не удался: %s", exc)
    blurred = img.filter(ImageFilter.GaussianBlur(radius=2))
    return Image.blend(img, blurred, alpha=0.2)


async def enhance_image(image: Image.Image) -> Image.Image:
    """Увеличивает резкость, контраст и яркость."""
    return await asyncio.to_thread(_enhance_image_sync, image)


def _enhance_image_sync(image: Image.Image) -> Image.Image:
    enhanced = image.convert("RGB")
    enhanced = enhanced.filter(ImageFilter.SHARPEN)
    enhanced = ImageEnhance.Contrast(enhanced).enhance(1.12)
    enhanced = ImageEnhance.Brightness(enhanced).enhance(1.06)
    enhanced = enhanced.filter(ImageFilter.SMOOTH)
    return enhanced


async def mirror_image(image: Image.Image) -> Image.Image:
    """Горизонтальное отражение изображения."""
    return await asyncio.to_thread(image.transpose, Image.FLIP_LEFT_RIGHT)


def resize_if_needed(image: Image.Image, max_side: int = MAX_SIDE) -> Image.Image:
    """Слегка уменьшает изображение по длинной стороне, чтобы не перегружать Telegram."""
    width, height = image.size
    longest = max(width, height)
    if longest <= max_side:
        return image
    ratio = max_side / float(longest)
    new_size = (int(width * ratio), int(height * ratio))
    resized = image.copy()
    resized.thumbnail(new_size, Image.Resampling.LANCZOS)
    return resized


async def process_batch(
    images: Iterable[Image.Image], func: Callable[[Image.Image], Image.Image | asyncio.Future]
) -> List[Image.Image]:
    """Применяет функцию к коллекции изображений, поддерживает sync и async функции."""

    tasks: list[asyncio.Future] = []
    is_async = inspect.iscoroutinefunction(func)
    for img in images:
        if is_async:
            tasks.append(asyncio.ensure_future(func(img)))
        else:
            tasks.append(asyncio.to_thread(func, img))
    return [result for result in await asyncio.gather(*tasks)]  # type: ignore[list-item]
