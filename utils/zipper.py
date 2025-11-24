import io
import zipfile
from typing import Iterable

from PIL import Image


def images_to_zip(images: Iterable[Image.Image]) -> bytes:
    """Упаковывает изображения в zip-архив и возвращает байты."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for idx, image in enumerate(images, start=1):
            img_buffer = io.BytesIO()
            image.save(img_buffer, format="JPEG", quality=90)
            archive.writestr(f"photo_{idx}.jpg", img_buffer.getvalue())
    buffer.seek(0)
    return buffer.getvalue()
