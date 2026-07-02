"""File storage service with S3-compatible object storage and local filesystem backends."""

import asyncio
import hashlib
import hmac
import logging
import os
import shutil
import tempfile
import time
import uuid
from collections.abc import AsyncIterable, AsyncIterator
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

import boto3
from botocore.config import Config as BotoConfig
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)

_client = None
_storage_status_cache: tuple[float, tuple, dict[str, str | bool]] | None = None
_STORAGE_STATUS_CACHE_TTL_SECONDS = 30
S3_MIN_MULTIPART_PART_BYTES = 5 * 1024 * 1024
S3_PART_SIGN_EXPIRES_SECONDS = 15 * 60


class StorageUnavailableError(RuntimeError):
    def __init__(self, reason_code: str) -> None:
        super().__init__(reason_code)
        self.reason_code = reason_code


class UploadTooLargeError(ValueError):
    def __init__(self, limit_bytes: int, actual_bytes: int) -> None:
        super().__init__("upload too large")
        self.limit_bytes = limit_bytes
        self.actual_bytes = actual_bytes


class DownloadRangeNotSatisfiableError(ValueError):
    def __init__(self, size: int) -> None:
        super().__init__("download range not satisfiable")
        self.size = size


@dataclass(frozen=True)
class DownloadRange:
    start: int
    end: int
    size: int
    is_partial: bool

    @property
    def length(self) -> int:
        if self.size <= 0:
            return 0
        return max(0, self.end - self.start + 1)

    @property
    def content_range(self) -> str:
        return f"bytes {self.start}-{self.end}/{self.size}"


@dataclass(frozen=True)
class DownloadStream:
    range: DownloadRange
    chunks: AsyncIterator[bytes]


@dataclass(frozen=True)
class MultipartUploadContext:
    storage_key: str
    provider_upload_id: str


@dataclass(frozen=True)
class MultipartPartUploadUrl:
    upload_url: str
    expires_at: datetime
    required_headers: dict[str, str]


def _storage_intent() -> str:
    intent = (settings.UPLOAD_STORAGE_BACKEND or "auto").lower()
    return intent if intent in {"auto", "local", "s3"} else "auto"


def _s3_required_values() -> list[str]:
    return [
        settings.S3_ENDPOINT,
        settings.S3_BUCKET,
        settings.S3_ACCESS_KEY_ID,
        settings.S3_SECRET_ACCESS_KEY,
    ]


def _s3_any_configured() -> bool:
    return any(bool(value) for value in _s3_required_values())


def _s3_config_complete() -> bool:
    return all(bool(value) for value in _s3_required_values())


def _target_backend() -> str:
    intent = _storage_intent()
    if intent == "local":
        return "local"
    if intent == "s3":
        return "s3"
    return "s3" if _s3_any_configured() else "local"


def _use_s3() -> bool:
    return _target_backend() == "s3" and _s3_config_complete()


def is_configured() -> bool:
    return get_storage_status()["storage_status"] == "available"


def reset_storage_status_cache() -> None:
    global _storage_status_cache
    _storage_status_cache = None


def _storage_status_signature() -> tuple:
    return (
        _storage_intent(),
        settings.S3_ENDPOINT,
        settings.S3_REGION,
        settings.S3_BUCKET,
        settings.S3_ACCESS_KEY_ID,
        settings.S3_SECRET_ACCESS_KEY,
        settings.S3_KEY_PREFIX,
        settings.LOCAL_STORAGE_DIR,
        tuple(settings.CORS_ORIGINS or []),
    )


def _status(
    *,
    backend: str,
    storage_status: str,
    storage_reason_code: str,
    direct_upload_supported: bool,
) -> dict[str, str | bool]:
    return {
        "backend": backend,
        "storage_status": storage_status,
        "storage_reason_code": storage_reason_code,
        "direct_upload_supported": direct_upload_supported,
    }


