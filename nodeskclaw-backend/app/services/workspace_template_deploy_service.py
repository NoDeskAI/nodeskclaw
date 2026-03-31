"""Orchestrate workspace creation from internal template (multi-agent deploy)."""

from __future__ import annotations

import asyncio
import logging
import time
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import async_session_factory
from app.models.blackboard import Blackboard
from app.models.cluster import Cluster
from app.models.deploy_record import DeployRecord, DeployStatus
from app.models.instance_mcp_server import InstanceMcpServer
from app.models.org_llm_key import OrgLlmKey
from app.models.user import User
from app.models.workspace import Workspace
from app.models.workspace_deploy import WorkspaceDeploy
from app.models.workspace_template import WorkspaceTemplate
from app.models.base import not_deleted
from app.schemas.deploy import DeployRequest
from app.schemas.llm import LlmConfigItem
from app.schemas.workspace import AddAgentRequest, WorkspaceCreate
from app.services import deploy_service, workspace_service
from app.services.codex_provider import normalize_selected_models
from app.services.gene_service import install_gene_prerestart
from app.services.k8s.event_bus import event_bus
from app.services.registry_service import list_image_tags

logger = logging.getLogger(__name__)

_WS_DEPLOY_CHANNEL = "workspace_deploy_progress"


def _publish(deploy_id: str, event: str, data: dict[str, Any]) -> None:
    payload = {"workspace_deploy_id": deploy_id, "event": event, **data}
    event_bus.publish(_WS_DEPLOY_CHANNEL, payload)


async def _org_has_llm_key(db: AsyncSession, org_id: str, provider: str) -> bool:
    r = await db.execute(
        select(OrgLlmKey.id).where(
            OrgLlmKey.org_id == org_id,
            OrgLlmKey.provider == provider,
            OrgLlmKey.is_active.is_(True),
            OrgLlmKey.deleted_at.is_(None),
        ).limit(1)
    )
    return r.scalar_one_or_none() is not None


async def _build_llm_configs(
    db: AsyncSession, org_id: str, llm_providers: list[dict],
) -> list[LlmConfigItem]:
    items: list[LlmConfigItem] = []
    for entry in llm_providers or []:
        prov = entry.get("provider") if isinstance(entry, dict) else None
        if not prov:
            continue
        ks = "org" if await _org_has_llm_key(db, org_id, prov) else "personal"
        models = entry.get("models") if isinstance(entry, dict) else None
        sm = normalize_selected_models(prov, models)
        items.append(LlmConfigItem(provider=prov, key_source=ks, selected_models=sm))
    return items


async def _resolve_image_version(db: AsyncSession, runtime: str) -> str:
    tags = await list_image_tags(db, runtime=runtime or "openclaw")
    if tags:
        return tags[0]["tag"]
    return "latest"


async def _wait_deploy_finished(deploy_id: str, timeout_s: float = 1200.0) -> tuple[bool, str | None]:
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        async with async_session_factory() as db:
            r = await db.execute(select(DeployRecord).where(DeployRecord.id == deploy_id))
            rec = r.scalar_one_or_none()
            if rec and rec.status in (DeployStatus.success, DeployStatus.failed):
                return rec.status == DeployStatus.success, rec.message
        await asyncio.sleep(3)
    return False, "部署等待超时"


async def _run_deploy_pipeline(workspace_deploy_id: str) -> None:
    try:
        await _run_deploy_pipeline_inner(workspace_deploy_id)
    except Exception as e:
        logger.exception("workspace template deploy failed: %s", workspace_deploy_id)
        async with async_session_factory() as db:
            r = await db.execute(
                select(WorkspaceDeploy).where(WorkspaceDeploy.id == workspace_deploy_id)
            )
            wd = r.scalar_one_or_none()
            if wd:
                wd.status = "failed"
                detail = dict(wd.progress_detail or {})
                detail["error"] = str(e)
                wd.progress_detail = detail
                await db.commit()
        _publish(workspace_deploy_id, "complete", {"status": "failed", "error": str(e)})


