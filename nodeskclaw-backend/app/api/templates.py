"""Workspace template CRUD API."""

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import and_, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.corridors import _check_workspace
from app.api.workspaces import broadcast_event
from app.core.deps import get_current_org, get_db
from app.models.base import not_deleted
from app.models.blackboard import Blackboard
from app.models.corridor import CorridorHex, HexConnection, ordered_pair
from app.models.instance import Instance
from app.models.workspace_agent import WorkspaceAgent
from app.models.workspace_template import WorkspaceTemplate
from app.services import corridor_router
from app.services import workspace_service
from app.services.workspace_template_collect import (
    collect_internal_template_payload,
    template_summary_from_specs,
)
from app.services.workspace_template_deploy_service import start_workspace_template_deploy

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
    visibility: str = "org_private"
    excluded_agent_indices: list[int] | None = None
    excluded_corridor_coords: list[list[int]] | None = None


class TemplateApplyRequest(BaseModel):
    target_workspace_id: str


class TemplateDeployRequest(BaseModel):
    workspace_name: str
    cluster_id: str
    selected_agent_indices: list[int] | None = None
    excluded_corridor_coords: list[list[int]] | None = None


def _row_summary(t: WorkspaceTemplate) -> dict:
    specs = t.agent_specs or []
    hs = t.human_specs or []
    if specs or hs:
        s = template_summary_from_specs(specs, hs)
        return {"agent_count": s["agent_count"], "human_count": s["human_count"], "agent_names": s["agent_names"]}
    topo = t.topology_snapshot or {}
    nodes = topo.get("nodes") or []
    agent_n = sum(1 for n in nodes if n.get("node_type") == "agent")
    human_n = sum(1 for n in nodes if n.get("node_type") == "human")
    return {
        "agent_count": agent_n,
        "human_count": human_n,
        "agent_names": [],
    }