def get_storage_status(*, force_refresh: bool = False) -> dict[str, str | bool]:
    global _storage_status_cache
    signature = _storage_status_signature()
    now = time.time()
    if not force_refresh and _storage_status_cache is not None:
        expires_at, cached_signature, cached_status = _storage_status_cache
        if cached_signature == signature and expires_at > now:
            return dict(cached_status)

    status = _compute_storage_status()
    _storage_status_cache = (now + _STORAGE_STATUS_CACHE_TTL_SECONDS, signature, status)
    return dict(status)


def _compute_storage_status() -> dict[str, str | bool]:
    backend = _target_backend()
    if backend == "s3":
        if not _s3_config_complete():
            return _status(
                backend="s3",
                storage_status="unavailable",
                storage_reason_code="s3_config_incomplete",
                direct_upload_supported=False,
            )
        return _s3_health_status()

    local_dir = _get_local_dir()
    parent = local_dir if local_dir.exists() else local_dir.parent
    if parent.exists() and os.access(parent, os.W_OK):
        return _status(
            backend="local",
            storage_status="available",
            storage_reason_code="",
            direct_upload_supported=False,
        )
    return _status(
        backend="local",
        storage_status="unavailable",
        storage_reason_code="local_storage_unwritable",
        direct_upload_supported=False,
    )


def _ensure_storage_available() -> None:
    status = get_storage_status()
    if status["storage_status"] != "available":
        raise StorageUnavailableError(str(status["storage_reason_code"]))


def _get_local_dir() -> Path:
    if settings.LOCAL_STORAGE_DIR:
        return Path(settings.LOCAL_STORAGE_DIR)
    return Path.home() / ".nodeskclaw" / "shared-files"


def _safe_filename(filename: str) -> str:
    clean = filename.replace("\\", "/").split("/")[-1].strip()
    clean = "".join(ch for ch in clean if ch >= " " and ch != "\x7f")
    return clean or "unnamed"


def _build_object_key(workspace_id: str, filename: str, *, include_prefix: bool) -> str:
    safe_name = _safe_filename(filename)
    base = f"workspace-files/{workspace_id}/{uuid.uuid4().hex}/{safe_name}"
    if not include_prefix:
        return base
    prefix = settings.S3_KEY_PREFIX.strip("/")
    return f"{prefix}/{base}" if prefix else base


def _sign_url(key: str, expires_at: int) -> str:
    payload = f"{key}{expires_at}"
    sig = hmac.new(
        settings.JWT_SECRET.encode(), payload.encode(), hashlib.sha256,
    ).hexdigest()
    return sig


def verify_signature(key: str, expires_str: str, sig: str) -> bool:
    try:
        expires_at = int(expires_str)
    except (ValueError, TypeError):
        return False
    if time.time() > expires_at:
        return False
    expected = _sign_url(key, expires_at)
    return hmac.compare_digest(expected, sig)


# ── S3 backend ──────────────────────────────────────────

def _get_s3_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT,
            region_name=settings.S3_REGION or None,
            aws_access_key_id=settings.S3_ACCESS_KEY_ID,
            aws_secret_access_key=settings.S3_SECRET_ACCESS_KEY,
            config=BotoConfig(signature_version="s3v4"),
        )
    return _client


def _s3_reason(exc: Exception, default: str) -> str:
    if isinstance(exc, ClientError):
        code = str(exc.response.get("Error", {}).get("Code", "")).lower()
        if code in {"accessdenied", "invalidaccesskeyid", "signaturedoesnotmatch"}:
            return "s3_credentials_invalid"
        if code in {"nosuchbucket", "notfound", "404"}:
            return "s3_bucket_unavailable"
    if isinstance(exc, BotoCoreError):
        return "s3_endpoint_unavailable"
    return default


def _health_check_key(kind: str) -> str:
    prefix = settings.S3_KEY_PREFIX.strip("/")
    base = f".nodeskclaw-health/{kind}/{uuid.uuid4().hex}"
    return f"{prefix}/{base}" if prefix else base


def _s3_probe_bucket_access() -> None:
    client = _get_s3_client()
    client.head_bucket(Bucket=settings.S3_BUCKET)
    key = _health_check_key("write")
    try:
        client.put_object(
            Bucket=settings.S3_BUCKET,
            Key=key,
            Body=b"",
            ContentType="application/octet-stream",
        )
    finally:
        try:
            client.delete_object(Bucket=settings.S3_BUCKET, Key=key)
        except Exception:
            logger.warning("S3 health check cleanup failed", exc_info=True)


