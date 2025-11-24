"""Callback query handlers for inline buttons."""

from __future__ import annotations

import asyncio
import logging

from aiogram import F, Router
from aiogram.types import BufferedInputFile, CallbackQuery

from handlers.commands import _prepare_media_group, _process_listing
from services.archive import images_to_zip
from services.image_processing import enhance_image, mirror_image, process_batch
from services import payments
from utils.state import state_storage

router = Router()
logger = logging.getLogger(__name__)


@router.callback_query(F.data == "enhance")
async def cb_enhance(call: CallbackQuery) -> None:
    """Enhance last images for the user."""
    await call.answer()
    user_id = call.from_user.id
    logger.info("Пользователь %s нажал 'enhance'", user_id)
    images = await state_storage.get_last_images(user_id)
    if not images:
        await call.message.answer("Нет изображений для обработки.")
        return
    enhanced = await process_batch(images, enhance_image)
    await state_storage.update_last_result(
        user_id,
        enhanced,
        await state_storage.get_last_description(user_id),
        await state_storage.get_last_title(user_id),
        await state_storage.get_last_url(user_id),
        await state_storage.get_platform(user_id),
    )
    media_groups = _prepare_media_group(enhanced, caption="Фото улучшены ✅")
    for group in media_groups:
        await call.message.answer_media_group(group)


@router.callback_query(F.data == "mirror")
async def cb_mirror(call: CallbackQuery) -> None:
    """Mirror last images for the user."""
    await call.answer()
    user_id = call.from_user.id
    logger.info("Пользователь %s нажал 'mirror'", user_id)
    images = await state_storage.get_last_images(user_id)
    if not images:
        await call.message.answer("Нет изображений для отражения.")
        return
    mirrored = await process_batch(images, mirror_image)
    await state_storage.update_last_result(
        user_id,
        mirrored,
        await state_storage.get_last_description(user_id),
        await state_storage.get_last_title(user_id),
        await state_storage.get_last_url(user_id),
        await state_storage.get_platform(user_id),
    )
    media_groups = _prepare_media_group(mirrored, caption="Фото отзеркалены 🔁")
    for group in media_groups:
        await call.message.answer_media_group(group)


@router.callback_query(F.data == "zip")
async def cb_zip(call: CallbackQuery) -> None:
    """Send zip archive with last images."""
    await call.answer()
    user_id = call.from_user.id
    logger.info("Пользователь %s запросил ZIP", user_id)
    images = await state_storage.get_last_images(user_id)
    if not images:
        await call.message.answer("Нет изображений для архива.")
        return
    zip_bytes = await asyncio.to_thread(images_to_zip, images)
    buffer = BufferedInputFile(zip_bytes, filename="photos.zip")
    await call.message.answer_document(buffer)


@router.callback_query(F.data.startswith("history:"))
async def cb_history(call: CallbackQuery) -> None:
    """Re-run processing for selected history item."""
    await call.answer()
    user_id = call.from_user.id
    logger.info("Пользователь %s выбрал элемент истории", user_id)
    _, _, idx_str = call.data.partition(":")
    try:
        index = int(idx_str)
    except ValueError:
        await call.message.answer("Некорректный элемент истории.")
        return

    history_item = await state_storage.get_history_item(user_id, index)
    if not history_item:
        await call.message.answer("Элемент истории не найден.")
        return

    can_process = await payments.can_process_request(user_id)
    if not can_process:
        payment_link = await payments.create_payment_link(user_id, "pro")
        await call.message.answer(
            "Лимит тарифа Free исчерпан. Оформите Pro, чтобы продолжить: " + payment_link
        )
        return

    await _process_listing(call.message, user_id, history_item.url)


__all__ = ["router"]