def _filter_topology_by_exclusions(
    topo_snap: dict,
    all_agent_specs: list[dict],
    selected_agent_specs: list[dict],
    excluded_corridor_coords: list[list[int]] | None,
) -> dict:
    """Filter topology nodes and edges based on user selections.

    Removes edges touching excluded agents and excluded corridors,
    then removes excluded corridor nodes from the node list.
    """
    selected_coords = {(s.get("hex_q"), s.get("hex_r")) for s in selected_agent_specs}
    excluded_agent_set = {
        (s.get("hex_q"), s.get("hex_r"))
        for s in all_agent_specs
        if (s.get("hex_q"), s.get("hex_r")) not in selected_coords
    }
    excluded_corridor_set = (
        {(c[0], c[1]) for c in excluded_corridor_coords if len(c) >= 2}
        if excluded_corridor_coords
        else set()
    )
    all_excluded = excluded_agent_set | excluded_corridor_set

    if not all_excluded:
        return topo_snap

    edges = [
        e for e in (topo_snap.get("edges") or [])
        if (e.get("a_q"), e.get("a_r")) not in all_excluded
        and (e.get("b_q"), e.get("b_r")) not in all_excluded
    ]

    nodes = [
        n for n in (topo_snap.get("nodes") or [])
        if n.get("node_type") != "corridor"
        or (n.get("hex_q"), n.get("hex_r")) not in excluded_corridor_set
    ]

    return {**topo_snap, "nodes": nodes, "edges": edges}