def _s3_probe_multipart_access() -> None:
    client = _get_s3_client()
    key = _health_check_key("multipart")
    upload_id = ""
    try:
        resp = client.create_multipart_upload(
            Bucket=settings.S3_BUCKET,
            Key=key,
            ContentType="application/octet-stream",
            Metadata={"nodeskclaw_health": "multipart"},
        )
        upload_id = str(resp.get("UploadId") or "")
    finally:
        if upload_id:
            try:
                client.abort_multipart_upload(
                    Bucket=settings.S3_BUCKET,
                    Key=key,
                    UploadId=upload_id,
                )
            except Exception:
                logger.warning("S3 multipart health check abort failed", exc_info=True)


def _matches_cors_value(values: list[str], required: str) -> bool:
    normalized = {value.lower() for value in values}
    return "*" in normalized or required.lower() in normalized


def _allows_header(values: list[str], required: str) -> bool:
    normalized = {value.lower() for value in values}
    return (
        "*" in normalized
        or required.lower() in normalized
        or any(value.endswith("*") and required.lower().startswith(value[:-1]) for value in normalized)
    )


def _s3_cors_allows_direct_upload() -> bool:
    origins = [origin for origin in (settings.CORS_ORIGINS or []) if origin]
    if not origins:
        return False
    if "*" in origins:
        return True

    client = _get_s3_client()
    resp = client.get_bucket_cors(Bucket=settings.S3_BUCKET)
    rules = resp.get("CORSRules") or []
    for origin in origins:
        allowed = False
        for rule in rules:
            rule_origins = rule.get("AllowedOrigins") or []
            rule_methods = rule.get("AllowedMethods") or []
            rule_headers = rule.get("AllowedHeaders") or []
            expose_headers = rule.get("ExposeHeaders") or []
            if not _matches_cors_value(rule_origins, origin):
                continue
            if not _matches_cors_value(rule_methods, "PUT") or not _matches_cors_value(rule_methods, "POST"):
                continue
            if not _allows_header(rule_headers, "content-type"):
                continue
            if not _matches_cors_value(expose_headers, "etag"):
                continue
            allowed = True
            break
        if not allowed:
            return False
    return True


def _s3_health_status() -> dict[str, str | bool]:
    try:
        _s3_probe_bucket_access()
    except Exception as exc:
        return _status(
            backend="s3",
            storage_status="unavailable",
            storage_reason_code=_s3_reason(exc, "s3_bucket_unavailable"),
            direct_upload_supported=False,
        )

    try:
        _s3_probe_multipart_access()
    except Exception as exc:
        return _status(
            backend="s3",
            storage_status="unavailable",
            storage_reason_code=_s3_reason(exc, "s3_multipart_unavailable"),
            direct_upload_supported=False,
        )

    try:
        cors_allows_direct_upload = _s3_cors_allows_direct_upload()
    except Exception:
        cors_allows_direct_upload = False

    return _status(
        backend="s3",
        storage_status="available",
        storage_reason_code="" if cors_allows_direct_upload else "s3_cors_direct_upload_unavailable",
        direct_upload_supported=cors_allows_direct_upload,
    )


def _s3_upload(file_content: bytes, filename: str, content_type: str, workspace_id: str) -> str:
    client = _get_s3_client()
    key = _build_object_key(workspace_id, filename, include_prefix=True)
    client.put_object(
        Bucket=settings.S3_BUCKET,
        Key=key,
        Body=file_content,
        ContentType=content_type,
    )
    return key


def _s3_presigned_url(key: str, expires: int = 3600) -> str:
    client = _get_s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={"Bucket": settings.S3_BUCKET, "Key": key},
        ExpiresIn=expires,
    )


def _s3_download(key: str) -> bytes:
    client = _get_s3_client()
    resp = client.get_object(Bucket=settings.S3_BUCKET, Key=key)
    return resp["Body"].read()


def _s3_size(key: str) -> int:
    client = _get_s3_client()
    resp = client.head_object(Bucket=settings.S3_BUCKET, Key=key)
    return int(resp["ContentLength"])