@router.get("")
async def list_templates(
    visibility: str | None = Query(None),
    org_ctx=Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
    org_id = _org_id(org)
    q = select(WorkspaceTemplate).where(not_deleted(WorkspaceTemplate))

    if visibility == "org_private":
        q = q.where(WorkspaceTemplate.visibility == "org_private", WorkspaceTemplate.org_id == org_id)
    elif visibility == "public":
        q = q.where(WorkspaceTemplate.visibility == "public")
    else:
        q = q.where(
            or_(
                WorkspaceTemplate.visibility == "public",
                and_(WorkspaceTemplate.visibility == "org_private", WorkspaceTemplate.org_id == org_id),
            )
        )

    result = await db.execute(q.order_by(WorkspaceTemplate.created_at.desc()))
    items = result.scalars().all()
    rows = []
    for t in items:
        summ = _row_summary(t)
        rows.append({
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "is_preset": t.is_preset,
            "org_id": t.org_id,
            "visibility": t.visibility,
            "created_by": t.created_by,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "agent_count": summ["agent_count"],
            "human_count": summ["human_count"],
            "agent_names": summ["agent_names"],
            "can_deploy_from_template": bool(t.agent_specs),
        })
    return _ok(rows)


@router.post("")
async def create_template(
    body: TemplateCreateRequest,
    org_ctx=Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx

    collect_warnings: list[str] = []
    agent_specs: list = []
    human_specs: list = []
    source_workspace_id: str | None = None

    if body.workspace_id:
        await _check_workspace(body.workspace_id, org, db)
        bb_info = await workspace_service.get_blackboard(db, body.workspace_id)
        gene_assignments = await _get_workspace_gene_assignments(db, body.workspace_id)
        try:
            agent_specs, human_specs, topology_snapshot, collect_warnings = (
                await collect_internal_template_payload(db, body.workspace_id, _org_id(org))
            )
            source_workspace_id = body.workspace_id
        except ValueError as e:
            raise _error(400, 40052, "errors.template.no_running_agents", str(e)) from e
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

    if body.excluded_agent_indices and agent_specs:
        excluded = set(body.excluded_agent_indices)
        excluded_coords = set()
        for i, s in enumerate(agent_specs):
            if i in excluded:
                excluded_coords.add((s.get("hex_q"), s.get("hex_r")))
        agent_specs = [s for i, s in enumerate(agent_specs) if i not in excluded]
        if excluded_coords and isinstance(topology_snapshot, dict):
            edges = topology_snapshot.get("edges") or []
            topology_snapshot = {
                **topology_snapshot,
                "edges": [
                    e for e in edges
                    if (e.get("a_q"), e.get("a_r")) not in excluded_coords
                    and (e.get("b_q"), e.get("b_r")) not in excluded_coords
                ],
            }

    if body.excluded_corridor_coords and isinstance(topology_snapshot, dict):
        excl_corridor_set = {(c[0], c[1]) for c in body.excluded_corridor_coords if len(c) >= 2}
        nodes = topology_snapshot.get("nodes") or []
        topology_snapshot = {
            **topology_snapshot,
            "nodes": [
                n for n in nodes
                if n.get("node_type") != "corridor"
                or (n.get("hex_q"), n.get("hex_r")) not in excl_corridor_set
            ],
            "edges": [
                e for e in (topology_snapshot.get("edges") or [])
                if (e.get("a_q"), e.get("a_r")) not in excl_corridor_set
                and (e.get("b_q"), e.get("b_r")) not in excl_corridor_set
            ],
        }

    t = WorkspaceTemplate(
        id=str(uuid.uuid4()),
        name=body.name,
        description=body.description,
        is_preset=False,
        topology_snapshot=topology_snapshot,
        blackboard_snapshot=blackboard_snapshot,
        gene_assignments=gene_assignments,
        org_id=_org_id(org),
        visibility=body.visibility,
        created_by=user.id if user else None,
        agent_specs=agent_specs,
        human_specs=human_specs,
        source_workspace_id=source_workspace_id,
    )
    db.add(t)
    await db.commit()
    await db.refresh(t)
    summ = template_summary_from_specs(t.agent_specs or [], t.human_specs or [])
    return _ok(
        {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "is_preset": t.is_preset,
            "topology_snapshot": t.topology_snapshot,
            "blackboard_snapshot": t.blackboard_snapshot,
            "gene_assignments": t.gene_assignments,
            "agent_specs": t.agent_specs,
            "human_specs": t.human_specs,
            "source_workspace_id": t.source_workspace_id,
            "org_id": t.org_id,
            "visibility": t.visibility,
            "created_by": t.created_by,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "agent_count": summ["agent_count"],
            "human_count": summ["human_count"],
            "collect_warnings": collect_warnings,
        }
    )


@router.get("/collect-preview")
async def collect_template_preview(
    workspace_id: str = Query(..., description="办公室 ID"),
    org_ctx=Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    _user, org = org_ctx
    await _check_workspace(workspace_id, org, db)
    try:
        agent_specs, human_specs, _topology_snapshot, collect_warnings = await collect_internal_template_payload(
            db, workspace_id, _org_id(org)
        )
    except ValueError as e:
        raise _error(400, 40052, "errors.template.no_running_agents", str(e)) from e
    summ = template_summary_from_specs(agent_specs, human_specs)

    full_topo = await corridor_router.get_topology(workspace_id, db)
    topo_snapshot = {
        "nodes": [
            {
                "hex_q": n.hex_q, "hex_r": n.hex_r,
                "node_type": n.node_type,
                "display_name": n.display_name or "",
                "entity_id": n.entity_id,
            }
            for n in full_topo.nodes
        ],
        "edges": [
            {
                "a_q": e.a_q, "a_r": e.a_r,
                "b_q": e.b_q, "b_r": e.b_r,
                "direction": e.direction,
                "auto_created": e.auto_created,
            }
            for e in full_topo.edges
        ],
    }

    return _ok({
        "agent_specs": agent_specs,
        "human_specs": human_specs,
        "collect_warnings": collect_warnings,
        "agent_count": summ["agent_count"],
        "human_count": summ["human_count"],
        "topology_snapshot": topo_snapshot,
    })


async def _get_workspace_gene_assignments(db: AsyncSession, workspace_id: str) -> list:
    from app.models.gene import Gene, InstanceGene
    from app.models.gene import InstanceGeneStatus

    result = await db.execute(
        select(Instance, WorkspaceAgent, InstanceGene, Gene)
        .join(WorkspaceAgent, (WorkspaceAgent.instance_id == Instance.id) & (WorkspaceAgent.deleted_at.is_(None)))
        .join(InstanceGene, Instance.id == InstanceGene.instance_id)
        .join(Gene, InstanceGene.gene_id == Gene.id)
        .where(
            WorkspaceAgent.workspace_id == workspace_id,
            Instance.deleted_at.is_(None),
            InstanceGene.status == InstanceGeneStatus.installed,
            InstanceGene.deleted_at.is_(None),
        )
    )
    rows = result.all()
    return [
        {
            "hex_q": wa.hex_q or 0,
            "hex_r": wa.hex_r or 0,
            "display_name": inst.agent_display_name or inst.name,
            "gene_slug": gene.slug,
        }
        for inst, wa, ig, gene in rows
    ]


@router.post("/{template_id}/deploy")
async def deploy_from_template(
    template_id: str,
    body: TemplateDeployRequest,
    org_ctx=Depends(get_current_org),
    db: AsyncSession = Depends(get_db),
):
    user, org = org_ctx
    org_id = _org_id(org)
    result = await db.execute(
        select(WorkspaceTemplate).where(
            WorkspaceTemplate.id == template_id,
            not_deleted(WorkspaceTemplate),
        )
    )
    t = result.scalar_one_or_none()
    if t is None:
        raise _error(404, 40450, "errors.template.not_found", "模板不存在")
    if t.visibility == "org_private" and t.org_id != org_id:
        raise _error(403, 40350, "errors.template.access_denied", "无权使用该模板")
    try:
        out = await start_workspace_template_deploy(
            db,
            template=t,
            workspace_name=body.workspace_name.strip(),
            cluster_id=body.cluster_id,
            user=user,
            org_id=org_id,
            selected_agent_indices=body.selected_agent_indices,
            excluded_corridor_coords=body.excluded_corridor_coords,
        )
    except ValueError as e:
        raise _error(400, 40053, "errors.template.deploy_invalid", str(e)) from e
    return _ok(out)


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
    summ = template_summary_from_specs(t.agent_specs or [], t.human_specs or [])
    return _ok(
        {
            "id": t.id,
            "name": t.name,
            "description": t.description,
            "is_preset": t.is_preset,
            "topology_snapshot": t.topology_snapshot,
            "blackboard_snapshot": t.blackboard_snapshot,
            "gene_assignments": t.gene_assignments,
            "agent_specs": t.agent_specs,
            "human_specs": t.human_specs,
            "source_workspace_id": t.source_workspace_id,
            "org_id": t.org_id,
            "visibility": t.visibility,
            "created_by": t.created_by,
            "created_at": t.created_at.isoformat() if t.created_at else None,
            "agent_count": summ["agent_count"],
            "human_count": summ["human_count"],
            "can_deploy_from_template": bool(t.agent_specs),
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
        select(Instance, WorkspaceAgent)
        .join(
            WorkspaceAgent,
            (WorkspaceAgent.instance_id == Instance.id) & (WorkspaceAgent.deleted_at.is_(None)),
        )
        .where(
            WorkspaceAgent.workspace_id == ws_id,
            Instance.deleted_at.is_(None),
        )
        .order_by(Instance.created_at.asc())
    )
    ws_agents = list(ws_agents_result.all())

    for i, node in enumerate(agent_nodes):
        hex_q = node.get("hex_q", 0)
        hex_r = node.get("hex_r", 0)
        if i < len(ws_agents):
            inst, wa = ws_agents[i]
            wa.hex_q = hex_q
            wa.hex_r = hex_r
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
        for inst, wa in ws_agents:
            if wa.hex_q == hex_q and wa.hex_r == hex_r:
                try:
                    from app.services import gene_service
                    await gene_service.install_gene(db, inst.id, gene_slug)
                except Exception as e:
                    logger.warning("Apply template: install gene %s on instance %s failed: %s", gene_slug, inst.id, e)
                break

    broadcast_event(ws_id, "template:applied", {"template_id": template_id})
    return _ok(message="模板已应用")
