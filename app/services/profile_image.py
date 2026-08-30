"""
profile_image_service.py
────────────────────────────────────────────────────────────────────────────
Profile-image upload and retrieval — backed by the R2 *private* bucket.

Key design decisions
────────────────────
• Private bucket only — profile images are never served via a public CDN URL.
  Every access goes through a 1-hour presigned URL generated at request time.

• Two derivatives are stored per upload:
    institutions/{tenant_id}/users/{user_id}/profile/main.webp   (200 × 200)
    institutions/{tenant_id}/users/{user_id}/profile/thumb.webp  ( 64 ×  64)

  Sizes are kept deliberately small compared to the old 400/128 px JPEG pair:
    - 200 px is plenty for any UI avatar at 2× retina density.
    - 64 px thumb is ideal for lists, nav bars, comment threads.
    - WebP at quality 80 is ~50-70 % smaller than JPEG at quality 85
      for the same perceived quality — protects R2 bandwidth & egress cost.

• Old derivatives are deleted from R2 *after* the DB commit succeeds so we
  never leave the row pointing at a key that no longer exists.

• get_profile_url / get_profile_thumb_url return 1-hour presigned URLs —
  the only safe way to expose private-bucket objects to authenticated callers.

Import the two public helpers:
    from .profile_image_service import upload_profile_image, get_profile_url
"""

from __future__ import annotations

import io
import logging
from typing import Optional

import magic
from fastapi import UploadFile
from PIL import Image, UnidentifiedImageError
from sqlalchemy.ext.asyncio import AsyncSession

from ..core.storage import r2, R2StorageError      
from ..core.exceptions import (
    InvalidImageError,
    ImageTooLargeError,
    FileUploadError,
    UserNotFoundException,
)


from ..crud.user_fun import get_basic_user_by_id

logger = logging.getLogger(__name__)


# ─── Constants ────────────────────────────────────────────────────────────────

MAX_FILE_SIZE_BYTES: int = 5 * 1024 * 1024   # 5 MB — input gate

# Output sizes — intentionally smaller than the old 400/128 px JPEG values.
# 200 px covers 2× retina; WebP compression does the rest.
MAIN_SIZE:  tuple[int, int] = (200, 200)
THUMB_SIZE: tuple[int, int] = ( 64,  64)

WEBP_QUALITY_MAIN:  int = 80
WEBP_QUALITY_THUMB: int = 75

OUTPUT_CONTENT_TYPE = "image/webp"

ALLOWED_MIME: set[str] = {"image/jpeg", "image/png", "image/webp"}

# Presigned URL lifetime (seconds)
SIGNED_URL_TTL: int = 3600   # 1 hour


# ─── R2 key helpers ───────────────────────────────────────────────────────────

def _main_key(tenant_id: str, user_id: int) -> str:
    return f"institutions/{tenant_id}/users/{user_id}/profile/main.webp"


def _thumb_key(tenant_id: str, user_id: int) -> str:
    return f"institutions/{tenant_id}/users/{user_id}/profile/thumb.webp"


# ─── Image processing ─────────────────────────────────────────────────────────

def _crop_square(image: Image.Image) -> Image.Image:
    """Centre-crop to a square without upscaling."""
    w, h = image.size
    side  = min(w, h)
    left  = (w - side) // 2
    top   = (h - side) // 2
    return image.crop((left, top, left + side, top + side))


def _encode_webp(image: Image.Image, size: tuple[int, int], quality: int) -> bytes:
    """
    Crop → resize → encode to WebP.
    Always converts to RGB first to strip alpha / palette modes safely.
    """
    img = _crop_square(image)
    img = img.resize(size, Image.LANCZOS)
    if img.mode != "RGB":
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode in ("RGBA", "LA", "P"):
            img = img.convert("RGBA")
            bg.paste(img, mask=img.split()[3])
            img = bg
        else:
            img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=quality, method=6)
    return buf.getvalue()


# ─── Validation ───────────────────────────────────────────────────────────────

async def _validate_and_decode(file: UploadFile) -> Image.Image:
    """
    Run the full validation pipeline and return an open Pillow image.

    Pipeline:
      1. Size cap
      2. Magic-byte MIME check
      3. Pillow verify() — rejects corrupt / polyglot files
      4. Re-open for pixel access (verify() exhausts the stream)

    Raises InvalidImageError / ImageTooLargeError on failure.
    """
    raw: bytes = await file.read()

    # 1. Size cap
    if len(raw) == 0:
        raise InvalidImageError("Uploaded file is empty.")
    if len(raw) > MAX_FILE_SIZE_BYTES:
        raise ImageTooLargeError(
            f"File is {len(raw):,} bytes — limit is {MAX_FILE_SIZE_BYTES:,} bytes (5 MB)."
        )

    # 2. Magic-byte MIME check
    try:
        detected: str = magic.from_buffer(raw[:4096], mime=True)
    except Exception as exc:
        logger.warning("python-magic failed: %s", exc)
        raise InvalidImageError("Could not detect file type.")

    if detected not in ALLOWED_MIME:
        raise InvalidImageError(f"Unsupported image format: {detected}.")

    # 3. Pillow verify
    try:
        probe = Image.open(io.BytesIO(raw))
        probe.verify()
    except UnidentifiedImageError:
        raise InvalidImageError("File is not a recognised image.")
    except Exception as exc:
        logger.warning("Pillow verify failed: %s", exc)
        raise InvalidImageError("Image validation failed — file may be corrupt.")

    # 4. Re-open after verify (stream is exhausted)
    try:
        return Image.open(io.BytesIO(raw))
    except Exception as exc:
        logger.warning("Pillow re-open failed: %s", exc)
        raise InvalidImageError("Could not decode image after validation.")


