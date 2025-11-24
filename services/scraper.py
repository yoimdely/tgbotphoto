from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from typing import Callable, List

import httpx
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)


@dataclass
class ListingData:
    title: str
    description: str
    images: List[bytes]
    platform: str


USER_AGENT = "Mozilla/5.0 (compatible; TelegramBot/1.0; +https://example.com/bot)"


async def fetch_html(url: str) -> str:
    """Загружает HTML страницы объявления."""
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=20) as client:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        return response.text


async def download_image(url: str) -> bytes:
    async with httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=20) as client:
        response = await client.get(url, follow_redirects=True)
        response.raise_for_status()
        return response.content


async def parse_listing(url: str) -> ListingData:
    """Определяет площадку и вызывает соответствующий парсер."""
    url = url.strip()
    if "avito.ru" in url:
        return await parse_avito(url)
    if "cian.ru" in url:
        return await parse_cian(url)
    if "domclick.ru" in url:
        return await parse_domclick(url)
    raise ValueError("Неизвестная площадка. Поддерживаются Avito, Циан и Домклик.")


async def _generic_parser(url: str, image_selectors: List[str], title_selector: str | None = None) -> ListingData:
    html = await fetch_html(url)
    soup = BeautifulSoup(html, "html.parser")

    title = soup.title.string.strip() if soup.title else "Объявление"
    if title_selector:
        found_title = soup.select_one(title_selector)
        if found_title and found_title.text:
            title = found_title.text.strip()

    description = ""
    description_candidates = [
        soup.find("meta", attrs={"name": "description"}),
        soup.find("meta", attrs={"property": "og:description"}),
    ]
    for candidate in description_candidates:
        if candidate and candidate.get("content"):
            description = candidate["content"].strip()
            break

    image_urls: List[str] = []
    for selector in image_selectors:
        for tag in soup.select(selector):
            if tag.get("content"):
                image_urls.append(tag["content"])
            elif tag.get("src"):
                image_urls.append(tag["src"])

    og_image = soup.find("meta", property="og:image")
    if og_image and og_image.get("content"):
        image_urls.append(og_image["content"])

    image_urls = [url for url in image_urls if url.startswith("http")]
    if not image_urls:
        raise RuntimeError("Не удалось получить фотографии с этой ссылки. Попробуйте другое объявление или другую площадку.")

    images: List[bytes] = []
    for img_url in image_urls[:20]:  # ограничиваемся первыми 20 изображениями
        try:
            images.append(await download_image(img_url))
        except Exception as exc:  # noqa: BLE001
            logger.warning("Ошибка загрузки изображения %s: %s", img_url, exc)

    if not images:
        raise RuntimeError("Не удалось скачать изображения с объявления.")

    return ListingData(title=title, description=description, images=images, platform=_detect_platform(url))


def _detect_platform(url: str) -> str:
    if "avito" in url:
        return "Avito"
    if "cian" in url:
        return "Циан"
    if "domclick" in url:
        return "Домклик"
    return "Неизвестно"


async def parse_avito(url: str) -> ListingData:
    # Avito часто кладёт ссылки в meta og:image и data-url в скриптах.
    selectors = ["meta[property='og:image']", "img[itemprop='image']"]
    return await _generic_parser(url, selectors, title_selector="span.title-info-title-text")


async def parse_cian(url: str) -> ListingData:
    # Циан хранит ссылки в meta og:image и теге picture > source.
    selectors = ["meta[property='og:image']", "picture source"]
    return await _generic_parser(url, selectors)


async def parse_domclick(url: str) -> ListingData:
    # Домклик использует meta и data-атрибуты.
    selectors = ["meta[property='og:image']", "img[data-test='gallery-image']"]
    return await _generic_parser(url, selectors)
