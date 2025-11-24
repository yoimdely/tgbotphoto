from __future__ import annotations

import asyncio
from io import BytesIO

from aiogram import F, Router
from aiogram.types import CallbackQuery, FSInputFile, InputMediaPhoto

from services.image_processing import enhance_image, mirror_image, process_batch
from utils.state import state_storage
from utils.zipper import images_to_zip
from .commands import _image_to_bytes_io

router = Router()


@router.callback_query(F.data == "enhance")
async def cb_enhance(call: CallbackQuery) -> None:
    await call.answer()
    user_id = call.from_user.id
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
    media_group = [
        InputMediaPhoto(media=_image_to_bytes_io(img), caption="Фото улучшены ✅" if idx == 0 else None)
        for idx, img in enumerate(enhanced[:10])
    ]
    await call.message.answer_media_group(media_group)


@router.callback_query(F.data == "mirror")
async def cb_mirror(call: CallbackQuery) -> None:
    await call.answer()
    user_id = call.from_user.id
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
    media_group = [
        InputMediaPhoto(media=_image_to_bytes_io(img), caption="Фото отзеркалены 🔁" if idx == 0 else None)
        for idx, img in enumerate(mirrored[:10])
    ]
    await call.message.answer_media_group(media_group)


@router.callback_query(F.data == "zip")
async def cb_zip(call: CallbackQuery) -> None:
    await call.answer()
    user_id = call.from_user.id
    images = await state_storage.get_last_images(user_id)
    if not images:
        await call.message.answer("Нет изображений для архива.")
        return
    zip_bytes = await asyncio.to_thread(images_to_zip, images)
    buffer = BytesIO(zip_bytes)
    await call.message.answer_document(FSInputFile(buffer, filename="photos.zip"))
