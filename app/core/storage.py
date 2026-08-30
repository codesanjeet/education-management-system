from __future__ import annotations

import logging
import os
import uuid
from pathlib import Path

import anyio
import boto3
from botocore.exceptions import BotoCoreError, ClientError
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)


# ── Env ───────────────────────────────────────────────────────────────────────

R2_PRIVATE_BUCKET: str = os.getenv("R2_PRIVATE_BUCKET_NAME", "")
R2_PUBLIC_BUCKET:  str = os.getenv("R2_PUBLIC_BUCKET_NAME",  "")
R2_PUBLIC_BASE:    str = os.getenv("R2_PUBLIC_BASE",          "").rstrip("/")
_R2_ENDPOINT:      str = os.getenv("R2_ENDPOINT",             "")
_R2_ACCESS_KEY:    str = os.getenv("R2_ACCESS_KEY",           "")
_R2_SECRET_KEY:    str = os.getenv("R2_SECRET_KEY",           "")

_MISSING = [
    name for name, val in {
        "R2_PRIVATE_BUCKET_NAME": R2_PRIVATE_BUCKET,
        "R2_PUBLIC_BUCKET_NAME":  R2_PUBLIC_BUCKET,
        "R2_PUBLIC_BASE":         R2_PUBLIC_BASE,
        "R2_ENDPOINT":            _R2_ENDPOINT,
        "R2_ACCESS_KEY":          _R2_ACCESS_KEY,
        "R2_SECRET_KEY":          _R2_SECRET_KEY,
    }.items()
    if not val
]
if _MISSING:
    raise RuntimeError(
        f"Missing required R2 env vars: {', '.join(_MISSING)}\n"
        "Set them in your .env before starting the application."
    )


# ── Exception ─────────────────────────────────────────────────────────────────

class R2StorageError(RuntimeError):
    """Raised when an R2 operation fails in a way the caller must handle."""


# ══════════════════════════════════════════════════════════════════════════════
# R2Storage
# ══════════════════════════════════════════════════════════════════════════════

class R2Storage:
    """
    Async-safe Cloudflare R2 client.

    A new boto3 client is created inside each method call because boto3 clients
    are NOT thread-safe across threads — one per call is the correct pattern
    for anyio thread-pool usage.

    Use the module-level singleton `r2`. Do not instantiate this class yourself.
    """

    # ── Internal ──────────────────────────────────────────────────────────────

    @staticmethod
    def _client():
        return boto3.client(
            service_name="s3",
            endpoint_url=_R2_ENDPOINT,
            aws_access_key_id=_R2_ACCESS_KEY,
            aws_secret_access_key=_R2_SECRET_KEY,
            region_name="auto",
        )

    @staticmethod
    def _bucket(is_private: bool) -> str:
        return R2_PRIVATE_BUCKET if is_private else R2_PUBLIC_BUCKET

    # ── Key builder ───────────────────────────────────────────────────────────

    @staticmethod
    def build_key(tenant_id: str, folder: str, filename: str) -> str:
        """
        Build a unique, collision-free R2 object key.

        Layout:  institutions/<tenant_id>/<folder>/<uuid><ext>

        Examples:
            r2.build_key("abc", "notifications", "report.pdf")
            # → "institutions/abc/notifications/3f2a...pdf"

            r2.build_key("abc", "avatars", "photo.jpg")
            # → "institutions/abc/avatars/9c1b...jpg"
        """
        ext = Path(filename).suffix.lower()
        return f"institutions/{tenant_id}/{folder}/{uuid.uuid4().hex}{ext}"

    # ── Upload ────────────────────────────────────────────────────────────────

    async def upload(
        self,
        key: str,
        content: bytes,
        content_type: str,
        *,
        is_private: bool,
    ) -> str:
        """
        Upload bytes to the correct bucket.
        Returns the key. Raises R2StorageError on failure.

        Private → CacheControl: private, no-cache
        Public  → CacheControl: public, max-age=31536000  +  ACL: public-read
        """
        bucket = self._bucket(is_private)
        extra: dict = {
            "CacheControl": "private, no-cache" if is_private else "public, max-age=31536000",
        }
        if not is_private:
            extra["ACL"] = "public-read"

        def _do() -> None:
            self._client().put_object(
                Bucket=bucket,
                Key=key,
                Body=content,
                ContentType=content_type,
                **extra,
            )

        try:
            await anyio.to_thread.run_sync(_do)
            logger.info("[R2] uploaded '%s' → %s bucket", key, "private" if is_private else "public")
            return key
        except (BotoCoreError, ClientError) as exc:
            logger.error("[R2] upload failed for '%s': %s", key, exc)
            raise R2StorageError(f"Upload failed: {exc}") from exc

    # ── Delete ────────────────────────────────────────────────────────────────

    async def delete(self, key: str | None, *, is_private: bool) -> None:
        """
        Delete an object from the correct bucket.
        Silently skips None / empty keys — safe to call unconditionally.
        Logs a warning on failure but never raises.
        """
        if not key:
            return
        bucket = self._bucket(is_private)

        def _do() -> None:
            self._client().delete_object(Bucket=bucket, Key=key)

        try:
            await anyio.to_thread.run_sync(_do)
            logger.info("[R2] deleted '%s' from %s bucket", key, "private" if is_private else "public")
        except (BotoCoreError, ClientError) as exc:
            logger.warning("[R2] delete warning for '%s': %s", key, exc)

    # ── URLs ──────────────────────────────────────────────────────────────────

    def public_url(self, key: str) -> str:
        """Permanent CDN URL for a public-bucket object. No network call."""
        return f"{R2_PUBLIC_BASE}/{key}"

    async def signed_url(self, key: str, *, expires: int = 3600) -> str:
        """
        Time-limited presigned URL for a private-bucket object.
        Raises R2StorageError on failure.
        """
        def _do() -> str:
            return self._client().generate_presigned_url(
                "get_object",
                Params={"Bucket": R2_PRIVATE_BUCKET, "Key": key},
                ExpiresIn=expires,
            )

        try:
            return await anyio.to_thread.run_sync(_do)
        except (BotoCoreError, ClientError) as exc:
            logger.error("[R2] presign failed for '%s': %s", key, exc)
            raise R2StorageError(f"Could not generate signed URL: {exc}") from exc

    async def url_for(self, key: str, *, is_private: bool, expires: int = 3600) -> str:
        """
        Return the right URL — no branching needed in callers.

        Private → presigned URL (expires after `expires` seconds)
        Public  → permanent CDN URL
        """
        if is_private:
            return await self.signed_url(key, expires=expires)
        return self.public_url(key)

    # ── Metadata ──────────────────────────────────────────────────────────────

    async def head(self, key: str, *, is_private: bool) -> dict:
        """
        Return object metadata without downloading the file.

        Returns {"size": int, "content_type": str}
        Returns {} if the object does not exist or the call fails — never raises.
        """
        bucket = self._bucket(is_private)

        def _do() -> dict:
            return self._client().head_object(Bucket=bucket, Key=key)

        try:
            resp = await anyio.to_thread.run_sync(_do)
            return {
                "size":         resp.get("ContentLength", 0),
                "content_type": resp.get("ContentType", "application/octet-stream"),
            }
        except (BotoCoreError, ClientError) as exc:
            logger.warning("[R2] head failed for '%s': %s", key, exc)
            return {}

    async def size(self, key: str, *, is_private: bool) -> int:
        """Return file size in bytes. Returns 0 on any error."""
        return (await self.head(key, is_private=is_private)).get("size", 0)


# ── Singleton ─────────────────────────────────────────────────────────────────

r2 = R2Storage()