def _s3_copy(source_key: str, target_key: str, content_type: str) -> None:
    client = _get_s3_client()
    client.copy_object(
        Bucket=settings.S3_BUCKET,
        Key=target_key,
        CopySource={"Bucket": settings.S3_BUCKET, "Key": source_key},
        ContentType=content_type,
        MetadataDirective="REPLACE",
    )


def _s3_delete(key: str) -> None:
    client = _get_s3_client()
    client.delete_object(Bucket=settings.S3_BUCKET, Key=key)


def _s3_create_multipart_upload(
    filename: str,
    content_type: str,
    workspace_id: str,
    metadata: dict[str, str],
) -> MultipartUploadContext:
    client = _get_s3_client()
    key = _build_object_key(workspace_id, filename, include_prefix=True)
    resp = client.create_multipart_upload(
        Bucket=settings.S3_BUCKET,
        Key=key,
        ContentType=content_type,
        Metadata=metadata,
    )
    return MultipartUploadContext(
        storage_key=key,
        provider_upload_id=str(resp["UploadId"]),
    )


def _s3_sign_multipart_part(
    key: str,
    provider_upload_id: str,
    part_number: int,
    expires: int,
) -> str:
    client = _get_s3_client()
    return client.generate_presigned_url(
        "upload_part",
        Params={
            "Bucket": settings.S3_BUCKET,
            "Key": key,
            "UploadId": provider_upload_id,
            "PartNumber": part_number,
        },
        ExpiresIn=expires,
    )


def _s3_complete_multipart_upload(
    key: str,
    provider_upload_id: str,
    parts: list[dict[str, str | int]],
) -> None:
    client = _get_s3_client()
    client.complete_multipart_upload(
        Bucket=settings.S3_BUCKET,
        Key=key,
        UploadId=provider_upload_id,
        MultipartUpload={
            "Parts": [
                {"PartNumber": int(part["part_number"]), "ETag": str(part["etag"])}
                for part in parts
            ],
        },
    )


def _s3_abort_multipart_upload(key: str, provider_upload_id: str) -> None:
    client = _get_s3_client()
    client.abort_multipart_upload(
        Bucket=settings.S3_BUCKET,
        Key=key,
        UploadId=provider_upload_id,
    )


def _s3_hash_object(key: str) -> tuple[int, str]:
    client = _get_s3_client()
    resp = client.get_object(Bucket=settings.S3_BUCKET, Key=key)
    body = resp["Body"]
    digest = hashlib.sha256()
    total = 0
    try:
        while True:
            chunk = body.read(1024 * 1024)
            if not chunk:
                break
            total += len(chunk)
            digest.update(chunk)
    finally:
        body.close()
    return total, digest.hexdigest()


# ── Local filesystem backend ─────────────────────────────

def _local_upload(file_content: bytes, filename: str, _content_type: str, workspace_id: str) -> str:
    base = _build_object_key(workspace_id, filename, include_prefix=False)
    local_dir = _get_local_dir()
    file_path = local_dir / base
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(file_content)
    return base


def _local_presigned_url(key: str, expires: int = 3600) -> str:
    expires_at = int(time.time()) + expires
    sig = _sign_url(key, expires_at)
    return f"/api/v1/files/local/{key}?expires={expires_at}&sig={sig}"


def _local_download(key: str) -> bytes:
    file_path = _get_local_dir() / key
    return file_path.read_bytes()


def _local_size(key: str) -> int:
    file_path = _get_local_dir() / key
    return file_path.stat().st_size


def _local_copy(source_key: str, target_key: str) -> None:
    source_path = _get_local_dir() / source_key
    target_path = _get_local_dir() / target_key
    target_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with source_path.open("rb") as src, target_path.open("wb") as dst:
            shutil.copyfileobj(src, dst, length=1024 * 1024)
    except Exception:
        try:
            target_path.unlink()
        except FileNotFoundError:
            pass
        raise


def _local_delete(key: str) -> None:
    file_path = _get_local_dir() / key
    try:
        file_path.unlink()
    except FileNotFoundError:
        pass


