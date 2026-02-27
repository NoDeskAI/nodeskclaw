"""Workspace template CRUD API."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.corridors import _check_workspace
from app.api.workspaces import broadcast_event
from app.core.deps import get_current_org, get_db
from app.models.base import not_deleted
from app.models.blackboard import Blackboard
from app.models.corridor import CorridorHex, HexConnection, ordered_pair
from app.models.instance import Instance
from app.models.workspace_template import WorkspaceTemplate
from app.services import corridor_router
from app.services import workspace_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/templates", tags=["templates"])


def _ok(data=None, message: str = "success"):
    return {"code": 0, "message": message, "data": data}


def _org_id(org) -> str:
    return org.id if hasattr(org, "id") else org.get("org_id", "")


def _error(status_code: int, error_code: int, message_key: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=status_code,
        detail={"error_code": error_code, "message_key": message_key, "message": message},
    )


class TemplateCreateRequest(BaseModel):
    name: str
    description: str = ""
    workspace_id: str | None = None
    topology_snapshot: dict | None = None
    blackboard_snapshot: dict | None = None
    gene_assignments: list | None = None


class TemplateApplyRequest(BaseModel):
    target_workspace_id: str


@router.get("")
async def list_templates(
    org_ctx=Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
    result = await db.execute(
        select(WorkspaceTemplate)
        .where(not_deleted(WorkspaceTemplate))
        .order_by(WorkspaceTemplate.created_at.desc())
    )
    items = result.scalars().all()
    rows = [
        {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "is_preset": t.is_preset,
            "created_by": t.created_by,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in items
    ]
    return _ok(rows)


@router.post("")
async def create_template(
    body: TemplateCreateRequest,
    org_ctx=Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx

    if body.workspace_id:
        await _check_workspace(body.workspace_id, org, db)
        topo = await corridor_router.get_topology(body.workspace_id, db)
        bb_info = await workspace_service.get_blackboard(db, body.workspace_id)
        gene_assignments = await _get_workspace_gene_assignments(db, body.workspace_id)

        topology_snapshot = {
            "nodes": [
                {
                    "hex_q": n.hex_q,
                    "hex_r": n.hex_r,
                    "node_type": n.node_type,
                    "entity_id": n.entity_id,
                    "display_name": n.display_name,
                    "extra": n.extra or {},
                }
                for n in topo.nodes
            ],
            "edges": [
                {
                    "a_q": e.a_q,
                    "a_r": e.a_r,
                    "b_q": e.b_q,
                    "b_r": e.b_r,
                    "direction": e.direction,
                    "auto_created": e.auto_created,
                }
                for e in topo.edges
            ],
        }
        blackboard_snapshot = (
            {"content": bb_info.content}
            if bb_info
            else {}
        )
    else:
        if body.topology_snapshot is None or body.blackboard_snapshot is None or body.gene_assignments is None:
            raise _error(400, 40051, "errors.template.missing_fields", "手动创建模板需提供 topology_snapshot、blackboard_snapshot、gene_assignments")
        topology_snapshot = body.topology_snapshot
        blackboard_snapshot = body.blackboard_snapshot
        gene_assignments = body.gene_assignments or []

    t = WorkspaceTemplate(
        id=str(uuid.uuid4()),
        name=body.name,
        description=body.description,
        is_preset=False,
        topology_snapshot=topology_snapshot,
        blackboard_snapshot=blackboard_snapshot,
        gene_assignments=gene_assignments,
        created_by=user.id if user else None,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    return _ok(
        {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "is_preset": t.is_preset,
            "topology_snapshot": t.topology_snapshot,
            "blackboard_snapshot": t.blackboard_snapshot,
            "gene_assignments": t.gene_assignments,
            "created_by": t.created_by,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
    )


async def _get_workspace_gene_assignments(db: AsyncSession, workspace_id: str) -> list:
    from app.models.gene import Gene, InstanceGene
    from app.models.gene import InstanceGeneStatus

    result = await db.execute(
        select(Instance, InstanceGene, Gene)
        .join(InstanceGene, Instance.id == InstanceGene.instance_id)
        .join(Gene, InstanceGene.gene_id == Gene.id)
        .where(
            Instance.workspace_id == workspace_id,
            Instance.deleted_at.is_(None),
            InstanceGene.status == InstanceGeneStatus.installed,
            InstanceGene.deleted_at.is_(None),
        )
    )
    rows = result.all()
    return [
        {
            "hex_q": inst.hex_position_q or 0,
            "hex_r": inst.hex_position_r or 0,
            "display_name": inst.agent_display_name or inst.name,
            "gene_slug": gene.slug,
        }
        for inst, ig, gene in rows
    ]


@router.get("/{template_id}")
async def get_template(
    template_id: str,
    org_ctx=Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WorkspaceTemplate).where(
            WorkspaceTemplate.id == template_id,
            not_deleted(WorkspaceTemplate),
        )
    )
    t = result.scalar_one_or_none()
    if t is None:
        raise _error(404, 40450, "errors.template.not_found", "模板不存在")
    return _ok(
        {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "is_preset": t.is_preset,
            "topology_snapshot": t.topology_snapshot,
            "blackboard_snapshot": t.blackboard_snapshot,
            "gene_assignments": t.gene_assignments,
            "created_by": t.created_by,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
    )


@router.delete("/{template_id}")
async def delete_template(
    template_id: str,
    org_ctx=Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(WorkspaceTemplate).where(
            WorkspaceTemplate.id == template_id,
            not_deleted(WorkspaceTemplate),
        )
    )
    t = result.scalar_one_or_none()
    if t is None:
        raise _error(404, 40450, "errors.template.not_found", "模板不存在")
    if t.is_preset:
        raise _error(400, 40050, "errors.template.cannot_delete_preset", "预设模板不可删除")
    t.soft_delete()
    await db.commit()
    return _ok(message="已删除")


@router.post("/{template_id}/apply")
async def apply_template(
    template_id: str,
    body: TemplateApplyRequest,
    org_ctx=Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
    await _check_workspace(body.target_workspace_id, org, db)

    result = await db.execute(
        select(WorkspaceTemplate).where(
            WorkspaceTemplate.id == template_id,
            not_deleted(WorkspaceTemplate),
        )
    )
    t = result.scalar_one_or_none()
    if t is None:
        raise _error(404, 40450, "errors.template.not_found", "模板不存在")

    ws_id = body.target_workspace_id
    topo = t.topology_snapshot or {}
    bb = t.blackboard_snapshot or {}
    genes = t.gene_assignments or []

    nodes = topo.get("nodes", [])
    edges = topo.get("edges", [])

    agent_nodes = [n for n in nodes if n.get("node_type") == "agent"]
    corridor_nodes = [n for n in nodes if n.get("node_type") == "corridor"]

    ws_agents_result = await db.execute(
        select(Instance).where(
            Instance.workspace_id == ws_id,
            Instance.deleted_at.is_(None),
        ).order_by(Instance.created_at.asc())
    )
    ws_agents = list(ws_agents_result.scalars().all())

    for i, node in enumerate(agent_nodes):
        hex_q = node.get("hex_q", 0)
        hex_r = node.get("hex_r", 0)
        if i < len(ws_agents):
            inst = ws_agents[i]
            inst.hex_position_q = hex_q
            inst.hex_position_r = hex_r
            inst.agent_display_name = node.get("display_name") or inst.agent_display_name

    conn_result = await db.execute(
        select(HexConnection).where(
            HexConnection.workspace_id == ws_id,
            not_deleted(HexConnection),
        )
    )
    for c in conn_result.scalars().all():
        c.soft_delete()

    corridor_result = await db.execute(
        select(CorridorHex).where(
            CorridorHex.workspace_id == ws_id,
            not_deleted(CorridorHex),
        )
    )
    for ch in corridor_result.scalars().all():
        ch.soft_delete()

    for node in corridor_nodes:
        ch = CorridorHex(
            id=str(uuid.uuid4()),
            workspace_id=ws_id,
            hex_q=node.get("hex_q", 0),
            hex_r=node.get("hex_r", 0),
            display_name=node.get("display_name", ""),
            created_by=user.id if user else None,
        )
        db.add(ch)

    await db.flush()

    for edge in edges:
        aq, ar, bq, br = ordered_pair(
            edge.get("a_q", 0), edge.get("a_r", 0),
            edge.get("b_q", 0), edge.get("b_r", 0),
        )
        conn = HexConnection(
            id=str(uuid.uuid4()),
            workspace_id=ws_id,
            hex_a_q=aq,
            hex_a_r=ar,
            hex_b_q=bq,
            hex_b_r=br,
            direction=edge.get("direction", "both"),
            auto_created=edge.get("auto_created", False),
            created_by=user.id if user else None,
        )
        db.add(conn)

    bb_result = await db.execute(
        select(Blackboard).where(Blackboard.workspace_id == ws_id)
    )
    bb_row = bb_result.scalar_one_or_none()
    if bb_row and "content" in bb:
        bb_row.content = bb["content"]

    await db.commit()

    for ga in genes:
        hex_q = ga.get("hex_q")
        hex_r = ga.get("hex_r")
        gene_slug = ga.get("gene_slug")
        if hex_q is None or hex_r is None or not gene_slug:
            continue
        for inst in ws_agents:
            if inst.hex_position_q == hex_q and inst.hex_position_r == hex_r:
                try:
                    from app.services import gene_service
                    await gene_service.install_gene(db, inst.id, gene_slug)
                except Exception as e:
                    logger.warning("Apply template: install gene %s on instance %s failed: %s", gene_slug, inst.id, e)
                break

    broadcast_event(ws_id, "template:applied", {"template_id": template_id})
    return _ok(message="模板已应用")