async def _run_deploy_pipeline_inner(workspace_deploy_id: str) -> None:
    async with async_session_factory() as db:
        r = await db.execute(
            select(WorkspaceDeploy).where(WorkspaceDeploy.id == workspace_deploy_id)
        )
        wd = r.scalar_one_or_none()
        if not wd:
            return
        tpl = (
            await db.execute(
                select(WorkspaceTemplate).where(
                    WorkspaceTemplate.id == wd.template_id,
                    not_deleted(WorkspaceTemplate),
                )
            )
        ).scalar_one_or_none()
        if not tpl:
            wd.status = "failed"
            await db.commit()
            return
        user = (await db.execute(select(User).where(User.id == wd.created_by))).scalar_one_or_none()
        if not user:
            wd.status = "failed"
            await db.commit()
            return
        deploy_user_id = user.id
        workspace_id = wd.workspace_id
        cfg = wd.config_snapshot or {}
        cluster_id = cfg.get("cluster_id")
        org_id = wd.org_id
        all_agent_specs: list[dict] = list(tpl.agent_specs or [])
        sel_indices = cfg.get("selected_agent_indices")
        if sel_indices is not None:
            valid = sorted(i for i in sel_indices if 0 <= i < len(all_agent_specs))
            agent_specs = [all_agent_specs[i] for i in valid] if valid else all_agent_specs
        else:
            agent_specs = all_agent_specs
        human_specs: list[dict] = list(tpl.human_specs or [])
        topo_snap = dict(tpl.topology_snapshot or {})
        bb_snap = tpl.blackboard_snapshot or {}
        excluded_corridor_coords: list[list[int]] | None = cfg.get("excluded_corridor_coords")

        has_agent_exclusions = sel_indices is not None and len(agent_specs) < len(all_agent_specs)
        has_corridor_exclusions = bool(excluded_corridor_coords)
        if has_agent_exclusions or has_corridor_exclusions:
            topo_snap = _filter_topology_by_exclusions(
                topo_snap, all_agent_specs, agent_specs,
                excluded_corridor_coords,
            )

        wd.status = "deploying"
        await db.commit()

    if not workspace_id:
        return

    _publish(workspace_deploy_id, "phase", {"phase": "blackboard", "message": "应用黑板内容"})

    async with async_session_factory() as db:
        if "content" in bb_snap:
            bb_row = (
                await db.execute(
                    select(Blackboard).where(
                        Blackboard.workspace_id == workspace_id,
                        Blackboard.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if bb_row:
                bb_row.content = bb_snap["content"]
                await db.commit()

    _publish(workspace_deploy_id, "phase", {"phase": "deploy_agents", "message": "正在部署 Agent"})

    instance_by_index: dict[int, str] = {}
    deploy_ids: dict[int, str] = {}
    errors: dict[int, str] = {}

    sem = asyncio.Semaphore(3)

    async def deploy_one(idx: int, spec: dict) -> None:
        nonlocal instance_by_index, deploy_ids, errors
        name_base = spec.get("display_name") or f"agent-{idx}"
        unique_name = f"{name_base}-{uuid.uuid4().hex[:6]}"
        resources = spec.get("resources") or {}
        runtime = spec.get("runtime") or "openclaw"
        async with sem:
            _publish(
                workspace_deploy_id, "agent_progress",
                {"display_name": name_base, "status": "deploying", "index": idx},
            )
            last_err: str | None = None
            for attempt in range(2):
                attempt_name = unique_name if attempt == 0 else f"{unique_name}-r{attempt}"
                rec_deploy_id: str | None = None
                inst_uuid: str | None = None
                async with async_session_factory() as db_inner:
                    urow = await db_inner.execute(select(User).where(User.id == deploy_user_id))
                    deploy_user = urow.scalar_one_or_none()
                    if not deploy_user:
                        last_err = "用户不存在"
                        break
                    cluster = (
                        await db_inner.execute(
                            select(Cluster).where(
                                Cluster.id == cluster_id,
                                Cluster.deleted_at.is_(None),
                            )
                        )
                    ).scalar_one_or_none()
                    if not cluster:
                        last_err = "集群不存在"
                        break
                    spec_cp = spec.get("compute_provider") or "k8s"
                    if cluster.compute_provider != spec_cp:
                        last_err = (
                            f"集群类型 {cluster.compute_provider} 与模板 Agent 所需 {spec_cp} 不一致"
                        )
                        break
                    llm_items = await _build_llm_configs(
                        db_inner, org_id, spec.get("llm_providers") or [],
                    )
                    image_version = await _resolve_image_version(db_inner, runtime)
                    req = DeployRequest(
                        cluster_id=cluster_id,
                        name=attempt_name,
                        image_version=image_version,
                        cpu_request=resources.get("cpu_request", "500m"),
                        cpu_limit=resources.get("cpu_limit", "2000m"),
                        mem_request=resources.get("mem_request", "2Gi"),
                        mem_limit=resources.get("mem_limit", "2Gi"),
                        storage_size=resources.get("storage_size", "80Gi"),
                        llm_configs=llm_items or None,
                        runtime=runtime,
                    )
                    try:
                        dep_id, ctx = await deploy_service.deploy_instance(
                            req, deploy_user, db_inner, org_id=org_id,
                        )
                        rec_deploy_id = dep_id
                        inst_uuid = ctx.instance_id
                        task = asyncio.create_task(
                            deploy_service.execute_deploy_pipeline(ctx),
                            name=f"tpl-deploy-{dep_id}",
                        )
                        deploy_service.register_deploy_task(dep_id, task)
                    except Exception as e:
                        last_err = str(e)
                        logger.warning("deploy_instance failed: %s", e)
                        continue
                if not rec_deploy_id or not inst_uuid:
                    continue
                ok, msg = await _wait_deploy_finished(rec_deploy_id)
                if ok:
                    instance_by_index[idx] = inst_uuid
                    deploy_ids[idx] = rec_deploy_id
                    _publish(
                        workspace_deploy_id, "agent_progress",
                        {"display_name": name_base, "status": "success", "index": idx},
                    )
                    return
                last_err = msg or "部署失败"
            errors[idx] = last_err or "部署失败"
            _publish(
                workspace_deploy_id, "agent_progress",
                {
                    "display_name": name_base,
                    "status": "failed",
                    "index": idx,
                    "error": errors[idx],
                },
            )

    await asyncio.gather(*[deploy_one(i, s) for i, s in enumerate(agent_specs)])

    agents_progress = []
    for i, spec in enumerate(agent_specs):
        name_base = spec.get("display_name") or f"agent-{i}"
        if i in instance_by_index:
            agents_progress.append({
                "display_name": name_base,
                "instance_id": instance_by_index[i],
                "deploy_id": deploy_ids.get(i),
                "status": "success",
                "step": "deploy",
                "error": None,
                "retry_count": 0,
            })
        else:
            agents_progress.append({
                "display_name": name_base,
                "instance_id": None,
                "deploy_id": None,
                "status": "failed",
                "step": "deploy",
                "error": errors.get(i),
                "retry_count": 1,
            })

    async with async_session_factory() as db:
        r = await db.execute(
            select(WorkspaceDeploy).where(WorkspaceDeploy.id == workspace_deploy_id)
        )
        wd = r.scalar_one_or_none()
        if wd:
            wd.progress_detail = {
                "agents": agents_progress,
                "current_phase": "install_genes",
                "phases_completed": ["create_workspace", "deploy_agents"],
            }
            wd.completed_agents = sum(1 for a in agents_progress if a["status"] == "success")
            wd.failed_agents = sum(1 for a in agents_progress if a["status"] == "failed")
            await db.commit()

    _publish(workspace_deploy_id, "phase", {"phase": "install_genes", "message": "正在安装基因"})

    for i, spec in enumerate(agent_specs):
        if i not in instance_by_index:
            continue
        inst_id = instance_by_index[i]
        name_base = spec.get("display_name") or f"agent-{i}"
        _publish(
            workspace_deploy_id, "agent_progress",
            {"display_name": name_base, "status": "gene_install", "index": i},
        )
        for slug in spec.get("gene_slugs") or []:
            try:
                await install_gene_prerestart(inst_id, slug)
            except Exception as e:
                logger.warning("gene install skipped %s on %s: %s", slug, inst_id, e)
        async with async_session_factory() as db_mcp:
            for ms in spec.get("mcp_servers") or []:
                nm = ms.get("name")
                if not nm:
                    continue
                exists = await db_mcp.execute(
                    select(InstanceMcpServer.id).where(
                        InstanceMcpServer.instance_id == inst_id,
                        InstanceMcpServer.name == nm,
                        not_deleted(InstanceMcpServer),
                    ).limit(1)
                )
                if exists.scalar_one_or_none():
                    continue
                raw_args = ms.get("args")
                args_val = raw_args if isinstance(raw_args, dict) else {}
                db_mcp.add(
                    InstanceMcpServer(
                        id=str(uuid.uuid4()),
                        instance_id=inst_id,
                        name=nm,
                        transport=ms.get("transport") or "stdio",
                        command=ms.get("command"),
                        url=ms.get("url"),
                        args=args_val,
                        env={},
                        is_active=True,
                        source=ms.get("source") or "manual",
                    )
                )
            await db_mcp.commit()

    _publish(workspace_deploy_id, "phase", {"phase": "setup_topology", "message": "配置拓扑"})

    user_id = deploy_user_id
    for i, spec in enumerate(agent_specs):
        if i not in instance_by_index:
            continue
        inst_id = instance_by_index[i]
        name_base = spec.get("display_name") or f"agent-{i}"
        _publish(
            workspace_deploy_id, "agent_progress",
            {"display_name": name_base, "status": "add_workspace", "index": i},
        )
        async with async_session_factory() as db_add:
            try:
                await workspace_service.add_agent(
                    db_add,
                    workspace_id,
                    AddAgentRequest(
                        instance_id=inst_id,
                        display_name=spec.get("display_name"),
                        label=spec.get("label"),
                        hex_q=int(spec.get("hex_q", 0)),
                        hex_r=int(spec.get("hex_r", 0)),
                        install_gene_slugs=[],
                    ),
                    user_id,
                )
                _publish(
                    workspace_deploy_id, "agent_progress",
                    {"display_name": name_base, "status": "success", "index": i},
                )
            except Exception as e:
                logger.error("add_agent failed: %s", e)
                _publish(
                    workspace_deploy_id, "agent_progress",
                    {"display_name": name_base, "status": "add_workspace_failed", "error": str(e), "index": i},
                )

    async with async_session_factory() as db_topo:
        await workspace_service.apply_internal_deploy_topology(
            db_topo, workspace_id, user_id, topo_snap, human_specs,
        )

    success_n = len(instance_by_index)
    fail_n = len(agent_specs) - success_n
    final_status = "success" if fail_n == 0 else "partial_success"

    async with async_session_factory() as db:
        r = await db.execute(
            select(WorkspaceDeploy).where(WorkspaceDeploy.id == workspace_deploy_id)
        )
        wd = r.scalar_one_or_none()
        if wd:
            wd.status = final_status
            detail = dict(wd.progress_detail or {})
            detail["current_phase"] = "done"
            detail["phases_completed"] = [
                "create_workspace", "deploy_agents", "install_genes", "setup_topology",
            ]
            wd.progress_detail = detail
            await db.commit()

    _publish(
        workspace_deploy_id, "complete",
        {"status": final_status, "success_count": success_n, "failed_count": fail_n},
    )


async def start_workspace_template_deploy(
    db: AsyncSession,
    *,
    template: WorkspaceTemplate,
    workspace_name: str,
    cluster_id: str,
    user: User,
    org_id: str,
    selected_agent_indices: list[int] | None = None,
    excluded_corridor_coords: list[list[int]] | None = None,
) -> dict[str, str]:
    agent_specs = list(template.agent_specs or [])
    if not agent_specs:
        raise ValueError("该模板不支持一键部署（缺少 agent_specs）")

    if selected_agent_indices is not None:
        valid = [i for i in selected_agent_indices if 0 <= i < len(agent_specs)]
        if not valid:
            raise ValueError("至少选择一个 Agent 进行部署")
        agent_specs = [agent_specs[i] for i in sorted(valid)]

    providers = {s.get("compute_provider") or "k8s" for s in agent_specs}
    if len(providers) > 1:
        raise ValueError("模板包含多种计算平台（K8s/Docker 混用），无法一键部署")

    cluster = (
        await db.execute(
            select(Cluster).where(Cluster.id == cluster_id, Cluster.deleted_at.is_(None))
        )
    ).scalar_one_or_none()
    if not cluster:
        raise ValueError("集群不存在")
    need = next(iter(providers))
    if cluster.compute_provider != need:
        raise ValueError(f"请选择 {need} 类型的集群以匹配模板")

    ws = await workspace_service.create_workspace(
        db,
        org_id,
        user.id,
        WorkspaceCreate(name=workspace_name, description=template.description or ""),
    )

    wd = WorkspaceDeploy(
        id=str(uuid.uuid4()),
        workspace_id=ws.id,
        template_id=template.id,
        status="pending",
        total_agents=len(agent_specs),
        completed_agents=0,
        failed_agents=0,
        progress_detail={
            "agents": [
                {
                    "display_name": s.get("display_name") or f"agent-{i}",
                    "instance_id": None,
                    "status": "pending",
                    "step": None,
                    "error": None,
                    "retry_count": 0,
                }
                for i, s in enumerate(agent_specs)
            ],
            "current_phase": "pending",
            "phases_completed": [],
        },
        config_snapshot={
            "cluster_id": cluster_id,
            "workspace_name": workspace_name,
            "selected_agent_indices": selected_agent_indices,
            "excluded_corridor_coords": excluded_corridor_coords,
        },
        created_by=user.id,
        org_id=org_id,
    )
    db.add(wd)
    await db.commit()

    asyncio.create_task(
        _run_deploy_pipeline(wd.id),
        name=f"ws-tpl-deploy-{wd.id}",
    )

    return {"workspace_deploy_id": wd.id, "workspace_id": ws.id}
