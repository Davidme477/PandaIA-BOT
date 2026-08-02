from __future__ import annotations

import re
import time
from threading import Lock
from pathlib import Path
from urllib.parse import urlparse
from urllib.request import Request, urlopen


from core.app_paths import get_paths

GIFT_CACHE_DIR = get_paths().cache / "gifts"

MAX_IMAGE_SIZE = 10 * 1024 * 1024
ALLOWED_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".webp",
    ".gif",
}

MAX_CACHE_BYTES = 200 * 1024 * 1024
MAX_CACHE_AGE_SECONDS = 30 * 24 * 60 * 60
_cache_lock = Lock()
_last_prune = 0.0


def prune_gift_cache(*, now: float | None = None) -> int:
    """Limita solo cache/gifts, como máximo una vez cada seis horas por proceso."""
    global _last_prune
    current = time.time() if now is None else now
    with _cache_lock:
        if current - _last_prune < 6 * 60 * 60 or not GIFT_CACHE_DIR.is_dir():
            return 0
        _last_prune = current
        files = [item for item in GIFT_CACHE_DIR.iterdir() if item.is_file() and item.suffix.lower() in ALLOWED_EXTENSIONS]
        removed = 0
        for item in list(files):
            try:
                if current - item.stat().st_mtime > MAX_CACHE_AGE_SECONDS:
                    item.unlink(); files.remove(item); removed += 1
            except OSError:
                continue
        sized = []
        for item in files:
            try: sized.append((item.stat().st_mtime, item.stat().st_size, item))
            except OSError: continue
        total = sum(size for _modified, size, _item in sized)
        for _modified, size, item in sorted(sized):
            if total <= MAX_CACHE_BYTES: break
            try: item.unlink(); total -= size; removed += 1
            except OSError: continue
        return removed


def clean_gift_id(gift_id: str | int) -> str:
    """
    Convierte el ID del regalo en un nombre de archivo seguro.
    """
    safe_id = re.sub(
        r"[^a-zA-Z0-9_-]",
        "",
        str(gift_id).strip(),
    )

    return safe_id or "unknown-gift"


def detect_extension(
    image_url: str,
    content_type: str,
) -> str:
    """
    Detecta el formato real de la imagen.
    """
    normalized_type = content_type.lower()

    if "png" in normalized_type:
        return ".png"

    if "webp" in normalized_type:
        return ".webp"

    if "jpeg" in normalized_type or "jpg" in normalized_type:
        return ".jpg"

    if "gif" in normalized_type:
        return ".gif"

    url_extension = Path(
        urlparse(image_url).path
    ).suffix.lower()

    if url_extension in ALLOWED_EXTENSIONS:
        return url_extension

    return ".png"


def find_cached_gift(
    gift_id: str | int,
) -> Path | None:
    """
    Busca una imagen del regalo que ya esté guardada.
    """
    safe_id = clean_gift_id(gift_id)

    for extension in ALLOWED_EXTENSIONS:
        image_path = GIFT_CACHE_DIR / (
            f"{safe_id}{extension}"
        )

        if image_path.is_file():
            return image_path

    return None


def download_gift_image(
    *,
    gift_id: str | int,
    image_url: str,
) -> Path | None:
    """
    Descarga la imagen oficial del regalo.

    Si ya existe en caché, devuelve el archivo existente.
    """
    safe_url = str(image_url).strip()

    if not safe_url:
        print(
            "[GiftImageService] No se recibió una URL."
        )
        return None

    GIFT_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    prune_gift_cache()

    cached_image = find_cached_gift(gift_id)

    if cached_image is not None:
        print(
            "[GiftImageService] Imagen encontrada en caché:",
            cached_image,
        )
        return cached_image

    try:
        image_request = Request(
            safe_url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "PandaIA-BOT/1.0"
                ),
                "Accept": (
                    "image/avif,image/webp,image/apng,"
                    "image/svg+xml,image/*,*/*;q=0.8"
                ),
            },
        )

        with urlopen(
            image_request,
            timeout=15,
        ) as response:
            content_type = response.headers.get(
                "Content-Type",
                "",
            )

            if not content_type.lower().startswith(
                "image/"
            ):
                print(
                    "[GiftImageService] "
                    "La dirección recibida no contiene "
                    "una imagen válida."
                )
                return None

            image_data = response.read(
                MAX_IMAGE_SIZE + 1
            )

        if len(image_data) > MAX_IMAGE_SIZE:
            print(
                "[GiftImageService] "
                "La imagen supera el límite de 10 MB."
            )
            return None

        extension = detect_extension(
            safe_url,
            content_type,
        )

        safe_id = clean_gift_id(gift_id)

        destination = GIFT_CACHE_DIR / (
            f"{safe_id}{extension}"
        )

        temporary_file = destination.with_suffix(
            f"{destination.suffix}.tmp"
        )

        temporary_file.write_bytes(image_data)
        temporary_file.replace(destination)

        print(
            "[GiftImageService] Imagen guardada:",
            destination,
        )

        return destination

    except Exception as error:
        print(
            "[GiftImageService] "
            "No se pudo descargar la imagen:",
            error,
        )
        return None


def get_gift_image(
    *,
    gift_id: str | int,
    image_url: str = "",
) -> Path | None:
    """
    Devuelve la imagen guardada o intenta descargarla.
    """
    cached_image = find_cached_gift(gift_id)

    if cached_image is not None:
        return cached_image

    if not image_url:
        return None

    return download_gift_image(
        gift_id=gift_id,
        image_url=image_url,
    )


def get_overlay_image_url(
    image_path: Path | None,
) -> str:
    """
    Genera la ruta que posteriormente utilizará el overlay.
    """
    if image_path is None:
        return ""

    return f"/gift-assets/{image_path.name}"