# ── Public async API ─────────────────────────────────────

async def upload_file(file_content: bytes, filename: str, content_type: str, workspace_id: str) -> str:
    _ensure_storage_available()
    if _use_s3():
        return await asyncio.to_thread(_s3_upload, file_content, filename, content_type, workspace_id)
    return await asyncio.to_thread(_local_upload, file_content, filename, content_type, workspace_id)


async def upload_stream(
    chunks: AsyncIterable[bytes],
    filename: str,
    content_type: str,
    workspace_id: str,
    *,
    max_bytes: int | None = None,
) -> tuple[str, int, str]:
    _ensure_storage_available()
    if _use_s3():
        return await _s3_upload_stream(chunks, filename, content_type, workspace_id, max_bytes=max_bytes)
    return await _local_upload_stream(chunks, filename, content_type, workspace_id, max_bytes=max_bytes)


async def upload_file_object(
    file_obj,
    filename: str,
    content_type: str,
    workspace_id: str,
    *,
    max_bytes: int | None = None,
    chunk_size: int = 1024 * 1024,
) -> tuple[str, int, str]:
    async def _chunks():
        while True:
            chunk = await file_obj.read(chunk_size)
            if not chunk:
                break
            yield chunk

    return await upload_stream(
        _chunks(),
        filename,
        content_type,
        workspace_id,
        max_bytes=max_bytes,
    )


async def create_multipart_upload(
    filename: str,
    content_type: str,
    workspace_id: str,
    *,
    metadata: dict[str, str] | None = None,
) -> MultipartUploadContext:
    _ensure_storage_available()
    if not _use_s3():
        raise StorageUnavailableError("direct_upload_unavailable")
    clean_metadata = {
        str(key)[:64]: str(value)[:256]
        for key, value in (metadata or {}).items()
        if key and value is not None
    }
    try:
        return await asyncio.to_thread(
            _s3_create_multipart_upload,
            filename,
            content_type,
            workspace_id,
            clean_metadata,
        )
    except Exception as exc:
        raise StorageUnavailableError(_s3_reason(exc, "s3_multipart_unavailable")) from exc


async def sign_multipart_part(
    key: str,
    provider_upload_id: str,
    part_number: int,
    *,
    expires: int = S3_PART_SIGN_EXPIRES_SECONDS,
) -> MultipartPartUploadUrl:
    _ensure_storage_available()
    if not _use_s3():
        raise StorageUnavailableError("direct_upload_unavailable")
    ttl = max(1, min(expires, S3_PART_SIGN_EXPIRES_SECONDS))
    try:
        upload_url = await asyncio.to_thread(
            _s3_sign_multipart_part,
            key,
            provider_upload_id,
            part_number,
            ttl,
        )
    except Exception as exc:
        raise StorageUnavailableError(_s3_reason(exc, "s3_presign_unavailable")) from exc
    return MultipartPartUploadUrl(
        upload_url=upload_url,
        expires_at=datetime.now(timezone.utc) + timedelta(seconds=ttl),
        required_headers={},
    )


async def complete_multipart_upload(
    key: str,
    provider_upload_id: str,
    parts: list[dict[str, str | int]],
) -> tuple[int, str]:
    _ensure_storage_available()
    if not _use_s3():
        raise StorageUnavailableError("direct_upload_unavailable")
    try:
        await asyncio.to_thread(_s3_complete_multipart_upload, key, provider_upload_id, parts)
        return await asyncio.to_thread(_s3_hash_object, key)
    except Exception as exc:
        raise StorageUnavailableError(_s3_reason(exc, "s3_multipart_unavailable")) from exc


async def abort_multipart_upload(key: str, provider_upload_id: str) -> None:
    if not key or not provider_upload_id or not _s3_config_complete():
        return
    try:
        await asyncio.to_thread(_s3_abort_multipart_upload, key, provider_upload_id)
    except Exception as exc:
        raise StorageUnavailableError(_s3_reason(exc, "s3_multipart_unavailable")) from exc


