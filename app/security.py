from __future__ import annotations

import io
import os
import secrets
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import urlparse

from fastapi import HTTPException, Request
from PIL import Image, UnidentifiedImageError


CSRF_SESSION_KEY = "_csrf_token"
MAX_LOGIN_ATTEMPTS = 5
LOGIN_BLOCK_MINUTES = 15
LOGIN_WINDOW_MINUTES = 15
MAX_PHOTO_BYTES = 5 * 1024 * 1024
MAX_CERTIFICATE_BYTES = 10 * 1024 * 1024
MAX_IMPORT_JSON_BYTES = 2 * 1024 * 1024
ALLOWED_CERTIFICATE_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_SALARY_CURRENCIES = {"rub", "usd", "eur"}


def get_csrf_token(request: Request) -> str:
    token = request.session.get(CSRF_SESSION_KEY)
    if not token:
        token = secrets.token_urlsafe(32)
        request.session[CSRF_SESSION_KEY] = token
    return token


async def enforce_csrf_protection(request: Request) -> None:
    get_csrf_token(request)

    if request.method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return

    base_url = str(request.base_url).rstrip("/")
    origin = request.headers.get("origin")
    referer = request.headers.get("referer")

    if origin and origin.rstrip("/") != base_url:
        raise HTTPException(status_code=403, detail="Forbidden")

    if referer and not referer.startswith(f"{base_url}/") and referer.rstrip("/") != base_url:
        raise HTTPException(status_code=403, detail="Forbidden")

    submitted_token = request.headers.get("X-CSRF-Token")
    if not submitted_token:
        content_type = request.headers.get("content-type", "")
        if "multipart/form-data" in content_type or "application/x-www-form-urlencoded" in content_type:
            form = await request.form()
            submitted_token = form.get("csrf_token")

    session_token = request.session.get(CSRF_SESSION_KEY)
    if not submitted_token or not session_token or not secrets.compare_digest(str(submitted_token), str(session_token)):
        raise HTTPException(status_code=403, detail="Forbidden")


def get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def normalize_text(value: str | None, *, max_length: int | None = None) -> str:
    normalized = (value or "").strip()
    if max_length is not None:
        normalized = normalized[:max_length]
    return normalized


def normalize_url(value: str | None) -> str:
    normalized = normalize_text(value, max_length=500)
    if not normalized:
        return ""

    if "://" not in normalized:
        normalized = f"https://{normalized}"

    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("Укажи корректную ссылку")

    return normalized


async def read_limited_upload(upload, max_bytes: int) -> bytes:
    content = await upload.read(max_bytes + 1)
    if len(content) > max_bytes:
        raise ValueError("Файл слишком большой")
    return content


def ensure_allowed_extension(filename: str | None, allowed_extensions: set[str]) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in allowed_extensions:
        raise ValueError("Недопустимый тип файла")
    return suffix


def save_profile_photo(content: bytes, destination: Path) -> None:
    try:
        with Image.open(io.BytesIO(content)) as image:
            image.verify()
        with Image.open(io.BytesIO(content)) as image:
            image = image.convert("RGB")
            if image.width < 64 or image.height < 64:
                raise ValueError("Изображение слишком маленькое")
            image.thumbnail((1800, 1800))
            destination.parent.mkdir(parents=True, exist_ok=True)
            image.save(destination, format="JPEG", quality=92, optimize=True)
    except (UnidentifiedImageError, OSError):
        raise ValueError("Файл не похож на изображение")


def save_certificate_file(content: bytes, filename: str | None, destination_dir: Path) -> str:
    suffix = ensure_allowed_extension(filename, ALLOWED_CERTIFICATE_EXTENSIONS)
    destination_dir.mkdir(parents=True, exist_ok=True)
    safe_name = f"{datetime.utcnow().strftime('%Y%m%d%H%M%S')}_{secrets.token_hex(6)}{suffix}"
    destination = destination_dir / safe_name

    if suffix in ALLOWED_IMAGE_EXTENSIONS:
        try:
            with Image.open(io.BytesIO(content)) as image:
                image.verify()
        except (UnidentifiedImageError, OSError):
            raise ValueError("Файл сертификата поврежден или не является изображением")

    destination.write_bytes(content)
    return f"/static/uploads/certificates/{safe_name}"


def build_session_secret() -> str:
    configured = os.getenv("CVAAS_SESSION_SECRET")
    if configured:
        return configured
    return secrets.token_urlsafe(48)


def login_rate_limit_message(blocked_until: datetime) -> str:
    remaining = max(int((blocked_until - datetime.utcnow()).total_seconds()), 0)
    minutes = max(1, (remaining + 59) // 60)
    return f"Слишком много попыток входа. Попробуй снова через {minutes} мин."


def login_window_expired(first_attempt_at: datetime | None) -> bool:
    if not first_attempt_at:
        return True
    return datetime.utcnow() - first_attempt_at > timedelta(minutes=LOGIN_WINDOW_MINUTES)
