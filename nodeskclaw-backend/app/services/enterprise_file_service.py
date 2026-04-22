"""Enterprise / instance file browsing service — read and write access to Agent instance files via PodFS."""

import logging
import mimetypes
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppException, ForbiddenError, NotFoundError
from app.models.base import not_deleted
from app.models.instance import Instance, InstanceStatus
from app.services.nfs_mount import NFSMountError, remote_fs

logger = logging.getLogger(__name__)

BLOCKED_SEGMENTS = frozenset({
    "credentials",
    "node_modules",
    ".env",
    "temp",
})

MAX_PREVIEW_BYTES = 1_048_576  # 1 MB

TEXT_MIME_PREFIXES = ("text/", "application/json", "application/xml", "application/yaml")

_DEFAULT_ROOT = ".openclaw"


def get_allowed_root(runtime: str) -> str:
    from app.services.runtime.registries.runtime_registry import RUNTIME_REGISTRY
    spec = RUNTIME_REGISTRY.get(runtime)
    if spec:
        return spec.config_rel_path.split("/")[0]
    return _DEFAULT_ROOT


def _validate_path(rel_path: str, allowed_root: str = _DEFAULT_ROOT) -> str:
    if ".." in rel_path.split("/"):
        raise AppException(
            code=40000,
            message="非法路径",
            message_key="errors.enterprise_files.invalid_path",
            status_code=400,
        )
    if not rel_path or rel_path == "/":
        return allowed_root
    if not rel_path.startswith(allowed_root):
        rel_path = f"{allowed_root}/{rel_path.lstrip('/')}"
    for segment in rel_path.split("/"):
        if segment in BLOCKED_SEGMENTS:
            raise ForbiddenError(
                message="无权访问此路径",
                message_key="errors.enterprise_files.blocked_path",
            )
    return rel_path


def _ts_to_iso(ts: float) -> str | None:
    if not ts:
        return None
    return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()


def _guess_mime(name: str) -> str:
    mime, _ = mimetypes.guess_type(name)
    return mime or "application/octet-stream"


def _is_text_mime(mime: str) -> bool:
    return any(mime.startswith(p) for p in TEXT_MIME_PREFIXES)


def _filter_blocked(items: list[dict]) -> list[dict]:
    return [i for i in items if i["name"] not in BLOCKED_SEGMENTS]


async def _get_instance(instance_id: str, org_id: str, db: AsyncSession) -> Instance:
    result = await db.execute(
        select(Instance).where(
            Instance.id == instance_id,
            Instance.org_id == org_id,
            not_deleted(Instance),
        )
    )
    instance = result.scalar_one_or_none()
    if not instance:
        raise NotFoundError("实例不存在", "errors.instance.not_found")
    return instance


async def _get_running_instance(instance_id: str, db: AsyncSession) -> Instance:
    """获取实例（不检查 org_id，权限由 API 层保证）。"""
    result = await db.execute(
        select(Instance).where(Instance.id == instance_id, not_deleted(Instance))
    )
    instance = result.scalar_one_or_none()
    if not instance:
        raise NotFoundError("实例不存在", "errors.instance.not_found")
    if instance.status != InstanceStatus.running:
        raise AppException(
            code=50300,
            message="实例未运行，无法浏览文件",
            message_key="errors.enterprise_files.instance_not_running",
            status_code=503,
        )
    return instance


async def list_browsable_agents(org_id: str, db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(Instance).where(
            Instance.org_id == org_id,
            not_deleted(Instance),
        ).order_by(Instance.name)
    )
    instances = result.scalars().all()
    return [
        {
            "instance_id": inst.id,
            "name": inst.agent_display_name or inst.name,
            "slug": inst.slug,
            "agent_label": inst.agent_label,
            "agent_theme_color": inst.agent_theme_color,
            "status": inst.status,
            "is_browsable": inst.status == InstanceStatus.running,
        }
        for inst in instances
    ]


