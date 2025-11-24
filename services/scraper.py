"""Парсеры объявлений для Avito, Циан и Домклик."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from typing import Iterable, List

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


USER_AGENT = "Mozilla/5.0 (compatible; TelegramBot/1.0; +https://example.com/bot)"
MAX_IMAGES = 20


class ListingParseError(ValueError):
    """Исключение, сигнализирующее о неудачной загрузке объявления."""


@dataclass
class ListingData:
    """Данные объявления."""

    title: str
    description: str
    images: List[bytes]
    platform: str


async def fetch_html(url: str) -> str:
    """Загружает HTML страницы объявления."""
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=20) as client:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        return response.text


async def download_image(url: str) -> bytes:
    """Скачивает изображение по ссылке."""
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=20) as client:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        return response.content


async def parse_listing(url: str) -> ListingData:
    """Определяет площадку и вызывает соответствующий парсер."""
    url = url.strip()
    logger.info("Получена ссылка от пользователя: %s", url)

    try:
        if "avito.ru" in url:
            return await parse_avito(url)
        if "cian.ru" in url:
            return await parse_cian(url)
        if "domclick.ru" in url:
            return await parse_domclick(url)
    except httpx.HTTPError as exc:
        logger.exception("Ошибка сети при парсинге ссылки")
        raise ListingParseError("Сайт недоступен. Попробуйте позже.") from exc
    except asyncio.TimeoutError as exc:
        logger.exception("Таймаут при парсинге ссылки")
        raise ListingParseError("Превышено время ожидания ответа сайта.") from exc
    except ListingParseError:
        raise
    except Exception as exc:  # noqa: BLE001
        logger.exception("Не удалось обработать объявление")
        raise ListingParseError("Не удалось получить данные объявления.") from exc

    raise ListingParseError("Неизвестная площадка. Поддерживаются Avito, Циан и Домклик.")


async def parse_avito(url: str) -> ListingData:
    """Парсинг объявлений Avito."""
    html = await fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")

    title = _extract_title(soup)
    description = _extract_description(soup)
    images = await _download_images(_collect_avito_images(html, soup))

    return ListingData(title=title, description=description, images=images, platform="Avito")


async def parse_cian(url: str) -> ListingData:
    """Парсинг объявлений Циан."""
    html = await fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")

    title = _extract_title(soup)
    description = _extract_description(soup)
    images = await _download_images(_collect_cian_images(html, soup))

    return ListingData(title=title, description=description, images=images, platform="Циан")


async def parse_domclick(url: str) -> ListingData:
    """Парсинг объявлений Домклик."""
    html = await fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")

    title = _extract_title(soup)
    description = _extract_description(soup)
    images = await _download_images(_collect_domclick_images(html, soup))

    return ListingData(title=title, description=description, images=images, platform="Домклик")


def _extract_title(soup: BeautifulSoup) -> str:
    for tag in [
        soup.find("meta", property="og:title"),
        soup.find("meta", attrs={"name": "title"}),
        soup.title,
    ]:
        if tag and (content := tag.get("content") or tag.text):
            return content.strip()
    return "Объявление"


def _extract_description(soup: BeautifulSoup) -> str:
    for tag in [
        soup.find("meta", property="og:description"),
        soup.find("meta", attrs={"name": "description"}),
    ]:
        if tag and tag.get("content"):
            return tag["content"].strip()
    return "Описание недоступно"


def _collect_avito_images(html: str, soup: BeautifulSoup) -> List[str]:
    matches = re.findall(r"https?://[^\s'\"]*?(?:avito\.st|images\.avito|static-\d+\.avito).*?(?:jpg|jpeg|png)", html)
    meta_images = [tag["content"] for tag in soup.find_all("meta", property="og:image") if tag.get("content")]
    return _cleanup_images(matches + meta_images)


def _collect_cian_images(html: str, soup: BeautifulSoup) -> List[str]:
    matches = re.findall(r"https?://[^\s'\"]*?(?:cdn-?cian|cian\.cdn).*?(?:jpg|jpeg|png)", html)
    picture_sources = [tag.get("srcset") or tag.get("src") for tag in soup.select("picture source, img")]
    json_images: list[str] = []
    for script in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(script.text)
            if isinstance(data, dict) and "image" in data:
                images = data.get("image")
                if isinstance(images, list):
                    json_images.extend([img for img in images if isinstance(img, str)])
                elif isinstance(images, str):
                    json_images.append(images)
        except json.JSONDecodeError:
            continue
    return _cleanup_images(matches + picture_sources + json_images)


def _collect_domclick_images(html: str, soup: BeautifulSoup) -> List[str]:
    matches = re.findall(r"https?://[^\s'\"]*?(?:domclick|static\.dc|cdn\.domclick).*?(?:jpg|jpeg|png)", html)
    data_attrs = [tag.get("src") for tag in soup.select("img[data-test='gallery-image'], img")]  # broader selection
    return _cleanup_images(matches + data_attrs)


def _cleanup_images(urls: Iterable[str | None]) -> List[str]:
    cleaned = []
    for url in urls:
        if not url:
            continue
        normalized = url.split("?")[0]
        if normalized.startswith("http") and normalized not in cleaned:
            cleaned.append(normalized)
        if len(cleaned) >= MAX_IMAGES:
            break
    if not cleaned:
        raise ListingParseError(
            "Не удалось получить фотографии с этой ссылки. Попробуйте другое объявление или другую площадку."
        )
    return cleaned


async def _download_images(urls: Iterable[str]) -> List[bytes]:
    tasks = [download_image(url) for url in urls]
    results: list[bytes] = []
    responses = await asyncio.gather(*tasks, return_exceptions=True)
    for idx, resp in enumerate(responses):
        if isinstance(resp, Exception):
            logger.warning("Ошибка загрузки изображения #%s: %s", idx + 1, resp)
            continue
        results.append(resp)
    if not results:
        raise ListingParseError(
            "Не удалось скачать изображения с объявления. Попробуйте позже или другую ссылку."
        )
    return results
