from __future__ import annotations

import logging
from io import BytesIO
from typing import List

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Message
from PIL import Image

from services import payments, scraper
from services.image_processing import process_batch, remove_watermark
from utils.ratelimit import create_default_limiter
from utils.state import state_storage

logger = logging.getLogger(__name__)

router = Router()
rate_limiter = create_default_limiter()


def _action_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Повысить качество фото", callback_data="enhance")],
            [InlineKeyboardButton(text="Отзеркалить фото", callback_data="mirror")],
            [InlineKeyboardButton(text="Скачать архивом (ZIP)", callback_data="zip")],
        ]
    )


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await message.answer(
        "Привет! 👋\n"
        "Я помогаю чистить фото объявлений с Авито, Циана и Домклик от водяных знаков, улучшать качество и отзеркаливать изображения.\n\n"
        "Просто пришли мне ссылку на объявление, а я верну тебе фотографии без водяных знаков и описание объекта.",
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    await message.answer(
        "Отправь ссылку на объявление Avito/Циан/Домклик.\n"
        "Я скачаю фото, уберу водяные знаки и пришлю тебе чистые изображения.\n"
        "Кнопки под ответом помогут улучшить качество, отзеркалить или скачать архивом."
    )


@router.message(Command("tariffs", "pricing"))
async def cmd_tariffs(message: Message) -> None:
    await message.answer("Тарифы:\nFree — 5 ссылок в день.\nPro — 100 ссылок в день. Платежи пока недоступны, но скоро будут!")


@router.message(Command("profile"))
async def cmd_profile(message: Message) -> None:
    user_id = message.from_user.id
    tariff = await payments.get_user_tariff(user_id)
    state = await state_storage.get_state(user_id)
    await message.answer(
        f"Ваш тариф: {tariff}.\n"
        f"Последняя площадка: {state.platform or '—'}.\n"
        f"Обработано ссылок: {len(state.history)}."
    )


@router.message(Command("history"))
async def cmd_history(message: Message) -> None:
    user_id = message.from_user.id
    history = await state_storage.get_history(user_id)
    if not history:
        await message.answer("История пуста. Отправьте ссылку, чтобы начать.")
        return
    lines: List[str] = []
    for item in history:
        lines.append(
            f"{item.processed_at:%d.%m %H:%M} — {item.platform}: {item.title[:40]}"
        )
    await message.answer("Последние объявления:\n" + "\n".join(lines))


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    if message.from_user.id not in message.bot['admin_ids']:
        await message.answer("Команда доступна только администраторам.")
        return
    total_users = len(message.bot['state_storage']._storage)  # type: ignore[attr-defined]
    total_requests = sum(len(state.history) for state in message.bot['state_storage']._storage.values())  # type: ignore[attr-defined]
    platform_stats = {}
    for state in message.bot['state_storage']._storage.values():  # type: ignore[attr-defined]
        if state.platform:
            platform_stats[state.platform] = platform_stats.get(state.platform, 0) + 1
    lines = [f"Пользователей: {total_users}", f"Всего запросов: {total_requests}"]
    for platform, count in platform_stats.items():
        lines.append(f"{platform}: {count}")
    await message.answer("\n".join(lines))


@router.message()
async def handle_link(message: Message) -> None:
    if not message.text:
        return
    user_id = message.from_user.id

    wait_seconds = await rate_limiter.check(user_id)
    if wait_seconds > 0:
        await message.answer(f"Слишком много запросов, попробуйте через {wait_seconds} секунд.")
        return

    can_process = await payments.can_process_request(user_id)
    if not can_process:
        payment_link = await payments.create_payment_link(user_id, "pro")
        await message.answer(
            "Лимит тарифа Free исчерпан. Оформите Pro, чтобы продолжить: " + payment_link
        )
        return

    await message.answer("🔄 Обрабатываю ссылку, подождите пару секунд...")

    try:
        listing = await scraper.parse_listing(message.text)
    except ValueError as exc:
        await message.answer(str(exc))
        return
    except Exception as exc:  # noqa: BLE001
        logger.exception("Ошибка парсинга ссылки")
        await message.answer(
            "Не удалось получить фотографии с этой ссылки. Попробуйте другое объявление или другую площадку."
        )
        return

    images: List[Image.Image] = []
    for content in listing.images:
        try:
            img = Image.open(BytesIO(content))
            images.append(img)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Не удалось открыть изображение: %s", exc)

    if not images:
        await message.answer(
            "Не удалось обработать изображения. Попробуйте другую ссылку."
        )
        return

    cleaned_images = await process_batch(images, remove_watermark)
    await payments.register_successful_request(user_id)
    await state_storage.update_last_result(
        user_id,
        cleaned_images,
        listing.description,
        listing.title,
        message.text,
        listing.platform,
    )

    media_group = [
        InputMediaPhoto(media=_image_to_bytes_io(img), caption=listing.title if idx == 0 else None)
        for idx, img in enumerate(cleaned_images[:10])
    ]
    await message.answer_media_group(media_group)
    await message.answer(listing.description or "Описание недоступно", reply_markup=_action_keyboard())


def _image_to_bytes_io(image: Image.Image) -> BytesIO:
    bio = BytesIO()
    image.save(bio, format="JPEG", quality=90)
    bio.seek(0)
    return bio