async def list_files(
    instance_id: str, rel_path: str, org_id: str, db: AsyncSession,
) -> dict:
    instance = await _get_instance(instance_id, org_id, db)
    safe_path = _validate_path(rel_path, get_allowed_root(instance.runtime))

    if instance.status != InstanceStatus.running:
        raise AppException(
            code=50300,
            message="实例未运行，无法浏览文件",
            message_key="errors.enterprise_files.instance_not_running",
            status_code=503,
        )

    try:
        async with remote_fs(instance, db) as fs:
            items = await fs.list_dir(safe_path)
    except NFSMountError:
        raise AppException(
            code=50300,
            message="无法连接到实例",
            message_key="errors.enterprise_files.instance_not_running",
            status_code=503,
        )

    if items is None:
        raise NotFoundError("目录不存在", "errors.enterprise_files.path_not_found")

    filtered = _filter_blocked(items)
    parts = safe_path.split("/")

    return {
        "instance_id": instance.id,
        "instance_name": instance.agent_display_name or instance.name,
        "path": safe_path,
        "breadcrumb": parts,
        "items": [
            {
                "name": item["name"],
                "is_dir": item["is_dir"],
                "size": item["size"],
                "mime_type": _guess_mime(item["name"]) if not item["is_dir"] else None,
                "modified_at": _ts_to_iso(item["modified_at"]),
            }
            for item in filtered
        ],
    }


async def read_file_content(
    instance_id: str, rel_path: str, org_id: str, db: AsyncSession,
) -> dict:
    instance = await _get_instance(instance_id, org_id, db)
    safe_path = _validate_path(rel_path, get_allowed_root(instance.runtime))

    if instance.status != InstanceStatus.running:
        raise AppException(
            code=50300,
            message="实例未运行，无法浏览文件",
            message_key="errors.enterprise_files.instance_not_running",
            status_code=503,
        )

    try:
        async with remote_fs(instance, db) as fs:
            stat = await fs.file_stat(safe_path)
            if stat is None:
                raise NotFoundError("文件不存在", "errors.enterprise_files.path_not_found")

            if stat["size"] > MAX_PREVIEW_BYTES:
                return {
                    "path": safe_path,
                    "mime_type": stat["mime_type"],
                    "size": stat["size"],
                    "content": None,
                    "truncated": True,
                }

            mime = stat["mime_type"]
            if mime == "application/octet-stream":
                mime = _guess_mime(safe_path.rsplit("/", 1)[-1])
            if not _is_text_mime(mime):
                return {
                    "path": safe_path,
                    "mime_type": mime,
                    "size": stat["size"],
                    "content": None,
                    "truncated": False,
                    "binary": True,
                }

            content = await fs.read_text(safe_path)
            return {
                "path": safe_path,
                "mime_type": mime,
                "size": stat["size"],
                "content": content,
                "truncated": False,
            }
    except NFSMountError:
        raise AppException(
            code=50300,
            message="无法连接到实例",
            message_key="errors.enterprise_files.instance_not_running",
            status_code=503,
        )


async def download_file(
    instance_id: str, rel_path: str, org_id: str, db: AsyncSession,
) -> tuple[str, str]:
    """Return (content, filename) for download."""
    instance = await _get_instance(instance_id, org_id, db)
    safe_path = _validate_path(rel_path, get_allowed_root(instance.runtime))

    if instance.status != InstanceStatus.running:
        raise AppException(
            code=50300,
            message="实例未运行，无法浏览文件",
            message_key="errors.enterprise_files.instance_not_running",
            status_code=503,
        )

    try:
        async with remote_fs(instance, db) as fs:
            content = await fs.read_text(safe_path)
            if content is None:
                raise NotFoundError("文件不存在", "errors.enterprise_files.path_not_found")
            filename = safe_path.rsplit("/", 1)[-1]
            return content, filename
    except NFSMountError:
        raise AppException(
            code=50300,
            message="无法连接到实例",
            message_key="errors.enterprise_files.instance_not_running",
            status_code=503,
        )


# ---------------------------------------------------------------------------
# Instance-level functions (permission checked at API layer, no org_id)
# ---------------------------------------------------------------------------


async def list_files_for_instance(
    instance_id: str, rel_path: str, db: AsyncSession,
) -> dict:
    instance = await _get_running_instance(instance_id, db)
    safe_path = _validate_path(rel_path, get_allowed_root(instance.runtime))

    try:
        async with remote_fs(instance, db) as fs:
            items = await fs.list_dir(safe_path)
    except NFSMountError:
        raise AppException(
            code=50300, message="无法连接到实例",
            message_key="errors.enterprise_files.instance_not_running", status_code=503,
        )

    if items is None:
        raise NotFoundError("目录不存在", "errors.enterprise_files.path_not_found")

    filtered = _filter_blocked(items)
    parts = safe_path.split("/")
    return {
        "instance_id": instance.id,
        "instance_name": instance.agent_display_name or instance.name,
        "path": safe_path,
        "breadcrumb": parts,
        "items": [
            {
                "name": item["name"],
                "is_dir": item["is_dir"],
                "size": item["size"],
                "mime_type": _guess_mime(item["name"]) if not item["is_dir"] else None,
                "modified_at": _ts_to_iso(item["modified_at"]),
            }
            for item in filtered
        ],
    }


