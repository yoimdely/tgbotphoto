"""Command handlers for the Telegram bot."""

from __future__ import annotations

import logging
import re
from datetime import date
from io import BytesIO
from typing import Iterable, List

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder
from PIL import Image

from services import payments, scraper
from services.image_processing import process_batch, remove_watermark, resize_if_needed
from utils.ratelimit import create_default_limiter
from utils.state import state_storage

logger = logging.getLogger(__name__)

router = Router()
rate_limiter = create_default_limiter()
MEDIA_BATCH_SIZE = 10


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    """Welcome message."""
    await message.answer(
        "Привет! 👋\n"
        "Я помогаю чистить фото объявлений с Авито, Циана и Домклик от водяных знаков, улучшать качество и отзеркаливать изображения.\n\n"
        "Просто пришли мне ссылку на объявление, а я верну тебе фотографии без водяных знаков и описание объекта."
    )


@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    """Detailed help."""
    await message.answer(
        "Отправь ссылку на объявление Avito/Циан/Домклик.\n"
        "Я скачаю фото, уберу водяные знаки и пришлю тебе чистые изображения.\n"
        "Кнопки под ответом помогут улучшить качество, отзеркалить или скачать архивом."
    )


@router.message(Command("tariffs", "pricing"))
async def cmd_tariffs(message: Message) -> None:
    """Show tariffs stub."""
    await message.answer("Тарифы:\nFree — 5 ссылок в день.\nPro — 100 ссылок в день. Платежи пока недоступны, но скоро будут!")


@router.message(Command("profile"))
async def cmd_profile(message: Message) -> None:
    """Return user's profile info."""
    user_id = message.from_user.id
    tariff = await payments.get_user_tariff(user_id)
    usage = await payments.get_usage(user_id)
    today_count = usage.daily.get(date.today(), 0)
    state = await state_storage.get_state(user_id)
    await message.answer(
        f"Ваш тариф: {tariff}.\n"
        f"Сегодня обработано: {today_count}. Всего: {usage.total}.\n"
        f"Последняя площадка: {state.platform or '—'}.\n"
        f"Последний URL: {state.last_url or '—'}.",
    )


@router.message(Command("history"))
async def cmd_history(message: Message) -> None:
    """Show last processed listings with ability to re-run."""
    user_id = message.from_user.id
    history = await state_storage.get_history(user_id)
    if not history:
        await message.answer("История пуста. Отправьте ссылку, чтобы начать.")
        return
    builder = InlineKeyboardBuilder()
    lines: list[str] = []
    for idx, item in enumerate(history):
        label = f"{item.processed_at:%d.%m %H:%M} — {item.platform}: {item.title[:40]}"
        lines.append(label)
        builder.button(text=f"Повторить #{idx + 1}", callback_data=f"history:{idx}")
    builder.adjust(1)
    await message.answer("Последние объявления:\n" + "\n".join(lines), reply_markup=builder.as_markup())


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    """Simple admin statistics."""
    if message.from_user.id not in message.bot["admin_ids"]:
        await message.answer("Команда доступна только администраторам.")
        return
    storage = message.bot["state_storage"]
    states = storage._storage.values()  # type: ignore[attr-defined]
    total_users = len(states)
    total_requests = sum(len(state.history) for state in states)
    platform_stats: dict[str, int] = {}
    for state in states:
        if state.platform:
            platform_stats[state.platform] = platform_stats.get(state.platform, 0) + 1
    lines = [f"Пользователей: {total_users}", f"Всего запросов: {total_requests}"]
    for platform, count in platform_stats.items():
        lines.append(f"{platform}: {count}")
    await message.answer("\n".join(lines))


@router.message()
async def handle_link(message: Message) -> None:
    """Main handler for incoming links."""
    if not message.text:
        await message.answer("Пришлите ссылку на объявление Avito/Циан/Домклик.")
        return

    url = message.text.strip()
    if not _looks_like_url(url):
        await message.answer("Это не похоже на ссылку. Пришлите ссылку на объявление.")
        return

    user_id = message.from_user.id
    logger.info("Получено сообщение для обработки от пользователя %s", user_id)

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

    await _process_listing(message, user_id, url)


async def _process_listing(message: Message, user_id: int, url: str) -> None:
    """Parse listing, clean images and send them back to user."""
    logger.info("Старт обработки ссылки %s для пользователя %s", url, user_id)
    await message.answer("🔄 Обрабатываю ссылку, подождите пару секунд...")

    try:
        listing = await scraper.parse_listing(url)
    except scraper.ListingParseError as exc:
        await message.answer(str(exc))
        return
    except Exception:  # noqa: BLE001
        logger.exception("Ошибка парсинга ссылки")
        await message.answer(
            "Не удалось получить фотографии с этой ссылки. Попробуйте другое объявление или другую площадку."
        )
        return

    images: List[Image.Image] = []
    for content in listing.images:
        try:
            img = Image.open(BytesIO(content)).convert("RGB")
            images.append(img)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Не удалось открыть изображение: %s", exc)

    if not images:
        await message.answer("Не удалось обработать изображения. Попробуйте другую ссылку.")
        return

    cleaned_images = await process_batch(images, remove_watermark)
    await payments.register_successful_request(user_id)
    await state_storage.update_last_result(
        user_id,
        cleaned_images,
        listing.description,
        listing.title,
        url,
        listing.platform,
    )

    await _send_media_groups(message, cleaned_images, first_caption=listing.title)
    await message.answer(listing.description or "Описание недоступно", reply_markup=_action_keyboard())
    logger.info("Успешно отправлено %s изображений для пользователя %s", len(cleaned_images), user_id)


def _action_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Повысить качество фото", callback_data="enhance")],
            [InlineKeyboardButton(text="Отзеркалить фото", callback_data="mirror")],
            [InlineKeyboardButton(text="Скачать архивом (ZIP)", callback_data="zip")],
        ]
    )


def _looks_like_url(text: str) -> bool:
    return bool(re.match(r"https?://", text))


def _prepare_media_group(images: Iterable[Image.Image], caption: str | None = None) -> List[List[InputMediaPhoto]]:
    media_groups: List[List[InputMediaPhoto]] = []
    batch: List[InputMediaPhoto] = []
    for idx, image in enumerate(images):
        if len(batch) >= MEDIA_BATCH_SIZE:
            media_groups.append(batch)
            batch = []
        batch.append(InputMediaPhoto(media=_image_to_input_file(image), caption=caption if idx == 0 else None))
    if batch:
        media_groups.append(batch)
    return media_groups


async def _send_media_groups(message: Message, images: List[Image.Image], first_caption: str | None = None) -> None:
    media_groups = _prepare_media_group(images, caption=first_caption)
    for group in media_groups:
        await message.answer_media_group(group)


def _image_to_input_file(image: Image.Image) -> BytesIO:
    resized = resize_if_needed(image)
    bio = BytesIO()
    resized.save(bio, format="JPEG", quality=95, subsampling=0, optimize=True)
    bio.seek(0)
    return bio


__all__ = [
    "router",
    "_process_listing",
]
