"""Collect agent_specs / human_specs / topology_snapshot when saving a workspace template."""

import logging
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import not_deleted
from app.models.gene import Gene, InstanceGene, InstanceGeneStatus
from app.models.instance import Instance, InstanceStatus
from app.models.instance_mcp_server import InstanceMcpServer
from app.models.workspace_agent import WorkspaceAgent
from app.models.user_llm_config import UserLlmConfig
from app.services import corridor_router

logger = logging.getLogger(__name__)


async def collect_internal_template_payload(
    db: AsyncSession,
    workspace_id: str,
    org_id: str,
) -> tuple[list[dict], list[dict], dict, list[str]]:
    """
    Returns (agent_specs, human_specs, topology_snapshot, warnings).
    Raises ValueError if no running agents.
    """
    warnings: list[str] = []

    wa_result = await db.execute(
        select(WorkspaceAgent, Instance)
        .join(Instance, WorkspaceAgent.instance_id == Instance.id)
        .where(
            WorkspaceAgent.workspace_id == workspace_id,
            WorkspaceAgent.deleted_at.is_(None),
            Instance.deleted_at.is_(None),
            Instance.status == InstanceStatus.running,
        )
    )
    rows = list(wa_result.all())
    if not rows:
        raise ValueError("工作区至少需要 1 个运行中的 Agent 才能保存为模板")

    agent_specs: list[dict] = []
    for wa, inst in rows:
        gene_rows = await db.execute(
            select(Gene.slug)
            .join(InstanceGene, InstanceGene.gene_id == Gene.id)
            .where(
                InstanceGene.instance_id == inst.id,
                InstanceGene.status == InstanceGeneStatus.installed,
                InstanceGene.deleted_at.is_(None),
                not_deleted(Gene),
            )
        )
        gene_slugs = [r[0] for r in gene_rows.all()]

        mcp_result = await db.execute(
            select(InstanceMcpServer).where(
                InstanceMcpServer.instance_id == inst.id,
                InstanceMcpServer.is_active.is_(True),
                InstanceMcpServer.source != "gene",
                not_deleted(InstanceMcpServer),
            )
        )
        mcp_servers: list[dict] = []
        for m in mcp_result.scalars().all():
            mcp_servers.append({
                "name": m.name,
                "transport": m.transport,
                "url": m.url,
                "command": m.command,
                "args": m.args if isinstance(m.args, dict) else (m.args or {}),
                "source": m.source,
            })

        llm_providers = await _llm_providers_snapshot(db, inst, org_id)

        raw_llm = inst.llm_providers
        if raw_llm is None and llm_providers:
            pass

        agent_specs.append({
            "hex_q": wa.hex_q,
            "hex_r": wa.hex_r,
            "display_name": wa.display_name or inst.name,
            "label": wa.label,
            "runtime": inst.runtime,
            "compute_provider": inst.compute_provider,
            "resources": {
                "cpu_request": inst.cpu_request,
                "cpu_limit": inst.cpu_limit,
                "mem_request": inst.mem_request,
                "mem_limit": inst.mem_limit,
                "storage_size": inst.storage_size,
            },
            "llm_providers": llm_providers,
            "gene_slugs": gene_slugs,
            "mcp_servers": mcp_servers,
        })

        if inst.compute_provider == "docker":
            warnings.append(f"实例「{inst.name}」为 Docker 部署，已纳入模板")

    topo = await corridor_router.get_topology(workspace_id, db)
    human_specs: list[dict] = []
    corridor_nodes: list[dict] = []
    for n in topo.nodes:
        if n.node_type == "human":
            human_specs.append({
                "hex_q": n.hex_q,
                "hex_r": n.hex_r,
                "display_name": n.display_name or "",
                "label": (n.extra or {}).get("channel_type") or "",
            })
        elif n.node_type in ("corridor", "blackboard"):
            corridor_nodes.append({
                "hex_q": n.hex_q,
                "hex_r": n.hex_r,
                "node_type": n.node_type,
                "display_name": n.display_name or "",
            })

    topology_snapshot = {
        "nodes": corridor_nodes,
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

    return agent_specs, human_specs, topology_snapshot, warnings


async def _llm_providers_snapshot(db: AsyncSession, inst: Instance, org_id: str) -> list[dict[str, Any]]:
    raw = inst.llm_providers
    if not raw:
        return []
    providers: list[str] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, str):
                providers.append(item)
            elif isinstance(item, dict) and item.get("provider"):
                providers.append(str(item["provider"]))
    out: list[dict[str, Any]] = []
    for prov in providers:
        r = await db.execute(
            select(UserLlmConfig).where(
                UserLlmConfig.user_id == inst.created_by,
                UserLlmConfig.org_id == org_id,
                UserLlmConfig.provider == prov,
                not_deleted(UserLlmConfig),
            )
        )
        ucfg = r.scalar_one_or_none()
        models = ucfg.selected_models if ucfg else None
        out.append({"provider": prov, "models": models or []})
    return out


def template_summary_from_specs(agent_specs: list, human_specs: list) -> dict[str, Any]:
    return {
        "agent_count": len(agent_specs or []),
        "human_count": len(human_specs or []),
        "agent_names": [a.get("display_name") or "" for a in (agent_specs or [])],
    }
