"""Deploy service: precheck, step-by-step deploy, SSE progress push.

部署采用「同步建记录 + 异步执行」两阶段模式：
  1. deploy_instance()  —— 在请求上下文中同步创建 Instance + DeployRecord，立即返回 record.id
  2. execute_deploy_pipeline() —— 通过 asyncio.create_task 在后台执行 K8s 资源创建，
     使用独立的 DB session，通过 EventBus 推送进度供 SSE 消费
"""

import asyncio
import logging
import re as _re
import json as _json
import secrets as _secrets
from datetime import datetime, timezone
from dataclasses import dataclass

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError

from app.models.cluster import Cluster
from app.models.deploy_record import DeployAction, DeployRecord, DeployStatus
from app.models.instance import Instance, InstanceStatus
from app.models.user import User
from app.schemas.deploy import DeployProgress, DeployRequest, PrecheckItem, PrecheckResult
from app.services.k8s.client_manager import k8s_manager
from app.services.k8s.event_bus import event_bus
from app.services.k8s.k8s_client import K8sClient
from app.services.k8s.resource_builder import (
    build_configmap,
    build_deployment,
    build_external_name_service,
    build_ingress,
    build_labels,
    build_network_policy,
    build_proxy_ingress,
    build_pvc,
    build_resource_quota,
    build_service,
)

logger = logging.getLogger(__name__)

# 正在运行的部署任务引用（deploy_id -> asyncio.Task）
_running_tasks: dict[str, asyncio.Task] = {}


def register_deploy_task(deploy_id: str, task: asyncio.Task) -> None:
    """注册后台部署任务，供取消时使用。"""
    _running_tasks[deploy_id] = task


def _unregister_deploy_task(deploy_id: str) -> None:
    """任务结束后移除引用。"""
    _running_tasks.pop(deploy_id, None)


async def cancel_deploy(deploy_id: str) -> str:
    """立即取消部署：清理 K8s namespace + 更新 DB + 杀掉后台协程。

    Returns: 操作结果描述
    """
    from app.core.deps import async_session_factory

    async with async_session_factory() as db:
        # 1. 查部署记录 + 实例
        rec_result = await db.execute(
            select(DeployRecord).where(DeployRecord.id == deploy_id)
        )
        record = rec_result.scalar_one_or_none()
        if not record:
            return "部署记录不存在"
        if record.status != DeployStatus.running:
            return f"部署已结束（状态: {record.status}）"

        inst_result = await db.execute(
            select(Instance).where(Instance.id == record.instance_id)
        )
        instance = inst_result.scalar_one_or_none()
        if not instance:
            return "实例记录不存在"

        # 2. 先杀后台协程（防止它继续操作 K8s / DB）
        task = _running_tasks.pop(deploy_id, None)
        if task and not task.done():
            task.cancel()

        # 3. 立即清理 K8s namespace
        ns_cleaned = False
        try:
            cluster_result = await db.execute(
                select(Cluster).where(Cluster.id == instance.cluster_id)
            )
            cluster = cluster_result.scalar_one_or_none()
            if cluster and cluster.kubeconfig_encrypted:
                api_client = await k8s_manager.get_or_create(
                    cluster.id, cluster.kubeconfig_encrypted
                )
                k8s = K8sClient(api_client)
                await k8s.core.delete_namespace(instance.namespace)
                ns_cleaned = True
                logger.info("取消部署，已清理命名空间: %s", instance.namespace)
        except Exception:
            logger.warning("取消部署，清理命名空间 %s 失败", instance.namespace)

        # 4. 更新 DB：标记失败 + 软删除
        record.status = DeployStatus.failed
        record.message = "用户手动取消部署"
        record.finished_at = datetime.now(timezone.utc)
        instance.soft_delete()
        await db.execute(
            update(DeployRecord)
            .where(DeployRecord.instance_id == instance.id, DeployRecord.deleted_at.is_(None))
            .values(deleted_at=func.now())
        )
        await db.commit()
        logger.info("取消部署完成: deploy_id=%s, instance=%s", deploy_id, instance.name)

    # 5. 推 SSE 事件通知前端
    event_bus.publish(
        "deploy_progress",
        DeployProgress(
            deploy_id=deploy_id,
            step=len(DEPLOY_STEPS),
            total_steps=len(DEPLOY_STEPS),
            current_step="已取消",
            status="failed",
            message=f"部署已取消{'，命名空间已清理' if ns_cleaned else ''}",
            percent=100,
        ).model_dump(),
    )

    return "已取消" + ("，命名空间已清理" if ns_cleaned else "")