def _s3_put_fileobj(file_obj, key: str, content_type: str) -> None:
    client = _get_s3_client()
    client.put_object(
        Bucket=settings.S3_BUCKET,
        Key=key,
        Body=file_obj,
        ContentType=content_type,
    )


async def _s3_upload_stream(
    chunks: AsyncIterable[bytes],
    filename: str,
    content_type: str,
    workspace_id: str,
    *,
    max_bytes: int | None,
) -> tuple[str, int, str]:
    key = _build_object_key(workspace_id, filename, include_prefix=True)
    digest = hashlib.sha256()
    total = 0
    with tempfile.SpooledTemporaryFile(max_size=8 * 1024 * 1024) as tmp:
        async for chunk in chunks:
            total += len(chunk)
            if max_bytes is not None and total > max_bytes:
                raise UploadTooLargeError(max_bytes, total)
            digest.update(chunk)
            tmp.write(chunk)
        tmp.seek(0)
        await asyncio.to_thread(_s3_put_fileobj, tmp, key, content_type)
    return key, total, digest.hexdigest()


async def _local_upload_stream(
    chunks: AsyncIterable[bytes],
    filename: str,
    _content_type: str,
    workspace_id: str,
    *,
    max_bytes: int | None,
) -> tuple[str, int, str]:
    key = _build_object_key(workspace_id, filename, include_prefix=False)
    file_path = _get_local_dir() / key
    file_path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    total = 0
    try:
        with file_path.open("wb") as fh:
            async for chunk in chunks:
                total += len(chunk)
                if max_bytes is not None and total > max_bytes:
                    raise UploadTooLargeError(max_bytes, total)
                digest.update(chunk)
                fh.write(chunk)
    except Exception:
        try:
            file_path.unlink()
        except FileNotFoundError:
            pass
        raise
    return key, total, digest.hexdigest()


async def get_presigned_url(key: str, expires: int = 3600) -> str:
    _ensure_storage_available()
    if _use_s3():
        return await asyncio.to_thread(_s3_presigned_url, key, expires)
    return _local_presigned_url(key, expires)


async def get_file_size(key: str) -> int:
    _ensure_storage_available()
    if _use_s3():
        return await asyncio.to_thread(_s3_size, key)
    return await asyncio.to_thread(_local_size, key)


def resolve_download_range(range_header: str | None, size: int) -> DownloadRange:
    if not range_header:
        end = max(0, size - 1)
        return DownloadRange(0, end, size, False)

    value = range_header.strip()
    if not value.startswith("bytes=") or "," in value:
        raise DownloadRangeNotSatisfiableError(size)

    spec = value.removeprefix("bytes=").strip()
    if "-" not in spec:
        raise DownloadRangeNotSatisfiableError(size)

    start_text, end_text = spec.split("-", 1)
    try:
        if start_text == "":
            suffix_length = int(end_text)
            if suffix_length <= 0 or size <= 0:
                raise DownloadRangeNotSatisfiableError(size)
            start = max(size - suffix_length, 0)
            end = size - 1
        else:
            start = int(start_text)
            end = int(end_text) if end_text else size - 1
    except ValueError as exc:
        raise DownloadRangeNotSatisfiableError(size) from exc

    if size <= 0 or start < 0 or end < start or start >= size:
        raise DownloadRangeNotSatisfiableError(size)

    return DownloadRange(start, min(end, size - 1), size, True)


async def _empty_chunks() -> AsyncIterator[bytes]:
    if False:
        yield b""


