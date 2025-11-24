from __future__ import annotations

import asyncio
import logging
from typing import Iterable, List

import numpy as np
from PIL import Image, ImageEnhance, ImageFilter

try:
    import cv2
except Exception:  # noqa: BLE001
    cv2 = None  # type: ignore

logger = logging.getLogger(__name__)


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
    enhanced = ImageEnhance.Contrast(enhanced).enhance(1.1)
    enhanced = ImageEnhance.Brightness(enhanced).enhance(1.05)
    enhanced = enhanced.filter(ImageFilter.SMOOTH)
    return enhanced


async def mirror_image(image: Image.Image) -> Image.Image:
    """Горизонтальное отражение изображения."""
    return await asyncio.to_thread(image.transpose, Image.FLIP_LEFT_RIGHT)


async def process_batch(images: Iterable[Image.Image], func) -> List[Image.Image]:
    tasks = [func(img) for img in images]
    return await asyncio.gather(*tasks)