# ══════════════════════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════════════════════

async def upload_profile_image(
    file: UploadFile,
    tenant_id: str,
    user_id: int,
    db: AsyncSession,
) -> dict[str, str]:
    """
    Validate → encode two WebP derivatives → upload both to the R2 private
    bucket → update the user row → delete old keys (best-effort).

    Returns:
        {
            "main_key":   "<r2-key>",
            "thumb_key":  "<r2-key>",
            "main_url":   "<1-hour presigned URL>",
            "thumb_url":  "<1-hour presigned URL>",
        }

    Raises:
        InvalidImageError   — bad file
        ImageTooLargeError  — exceeds 5 MB
        FileUploadError     — R2 or DB failure
    """
    try:
        image = await _validate_and_decode(file)
    except (InvalidImageError, ImageTooLargeError):
        raise

    # Encode derivatives
    try:
        main_bytes  = _encode_webp(image, MAIN_SIZE,  WEBP_QUALITY_MAIN)
        thumb_bytes = _encode_webp(image, THUMB_SIZE, WEBP_QUALITY_THUMB)
    except Exception as exc:
        logger.error("WebP encode failed | tenant=%s user=%s: %s", tenant_id, user_id, exc)
        raise FileUploadError("Failed to process image.") from exc

    main_key  = _main_key(tenant_id, user_id)
    thumb_key = _thumb_key(tenant_id, user_id)

    # Fetch user + snapshot old keys before touching R2
    user = await get_basic_user_by_id(db=db, id=user_id, tenant_id=tenant_id)
    if not user:
        raise UserNotFoundException("User not found.")

    old_main_key:  Optional[str] = getattr(user, "profile_image_key",       None)
    old_thumb_key: Optional[str] = getattr(user, "profile_image_thumb_key", None)

    # Upload both derivatives (private bucket)
    try:
        await r2.upload(main_key,  main_bytes,  OUTPUT_CONTENT_TYPE, is_private=True)
        await r2.upload(thumb_key, thumb_bytes, OUTPUT_CONTENT_TYPE, is_private=True)
    except R2StorageError as exc:
        logger.error(
            "R2 upload failed | tenant=%s user=%s: %s", tenant_id, user_id, exc
        )
        raise FileUploadError("Storage upload failed.") from exc

    # Persist R2 keys to DB  (store keys, NOT URLs — URLs expire)
    try:
        user.profile_image_key       = main_key
        user.profile_image_thumb_key = thumb_key
        await db.commit()
        await db.refresh(user)
    except Exception as exc:
        # Roll back the R2 upload — best-effort cleanup
        await r2.delete(main_key,  is_private=True)
        await r2.delete(thumb_key, is_private=True)
        logger.error(
            "DB commit failed after R2 upload | tenant=%s user=%s: %s",
            tenant_id, user_id, exc,
        )
        raise FileUploadError("Failed to save profile image reference.") from exc

    # Delete old derivatives only after DB commit succeeds
    if old_main_key and old_main_key != main_key:
        await r2.delete(old_main_key,  is_private=True)
    if old_thumb_key and old_thumb_key != thumb_key:
        await r2.delete(old_thumb_key, is_private=True)

    # Return fresh presigned URLs (1-hour lifetime)
    try:
        main_url  = await r2.signed_url(main_key,  expires=SIGNED_URL_TTL)
        thumb_url = await r2.signed_url(thumb_key, expires=SIGNED_URL_TTL)
    except R2StorageError as exc:
        # Upload succeeded — don't fail the request, just warn
        logger.warning(
            "Presign failed after successful upload | tenant=%s user=%s: %s",
            tenant_id, user_id, exc,
        )
        main_url  = ""
        thumb_url = ""

    return {
        "main_key":  main_key,
        "thumb_key": thumb_key,
        "main_url":  main_url,
        "thumb_url": thumb_url,
    }


async def get_profile_signed_url(
    db: AsyncSession,
    tenant_id: str,
    user_id: int,
    image_type: str = "thumb",   # "main" | "thumb"
) -> str:
    """
    Return a 1-hour presigned URL for the requested profile image derivative.

    Args:
        image_type: "main"  → 200×200 full avatar
                    "thumb" → 64×64  nav/list icon  (default)

    Raises:
        UserNotFoundException — user row missing
        InvalidImageError     — no image on record for the requested type
        R2StorageError        — presign failed
    """
    user = await get_basic_user_by_id(db=db, id=user_id, tenant_id=tenant_id)
    if not user:
        raise UserNotFoundException("User not found.")

    # Pick the correct DB field based on requested type
    field = "profile_image_key" if image_type == "main" else "profile_image_thumb_key"
    key: Optional[str] = getattr(user, field, None)
    if not key:
        raise InvalidImageError(f"No profile {image_type} image uploaded yet.")

    return await r2.signed_url(key, expires=SIGNED_URL_TTL)