async def _local_iter_range(
    key: str,
    start: int,
    end: int,
    *,
    chunk_size: int,
) -> AsyncIterator[bytes]:
    remaining = max(0, end - start + 1)
    if remaining == 0:
        async for chunk in _empty_chunks():
            yield chunk
        return

    file_path = _get_local_dir() / key
    with file_path.open("rb") as fh:
        fh.seek(start)
        while remaining > 0:
            chunk = await asyncio.to_thread(fh.read, min(chunk_size, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def _s3_range_body(key: str, start: int, end: int):
    client = _get_s3_client()
    range_header = f"bytes={start}-{end}"
    resp = client.get_object(
        Bucket=settings.S3_BUCKET,
        Key=key,
        Range=range_header,
    )
    return resp["Body"]


async def _s3_iter_range(
    key: str,
    start: int,
    end: int,
    *,
    chunk_size: int,
) -> AsyncIterator[bytes]:
    if end < start:
        async for chunk in _empty_chunks():
            yield chunk
        return

    body = await asyncio.to_thread(_s3_range_body, key, start, end)
    try:
        while True:
            chunk = await asyncio.to_thread(body.read, chunk_size)
            if not chunk:
                break
            yield chunk
    finally:
        body.close()


async def get_download_stream(
    key: str,
    range_header: str | None = None,
    *,
    chunk_size: int = 1024 * 1024,
) -> DownloadStream:
    size = await get_file_size(key)
    resolved = resolve_download_range(range_header, size)
    if resolved.length == 0:
        chunks = _empty_chunks()
    elif _use_s3():
        chunks = _s3_iter_range(key, resolved.start, resolved.end, chunk_size=chunk_size)
    else:
        chunks = _local_iter_range(key, resolved.start, resolved.end, chunk_size=chunk_size)
    return DownloadStream(resolved, chunks)


async def download_file(key: str) -> bytes:
    _ensure_storage_available()
    if _use_s3():
        return await asyncio.to_thread(_s3_download, key)
    return await asyncio.to_thread(_local_download, key)


async def copy_file(source_key: str, filename: str, content_type: str, workspace_id: str) -> str:
    _ensure_storage_available()
    if _use_s3():
        target_key = _build_object_key(workspace_id, filename, include_prefix=True)
        await asyncio.to_thread(_s3_copy, source_key, target_key, content_type)
        return target_key

    target_key = _build_object_key(workspace_id, filename, include_prefix=False)
    await asyncio.to_thread(_local_copy, source_key, target_key)
    return target_key


async def delete_file(key: str) -> None:
    _ensure_storage_available()
    if _use_s3():
        await asyncio.to_thread(_s3_delete, key)
    else:
        await asyncio.to_thread(_local_delete, key)


# ── Raw key API (for backup storage) ─────────────────────

def _s3_upload_raw(key: str, data: bytes) -> None:
    client = _get_s3_client()
    prefix = settings.S3_KEY_PREFIX.strip("/")
    full_key = f"{prefix}/{key}" if prefix else key
    client.put_object(Bucket=settings.S3_BUCKET, Key=full_key, Body=data)


def _local_upload_raw(key: str, data: bytes) -> None:
    file_path = _get_local_dir() / key
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(data)


async def upload_raw(key: str, data: bytes) -> None:
    """Upload raw bytes to a specific storage key."""
    if _use_s3():
        await asyncio.to_thread(_s3_upload_raw, key, data)
    else:
        await asyncio.to_thread(_local_upload_raw, key, data)


def _s3_download_raw(key: str) -> bytes:
    client = _get_s3_client()
    prefix = settings.S3_KEY_PREFIX.strip("/")
    full_key = f"{prefix}/{key}" if prefix else key
    resp = client.get_object(Bucket=settings.S3_BUCKET, Key=full_key)
    return resp["Body"].read()


def _local_download_raw(key: str) -> bytes:
    file_path = _get_local_dir() / key
    return file_path.read_bytes()


async def download_raw(key: str) -> bytes:
    """Download raw bytes from a specific storage key."""
    if _use_s3():
        return await asyncio.to_thread(_s3_download_raw, key)
    return await asyncio.to_thread(_local_download_raw, key)


def _s3_delete_raw(key: str) -> None:
    client = _get_s3_client()
    prefix = settings.S3_KEY_PREFIX.strip("/")
    full_key = f"{prefix}/{key}" if prefix else key
    client.delete_object(Bucket=settings.S3_BUCKET, Key=full_key)


def _local_delete_raw(key: str) -> None:
    file_path = _get_local_dir() / key
    try:
        file_path.unlink()
    except FileNotFoundError:
        pass


async def delete_raw(key: str) -> None:
    """Delete an object by specific storage key."""
    if _use_s3():
        await asyncio.to_thread(_s3_delete_raw, key)
    else:
        await asyncio.to_thread(_local_delete_raw, key)