DEPLOY_STEPS = [
    "预检",
    "创建命名空间",
    "创建 ConfigMap",
    "创建 PVC",
    "创建 Deployment",
    "创建 Service",
    "创建 Ingress（自动路由）",
    "配置网络策略",
    "等待 Deployment 就绪",
]


async def precheck(req: DeployRequest, db: AsyncSession) -> PrecheckResult:
    """Run pre-deploy checks."""
    items: list[PrecheckItem] = []

    # Check cluster exists
    result = await db.execute(
        select(Cluster).where(Cluster.id == req.cluster_id, Cluster.deleted_at.is_(None))
    )
    cluster = result.scalar_one_or_none()
    if not cluster:
        items.append(PrecheckItem(name="集群", status="fail", message="集群不存在"))
        return PrecheckResult(passed=False, items=items)
    items.append(PrecheckItem(name="集群", status="pass", message=f"集群 {cluster.name} 可用"))

    # Check cluster connection
    if cluster.status != "connected":
        items.append(PrecheckItem(name="连接", status="fail", message="集群未连接"))
        return PrecheckResult(passed=False, items=items)
    items.append(PrecheckItem(name="连接", status="pass", message="集群已连接"))

    # Check name uniqueness（仅检查未删除的实例，已删除的名称可复用）
    existing = await db.execute(
        select(Instance).where(Instance.name == req.name, Instance.deleted_at.is_(None))
    )
    if existing.scalar_one_or_none():
        items.append(PrecheckItem(name="名称", status="fail", message=f"实例名 '{req.name}' 已存在"))
        return PrecheckResult(passed=False, items=items)
    items.append(PrecheckItem(name="名称", status="pass", message="实例名可用"))

    # Image version
    if not req.image_version:
        items.append(PrecheckItem(name="镜像", status="fail", message="镜像版本不能为空"))
        return PrecheckResult(passed=False, items=items)
    items.append(PrecheckItem(name="镜像", status="pass", message=f"镜像版本: {req.image_version}"))

    passed = all(item.status != "fail" for item in items)
    return PrecheckResult(passed=passed, items=items)


@dataclass
class _DeployContext:
    """后台部署管道所需的上下文（避免跨 session 传递 ORM 对象）。"""

    record_id: str
    instance_id: str
    cluster_id: str
    name: str
    namespace: str
    image_version: str
    replicas: int
    cpu_request: str
    cpu_limit: str
    mem_request: str
    mem_limit: str
    storage_class: str
    storage_size: str
    quota_cpu: str
    quota_mem: str
    env_vars: dict | None
    advanced_config: dict | None
    kubeconfig_encrypted: str
    ingress_class: str = "nginx"
    proxy_endpoint: str | None = None
    org_id: str | None = None


