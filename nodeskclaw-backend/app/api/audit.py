"""CE 操作审计日志查询与导出 API。"""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db, require_org_admin
from app.models.operation_audit_log import OperationAuditLog
from app.models.user import User
from app.schemas.common import PaginatedResponse, Pagination

router = APIRouter()


def _build_query(
    org_id: str,
    action: str | None,
    target_type: str | None,
    from_time: datetime | None,
    to_time: datetime | None,
):
    q = select(OperationAuditLog).where(OperationAuditLog.org_id == org_id)

    if action:
        q = q.where(OperationAuditLog.action.ilike(f"%{action}%"))
    if target_type:
        q = q.where(OperationAuditLog.target_type == target_type)
    if from_time:
        q = q.where(OperationAuditLog.created_at >= from_time)
    if to_time:
        q = q.where(OperationAuditLog.created_at <= to_time)

    return q


async def _enrich_actor_names(
    db: AsyncSession,
    rows: list[OperationAuditLog],
) -> dict[str, str]:
    user_ids = {r.actor_id for r in rows if r.actor_type == "user" and not r.actor_name}
    if not user_ids:
        return {}
    result = await db.execute(select(User.id, User.name).where(User.id.in_(user_ids)))
    return {uid: uname for uid, uname in result.all()}


def _serialize(row: OperationAuditLog, name_map: dict[str, str] | None = None) -> dict:
    actor_name = row.actor_name
    if not actor_name and name_map:
        actor_name = name_map.get(row.actor_id)

    return {
        "id": row.id,
        "org_id": row.org_id,
        "workspace_id": row.workspace_id,
        "action": row.action,
        "target_type": row.target_type,
        "target_id": row.target_id,
        "actor_type": row.actor_type,
        "actor_id": row.actor_id,
        "actor_name": actor_name,
        "details": row.details,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


@router.get("/{org_id}/audit-logs")
async def list_audit_logs(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: tuple = Depends(require_org_admin),
    action: str | None = Query(None),
    target_type: str | None = Query(None),
    from_time: datetime | None = Query(None),
    to_time: datetime | None = Query(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    base = _build_query(org_id, action, target_type, from_time, to_time)

    count_q = select(func.count()).select_from(base.subquery())
    total = (await db.execute(count_q)).scalar() or 0

    rows_q = base.order_by(OperationAuditLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    rows = (await db.execute(rows_q)).scalars().all()

    name_map = await _enrich_actor_names(db, rows)

    return PaginatedResponse(
        data=[_serialize(r, name_map) for r in rows],
        pagination=Pagination(page=page, page_size=page_size, total=total),
    )


@router.get("/{org_id}/audit-logs/export")
async def export_audit_logs(
    org_id: str,
    db: AsyncSession = Depends(get_db),
    _auth: tuple = Depends(require_org_admin),
    action: str | None = Query(None),
    target_type: str | None = Query(None),
    from_time: datetime | None = Query(None),
    to_time: datetime | None = Query(None),
    format: str = Query("json", pattern="^(json|csv)$"),
    limit: int = Query(5000, ge=1, le=50000),
):
    base = _build_query(org_id, action, target_type, from_time, to_time)
    rows_q = base.order_by(OperationAuditLog.created_at.desc()).limit(limit)
    rows = (await db.execute(rows_q)).scalars().all()

    name_map = await _enrich_actor_names(db, rows)
    data = [_serialize(r, name_map) for r in rows]

    if format == "csv":
        return _csv_response(data)
    return _json_response(data)


_CSV_FIELDS = [
    "id", "org_id", "workspace_id", "action", "target_type",
    "target_id", "actor_type", "actor_id", "actor_name", "details", "created_at",
]


def _csv_response(data: list[dict]) -> StreamingResponse:
    buf = io.StringIO()
    writer = csv.DictWriter(buf, fieldnames=_CSV_FIELDS)
    writer.writeheader()
    for row in data:
        row_copy = dict(row)
        if row_copy.get("details") is not None:
            row_copy["details"] = json.dumps(row_copy["details"], ensure_ascii=False)
        writer.writerow(row_copy)
    buf.seek(0)
    return StreamingResponse(
        buf,
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=audit_logs.csv"},
    )


def _json_response(data: list[dict]) -> StreamingResponse:
    content = json.dumps(data, ensure_ascii=False, indent=2)
    return StreamingResponse(
        io.BytesIO(content.encode("utf-8")),
        media_type="application/json",
        headers={"Content-Disposition": "attachment; filename=audit_logs.json"},
    )