async def read_file_for_instance(
    instance_id: str, rel_path: str, db: AsyncSession,
) -> dict:
    instance = await _get_running_instance(instance_id, db)
    safe_path = _validate_path(rel_path, get_allowed_root(instance.runtime))

    try:
        async with remote_fs(instance, db) as fs:
            stat = await fs.file_stat(safe_path)
            if stat is None:
                raise NotFoundError("文件不存在", "errors.enterprise_files.path_not_found")

            if stat["size"] > MAX_PREVIEW_BYTES:
                return {
                    "path": safe_path, "mime_type": stat["mime_type"],
                    "size": stat["size"], "content": None, "truncated": True,
                }

            mime = stat["mime_type"]
            if mime == "application/octet-stream":
                mime = _guess_mime(safe_path.rsplit("/", 1)[-1])
            if not _is_text_mime(mime):
                return {
                    "path": safe_path, "mime_type": mime,
                    "size": stat["size"], "content": None, "truncated": False, "binary": True,
                }

            content = await fs.read_text(safe_path)
            return {
                "path": safe_path, "mime_type": mime,
                "size": stat["size"], "content": content, "truncated": False,
            }
    except NFSMountError:
        raise AppException(
            code=50300, message="无法连接到实例",
            message_key="errors.enterprise_files.instance_not_running", status_code=503,
        )


async def download_file_for_instance(
    instance_id: str, rel_path: str, db: AsyncSession,
) -> tuple[bytes, str, str]:
    """Return (raw_bytes, filename, mime_type) for download."""
    instance = await _get_running_instance(instance_id, db)
    safe_path = _validate_path(rel_path, get_allowed_root(instance.runtime))

    try:
        async with remote_fs(instance, db) as fs:
            stat = await fs.file_stat(safe_path)
            if stat is None:
                raise NotFoundError("文件不存在", "errors.enterprise_files.path_not_found")

            mime = stat.get("mime_type") or "application/octet-stream"
            if mime == "application/octet-stream":
                mime = _guess_mime(safe_path.rsplit("/", 1)[-1])

            data = await fs.read_binary(safe_path)
            if data is None:
                raise NotFoundError("文件不存在", "errors.enterprise_files.path_not_found")

            filename = safe_path.rsplit("/", 1)[-1]
            return data, filename, mime
    except NFSMountError:
        raise AppException(
            code=50300, message="无法连接到实例",
            message_key="errors.enterprise_files.instance_not_running", status_code=503,
        )


async def write_file_content(
    instance_id: str, rel_path: str, content: str, db: AsyncSession,
) -> dict:
    instance = await _get_running_instance(instance_id, db)
    safe_path = _validate_path(rel_path, get_allowed_root(instance.runtime))

    try:
        async with remote_fs(instance, db) as fs:
            await fs.write_text(safe_path, content)
            return {"path": safe_path, "size": len(content.encode("utf-8"))}
    except NFSMountError:
        raise AppException(
            code=50300, message="无法连接到实例",
            message_key="errors.enterprise_files.instance_not_running", status_code=503,
        )


async def write_file_content_for_org(
    instance_id: str, rel_path: str, content: str, org_id: str, db: AsyncSession,
) -> dict:
    """写入文件（企业空间入口，含组织归属校验）。"""
    instance = await _get_instance(instance_id, org_id, db)
    safe_path = _validate_path(rel_path, get_allowed_root(instance.runtime))

    if instance.status != InstanceStatus.running:
        raise AppException(
            code=50300,
            message="实例未运行，无法写入文件",
            message_key="errors.enterprise_files.instance_not_running",
            status_code=503,
        )

    try:
        async with remote_fs(instance, db) as fs:
            await fs.write_text(safe_path, content)
            return {"path": safe_path, "size": len(content.encode("utf-8"))}
    except NFSMountError:
        raise AppException(
            code=50300, message="无法连接到实例",
            message_key="errors.enterprise_files.instance_not_running", status_code=503,
        )