async def deploy_instance(
    req: DeployRequest, user: User, db: AsyncSession, org_id: str | None = None
) -> str:
    """
    同步阶段：创建 Instance + DeployRecord，立即返回 record.id。
    不执行任何 K8s 操作，由调用方用 asyncio.create_task 启动后台管道。
    """
    # 组织配额检查 + 专属集群路由
    effective_cluster_id = req.cluster_id
    org = None
    if org_id:
        from app.models.organization import Organization
        from app.services.billing_service import check_deploy_quota
        org_result = await db.execute(
            select(Organization).where(Organization.id == org_id, Organization.deleted_at.is_(None))
        )
        org = org_result.scalar_one_or_none()
        if org:
            await check_deploy_quota(
                org, db,
                cpu_request=req.cpu_limit,
                mem_request=req.mem_limit,
                storage_size=req.storage_size,
            )
            # 如果组织绑定了专属集群，强制使用该集群
            if org.cluster_id:
                effective_cluster_id = org.cluster_id
                logger.info("组织 %s 绑定专属集群 %s，覆盖用户选择", org.slug, org.cluster_id)

    # 校验集群
    result = await db.execute(
        select(Cluster).where(Cluster.id == effective_cluster_id, Cluster.deleted_at.is_(None))
    )
    cluster = result.scalar_one_or_none()
    if not cluster:
        raise NotFoundError("集群不存在")

    # slug: 前端显式传入，或从 name 自动生成（兼容管理端不传 slug 的情况）
    slug = req.slug
    if not slug:
        slug = _re.sub(r"[^a-z0-9-]", "-", req.name.lower()).strip("-")
        slug = _re.sub(r"-{2,}", "-", slug) or "instance"

    # namespace: nodeskclaw-{org_slug}-{instance_slug}
    org_slug = org.slug if org else "default"
    namespace = req.namespace or f"nodeskclaw-{org_slug}-{slug}"

    # 自动注入 OPENCLAW_GATEWAY_TOKEN（用户未提供时自动生成）
    env_vars = dict(req.env_vars) if req.env_vars else {}
    if "OPENCLAW_GATEWAY_TOKEN" not in env_vars:
        env_vars["OPENCLAW_GATEWAY_TOKEN"] = _secrets.token_hex(24)
    gateway_token = env_vars["OPENCLAW_GATEWAY_TOKEN"]

    # 创建实例记录
    instance = Instance(
        name=req.name,
        slug=slug,
        cluster_id=cluster.id,
        namespace=namespace,
        image_version=req.image_version,
        replicas=req.replicas,
        cpu_request=req.cpu_request,
        cpu_limit=req.cpu_limit,
        mem_request=req.mem_request,
        mem_limit=req.mem_limit,
        service_type="ClusterIP",
        ingress_domain=None,
        proxy_token=gateway_token,
        wp_api_key=f"nodeskclaw-wp-{_secrets.token_hex(32)}",
        env_vars=_json.dumps(env_vars),
        advanced_config=_json.dumps(req.advanced_config) if req.advanced_config else None,
        storage_class=req.storage_class,
        storage_size=req.storage_size,
        status=InstanceStatus.deploying,
        created_by=user.id,
        org_id=org_id,
    )
    db.add(instance)
    await db.commit()
    await db.refresh(instance)

    # 创建部署记录
    max_rev = await db.execute(
        select(func.coalesce(func.max(DeployRecord.revision), 0)).where(
            DeployRecord.instance_id == instance.id, DeployRecord.deleted_at.is_(None)
        )
    )
    next_rev = max_rev.scalar() + 1

    record = DeployRecord(
        instance_id=instance.id,
        revision=next_rev,
        action=DeployAction.deploy,
        image_version=req.image_version,
        status=DeployStatus.running,
        triggered_by=user.id,
        started_at=datetime.now(timezone.utc),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    return record.id, _DeployContext(
        record_id=record.id,
        instance_id=instance.id,
        cluster_id=cluster.id,
        name=slug,
        namespace=namespace,
        image_version=req.image_version,
        replicas=req.replicas,
        cpu_request=req.cpu_request,
        cpu_limit=req.cpu_limit,
        mem_request=req.mem_request,
        mem_limit=req.mem_limit,
        storage_class=req.storage_class,
        storage_size=req.storage_size,
        quota_cpu=req.quota_cpu,
        quota_mem=req.quota_mem,
        env_vars=env_vars,
        advanced_config=req.advanced_config,
        kubeconfig_encrypted=cluster.kubeconfig_encrypted,
        ingress_class=cluster.ingress_class,
        proxy_endpoint=cluster.proxy_endpoint,
        org_id=org_id,
    )


async def execute_deploy_pipeline(ctx: _DeployContext) -> None:
    """
    后台异步阶段：使用独立 DB session 执行 K8s 资源创建。
    通过 EventBus 推送 SSE 进度事件。
    """
    from app.core.deps import async_session_factory
    from app.services.config_service import get_config

    total = len(DEPLOY_STEPS)

    try:
        await _execute_deploy_inner(ctx, async_session_factory, get_config, total)
    finally:
        _unregister_deploy_task(ctx.record_id)


async def _execute_deploy_inner(ctx, async_session_factory, get_config, total) -> None:
    """实际的部署管道逻辑（拆出来方便 finally 注销任务）。"""

    def _publish(
        step: int, step_name: str, status: str = "in_progress",
        message: str | None = None, logs: list[str] | None = None,
    ):
        # 进行中的步骤不应该达到 100%，留给 success 状态
        if status in ("success", "failed"):
            pct = round(step / total * 100, 1)
        else:
            pct = round((step - 0.5) / total * 100, 1)
        event_bus.publish(
            "deploy_progress",
            DeployProgress(
                deploy_id=ctx.record_id,
                step=step,
                total_steps=total,
                current_step=step_name,
                status=status,
                message=message,
                percent=pct,
                logs=logs,
            ).model_dump(),
        )

    # 等待前端 SSE 订阅建立连接（给前端足够时间发起 /progress SSE 请求）
    await asyncio.sleep(0.3)

    async with async_session_factory() as db:
        try:
            # Step 1: 预检（同步阶段已完成，标记通过）
            _publish(1, DEPLOY_STEPS[0])

            # 获取 K8s 客户端
            api_client = await k8s_manager.get_or_create(ctx.cluster_id, ctx.kubeconfig_encrypted)
            k8s = K8sClient(api_client)

            labels = build_labels(ctx.name, ctx.instance_id, ctx.image_version)

            # Step 2: 创建命名空间 + ResourceQuota
            _publish(2, DEPLOY_STEPS[1])
            ns_labels = {"nodeskclaw.io/org-id": ctx.org_id} if ctx.org_id else None
            await k8s.ensure_namespace(ctx.namespace, extra_labels=ns_labels)
            rq = build_resource_quota(
                f"{ctx.namespace}-quota", ctx.namespace,
                cpu=ctx.quota_cpu, mem=ctx.quota_mem,
                storage=ctx.storage_size,
            )
            await k8s.create_or_skip(k8s.core.create_namespaced_resource_quota, ctx.namespace, rq)

            # Step 3: 创建 ConfigMap
            _publish(3, DEPLOY_STEPS[2])
            if ctx.env_vars:
                cm = build_configmap(f"{ctx.name}-config", ctx.namespace, ctx.env_vars, labels)
                await k8s.create_or_skip(k8s.core.create_namespaced_config_map, ctx.namespace, cm)

            # Step 4: 创建 PVC（使用实例指定的 StorageClass）
            _publish(4, DEPLOY_STEPS[3])
            pvc_name = f"{ctx.name}-root-data"
            logger.info("使用 StorageClass: %s, 存储大小: %s", ctx.storage_class, ctx.storage_size)
            pvc = build_pvc(pvc_name, ctx.namespace, ctx.storage_size, ctx.storage_class, labels)
            await k8s.create_or_skip(k8s.core.create_namespaced_persistent_volume_claim, ctx.namespace, pvc)

            # Step 5: 创建 Deployment（含镜像拉取凭据）
            _publish(5, DEPLOY_STEPS[4])
            image_registry = await get_config("image_registry", db) or "openclaw"
            image = f"{image_registry}:{ctx.image_version}"

            # 创建镜像仓库拉取凭据 Secret（如果配置了仓库用户名密码）
            registry_username = await get_config("registry_username", db)
            registry_password = await get_config("registry_password", db)
            pull_secret_name: str | None = None
            if registry_username and registry_password and image_registry:
                from app.services.k8s.resource_builder import build_registry_secret, REGISTRY_SECRET_NAME
                secret = build_registry_secret(
                    ctx.namespace, image_registry, registry_username, registry_password,
                )
                await k8s.create_or_skip(k8s.core.create_namespaced_secret, ctx.namespace, secret)
                pull_secret_name = REGISTRY_SECRET_NAME
                logger.info("已创建镜像拉取凭据 Secret: %s/%s", ctx.namespace, REGISTRY_SECRET_NAME)

            dep = build_deployment(
                name=ctx.name,
                namespace=ctx.namespace,
                image=image,
                replicas=ctx.replicas,
                labels=labels,
                configmap_name=f"{ctx.name}-config" if ctx.env_vars else None,
                pvc_name=pvc_name,
                cpu_request=ctx.cpu_request,
                cpu_limit=ctx.cpu_limit,
                mem_request=ctx.mem_request,
                mem_limit=ctx.mem_limit,
                env_vars=ctx.env_vars,
                advanced_config=ctx.advanced_config,
                image_pull_secret=pull_secret_name,
            )
            await k8s.apply(
                k8s.apps.create_namespaced_deployment,
                k8s.apps.patch_namespaced_deployment,
                ctx.namespace,
                ctx.name,
                dep,
            )

            # Step 6: 创建 Service（固定 ClusterIP）
            _publish(6, DEPLOY_STEPS[5])
            svc = build_service(ctx.name, ctx.namespace, labels)
            await k8s.create_or_skip(k8s.core.create_namespaced_service, ctx.namespace, svc)

            # Step 7: 创建 Ingress（自动子域名路由）
            _publish(7, DEPLOY_STEPS[6])
            ingress_base_domain = await get_config("ingress_base_domain", db)
            subdomain_suffix = await get_config("ingress_subdomain_suffix", db)
            tls_secret_name = await get_config("tls_secret_name", db)
            if ingress_base_domain:
                if subdomain_suffix:
                    ingress_host = f"{ctx.name}-{subdomain_suffix}.{ingress_base_domain}"
                else:
                    ingress_host = f"{ctx.name}.{ingress_base_domain}"
                inst_tls = None if ctx.proxy_endpoint else tls_secret_name
                ing = build_ingress(
                    ctx.name, ctx.namespace, ingress_host, labels,
                    tls_secret_name=inst_tls,
                    ingress_class=ctx.ingress_class,
                )
                await k8s.create_or_skip(k8s.networking.create_namespaced_ingress, ctx.namespace, ing)
                # 回写自动生成的域名到实例记录
                inst_result = await db.execute(
                    select(Instance).where(Instance.id == ctx.instance_id)
                )
                instance = inst_result.scalar_one()
                instance.ingress_domain = ingress_host
                await db.commit()
                # 网关代理：在 infra 集群创建 proxy Ingress，将流量转发到 inst 集群
                if ctx.proxy_endpoint:
                    try:
                        from app.services.k8s.client_manager import GATEWAY_NS
                        gateway_api = await k8s_manager.get_gateway_client()
                        gateway_k8s = K8sClient(gateway_api)

                        ext_svc = build_external_name_service(ctx.cluster_id, ctx.proxy_endpoint)
                        await gateway_k8s.create_or_skip(
                            gateway_k8s.core.create_namespaced_service, GATEWAY_NS, ext_svc,
                        )

                        proxy_ing = build_proxy_ingress(
                            ctx.name, ingress_host, ext_svc.metadata.name,
                        )
                        await gateway_k8s.create_or_skip(
                            gateway_k8s.networking.create_namespaced_ingress, GATEWAY_NS, proxy_ing,
                        )
                        logger.info("已在网关集群创建代理 Ingress: %s -> %s", ingress_host, ctx.proxy_endpoint)
                    except Exception as e:
                        logger.warning("创建网关代理 Ingress 失败（非致命）: %s", e)
            else:
                logger.warning("未配置 ingress_base_domain，跳过 Ingress 创建")

            # Step 8: 配置网络策略（多租户隔离）
            _publish(8, DEPLOY_STEPS[7])
            peer_namespaces = []
            if ctx.advanced_config and ctx.advanced_config.get("network", {}).get("peers"):
                peer_ids = ctx.advanced_config["network"]["peers"]
                for pid in peer_ids:
                    peer_result = await db.execute(
                        select(Instance).where(Instance.id == pid, Instance.deleted_at.is_(None))
                    )
                    peer_inst = peer_result.scalar_one_or_none()
                    if peer_inst:
                        peer_namespaces.append(peer_inst.namespace)

            # 始终创建默认隔离策略（允许 Ingress + 同 NS + 同组织 peer）
            np = build_network_policy(
                f"{ctx.name}-isolation", ctx.namespace, labels,
                peer_namespaces, org_id=ctx.org_id,
            )
            try:
                await k8s.networking.create_namespaced_network_policy(ctx.namespace, np)
            except Exception:
                await k8s.networking.patch_namespaced_network_policy(
                    f"{ctx.name}-isolation", ctx.namespace, np
                )

            # Step 9: 等待 Deployment 就绪（最多 300 秒）
            _publish(9, DEPLOY_STEPS[8], logs=["开始等待 Pod 就绪..."])
            dep_status: dict = {"ready_replicas": 0, "available_replicas": 0}
            deployment_ready = False
            label_selector = f"app.kubernetes.io/name={ctx.name}"

            for tick in range(150):  # 150 x 2s = 300s
                dep_status = await k8s.get_deployment_status(ctx.namespace, ctx.name)
                if dep_status["ready_replicas"] >= ctx.replicas:
                    deployment_ready = True
                    break

                # 每 10 秒（5 个 tick）推送一次 Pod 诊断日志
                if tick % 5 == 4:
                    diag_lines: list[str] = []

                    # ── Pod 状态 ──
                    try:
                        pods = await k8s.list_pods(ctx.namespace, label_selector)
                        if not pods:
                            diag_lines.append("尚未发现 Pod（调度中）")
                        for pod in pods:
                            phase = pod.get("phase", "Unknown")
                            node = pod.get("node") or "未分配"
                            pod_short = pod.get("name", "?").split("-")[-1]
                            parts = [f"Pod ...{pod_short}: {phase} (节点: {node})"]
                            for c in pod.get("containers", []):
                                c_state = c.get("state", "unknown")
                                parts.append(f"{c['name']}={c_state}, restarts={c.get('restart_count', 0)}")
                            diag_lines.append(" | ".join(parts))
                    except Exception:
                        diag_lines.append("无法获取 Pod 状态")

                    # ── PVC 状态 ──
                    try:
                        pvcs = await k8s.core.list_namespaced_persistent_volume_claim(ctx.namespace)
                        for pvc in pvcs.items:
                            pvc_phase = pvc.status.phase if pvc.status else "Unknown"
                            sc = pvc.spec.storage_class_name or "(默认)"
                            diag_lines.append(f"PVC {pvc.metadata.name}: {pvc_phase} (StorageClass: {sc})")
                    except Exception:
                        pass

                    # ── K8s Events（最近 5 条） ──
                    try:
                        events = await k8s.core.list_namespaced_event(ctx.namespace)
                        recent = sorted(events.items, key=lambda e: e.last_timestamp or e.metadata.creation_timestamp or "", reverse=True)[:5]
                        for ev in recent:
                            diag_lines.append(f"Event: {ev.reason} — {(ev.message or '')[:200]}")
                    except Exception:
                        pass

                    # ── Deployment conditions ──
                    for cond in dep_status.get("conditions", []):
                        diag_lines.append(f"{cond['type']}: {cond.get('message', '')[:100]}")

                    elapsed = (tick + 1) * 2
                    diag_lines.append(f"已等待 {elapsed}s / 300s")
                    # 同时写入后端日志文件，方便事后排查
                    logger.info("[%s] 等待就绪诊断:\n  %s", ctx.name, "\n  ".join(diag_lines))
                    _publish(9, DEPLOY_STEPS[8], logs=diag_lines)

                await asyncio.sleep(2)

            rec_result = await db.execute(select(DeployRecord).where(DeployRecord.id == ctx.record_id))
            record = rec_result.scalar_one()
            inst_result = await db.execute(select(Instance).where(Instance.id == ctx.instance_id))
            instance = inst_result.scalar_one()

            if deployment_ready:
                # 标记成功
                record.status = DeployStatus.success
                record.finished_at = datetime.now(timezone.utc)
                instance.status = InstanceStatus.running
                instance.available_replicas = dep_status.get("available_replicas", 0)
                await db.commit()

                # 注入 gateway 配置 + LLM provider 配置到 openclaw.json
                from app.services.llm_config_service import (
                    ensure_openclaw_gateway_config,
                    sync_openclaw_llm_config,
                )
                llm_sync_warning = ""
                await ensure_openclaw_gateway_config(instance, db)
                try:
                    await sync_openclaw_llm_config(instance, db)
                except Exception as e:
                    logger.warning("部署后同步 LLM 配置失败（非致命）: %s", e)
                    llm_sync_warning = "（LLM 配置注入失败，请在管理后台手动同步）"

                success_msg = f"部署成功{llm_sync_warning}"
                _publish(total, "完成", status="success", message=success_msg)
                logger.info("部署成功: %s (namespace=%s)", ctx.name, ctx.namespace)
            else:
                # 超时未就绪 —— 标记失败，附带 Deployment 状态详情
                conditions = dep_status.get("conditions", [])
                cond_msg = "; ".join(
                    f"{c['type']}: {c.get('message', '')}" for c in conditions
                ) or "Deployment 未在 120 秒内就绪"

                # 清理 K8s namespace（级联删除所有资源）
                ns_cleaned = False
                try:
                    await k8s.core.delete_namespace(ctx.namespace)
                    ns_cleaned = True
                    logger.info("部署失败，已清理命名空间: %s", ctx.namespace)
                except Exception:
                    logger.warning("清理命名空间 %s 失败", ctx.namespace)

                await _cleanup_proxy_ingress(ctx)

                record.status = DeployStatus.failed
                record.message = f"就绪超时: {cond_msg}"[:500]
                record.finished_at = datetime.now(timezone.utc)

                # 软删除实例 + 级联软删除部署记录
                instance.soft_delete()
                await db.execute(
                    update(DeployRecord)
                    .where(DeployRecord.instance_id == ctx.instance_id, DeployRecord.deleted_at.is_(None))
                    .values(deleted_at=func.now())
                )
                await db.commit()

                cleanup_hint = "，命名空间已清理" if ns_cleaned else ""
                _publish(total, "失败", status="failed", message=f"Pod 未就绪: {cond_msg}{cleanup_hint}"[:200])
                logger.warning("部署超时未就绪: %s (namespace=%s) — %s", ctx.name, ctx.namespace, cond_msg)

        except asyncio.CancelledError:
            # 被 cancel_deploy() 杀掉的协程，清理已由 cancel_deploy() 完成
            logger.info("部署协程被取消: %s", ctx.name)
            return

        except Exception as e:
            logger.exception("部署失败: %s", ctx.name)
            ns_cleaned = False
            try:
                api_client = await k8s_manager.get_or_create(ctx.cluster_id, ctx.kubeconfig_encrypted)
                cleanup_k8s = K8sClient(api_client)
                await cleanup_k8s.core.delete_namespace(ctx.namespace)
                ns_cleaned = True
                logger.info("部署异常，已清理命名空间: %s", ctx.namespace)
            except Exception:
                logger.warning("清理命名空间 %s 失败", ctx.namespace)

            await _cleanup_proxy_ingress(ctx)

            try:
                rec_result = await db.execute(select(DeployRecord).where(DeployRecord.id == ctx.record_id))
                record = rec_result.scalar_one()
                record.status = DeployStatus.failed
                record.message = str(e)[:500]
                record.finished_at = datetime.now(timezone.utc)

                inst_result = await db.execute(select(Instance).where(Instance.id == ctx.instance_id))
                instance = inst_result.scalar_one()

                # 软删除实例 + 级联软删除部署记录
                instance.soft_delete()
                await db.execute(
                    update(DeployRecord)
                    .where(DeployRecord.instance_id == ctx.instance_id, DeployRecord.deleted_at.is_(None))
                    .values(deleted_at=func.now())
                )
                await db.commit()
            except Exception:
                logger.exception("更新部署失败状态时出错")

            cleanup_hint = "，命名空间已清理" if ns_cleaned else ""
            _publish(total, "失败", status="failed", message=f"{str(e)[:180]}{cleanup_hint}")


async def _cleanup_proxy_ingress(ctx: _DeployContext) -> None:
    """清理 infra 网关集群上的代理 Ingress（部署失败或实例删除时调用）。"""
    if not ctx.proxy_endpoint:
        return
    try:
        from app.services.k8s.client_manager import GATEWAY_NS
        gateway_api = await k8s_manager.get_gateway_client()
        gateway_k8s = K8sClient(gateway_api)
        await gateway_k8s.networking.delete_namespaced_ingress(
            f"proxy-{ctx.name}", GATEWAY_NS,
        )
        logger.info("已清理网关代理 Ingress: proxy-%s", ctx.name)
    except Exception:
        logger.debug("清理网关代理 Ingress proxy-%s 失败（可能不存在）", ctx.name)
