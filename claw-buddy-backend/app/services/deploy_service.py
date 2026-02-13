"""Deploy service: precheck, step-by-step deploy, SSE progress push."""

import logging
from datetime import datetime, timezone

from sqlalchemy import func, select
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
    build_ingress,
    build_labels,
    build_network_policy,
    build_pvc,
    build_resource_quota,
    build_service,
)

logger = logging.getLogger(__name__)

DEPLOY_STEPS = [
    "预检",
    "创建命名空间",
    "创建 ConfigMap",
    "创建 PVC",
    "创建 Deployment",
    "创建 Service",
    "创建 Ingress",
    "配置网络策略",
    "等待 Deployment 就绪",
]


async def precheck(req: DeployRequest, db: AsyncSession) -> PrecheckResult:
    """Run pre-deploy checks."""
    items: list[PrecheckItem] = []

    # Check cluster exists
    result = await db.execute(select(Cluster).where(Cluster.id == req.cluster_id))
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

    # Check name uniqueness
    existing = await db.execute(select(Instance).where(Instance.name == req.name))
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


async def deploy_instance(
    req: DeployRequest, user: User, db: AsyncSession
) -> str:
    """
    Execute full deployment pipeline.
    Returns deploy_record_id. Progress is pushed via SSE EventBus.
    """
    # Get cluster
    result = await db.execute(select(Cluster).where(Cluster.id == req.cluster_id))
    cluster = result.scalar_one_or_none()
    if not cluster:
        raise NotFoundError("集群不存在")

    namespace = req.namespace or f"oc-{req.name}"

    import json as _json

    # Create instance record
    instance = Instance(
        name=req.name,
        cluster_id=cluster.id,
        namespace=namespace,
        image_version=req.image_version,
        replicas=req.replicas,
        cpu_request=req.cpu_request,
        cpu_limit=req.cpu_limit,
        mem_request=req.mem_request,
        mem_limit=req.mem_limit,
        service_type=req.service_type,
        ingress_domain=req.ingress_domain,
        env_vars=_json.dumps(req.env_vars) if req.env_vars else None,
        advanced_config=_json.dumps(req.advanced_config) if req.advanced_config else None,
        status=InstanceStatus.deploying,
        created_by=user.id,
    )
    db.add(instance)
    await db.commit()
    await db.refresh(instance)

    # Create deploy record
    max_rev = await db.execute(
        select(func.coalesce(func.max(DeployRecord.revision), 0)).where(
            DeployRecord.instance_id == instance.id
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

    # Execute deploy steps
    total = len(DEPLOY_STEPS)

    def _publish(step: int, step_name: str, status: str = "in_progress", message: str | None = None):
        event_bus.publish(
            "deploy_progress",
            DeployProgress(
                deploy_id=record.id,
                step=step,
                total_steps=total,
                current_step=step_name,
                status=status,
                message=message,
                percent=round(step / total * 100, 1),
            ).model_dump(),
        )

    try:
        # Step 1: precheck (already done by caller, mark pass)
        _publish(1, DEPLOY_STEPS[0])

        # Get K8s client
        api_client = await k8s_manager.get_or_create(cluster.id, cluster.kubeconfig_encrypted)
        k8s = K8sClient(api_client)

        labels = build_labels(req.name, instance.id, req.image_version)

        # Step 2: create namespace + ResourceQuota
        _publish(2, DEPLOY_STEPS[1])
        await k8s.ensure_namespace(namespace)
        # Apply ResourceQuota to namespace
        rq = build_resource_quota(
            f"{namespace}-quota", namespace,
            cpu=req.quota_cpu, mem=req.quota_mem,
        )
        await k8s.create_or_skip(k8s.core.create_namespaced_resource_quota, namespace, rq)

        # Step 3: create configmap
        _publish(3, DEPLOY_STEPS[2])
        if req.env_vars:
            cm = build_configmap(f"{req.name}-config", namespace, req.env_vars, labels)
            await k8s.create_or_skip(k8s.core.create_namespaced_config_map, namespace, cm)

        # Step 4: create PVC
        _publish(4, DEPLOY_STEPS[3])
        pvc_name = f"{req.name}-root-data"
        pvc = build_pvc(pvc_name, namespace, req.storage_size, None, labels)
        await k8s.create_or_skip(k8s.core.create_namespaced_persistent_volume_claim, namespace, pvc)

        # Step 5: create deployment
        _publish(5, DEPLOY_STEPS[4])
        from app.services.config_service import get_config

        image_registry = await get_config("image_registry", db) or "openclaw"
        image = f"{image_registry}:{req.image_version}"
        dep = build_deployment(
            name=req.name,
            namespace=namespace,
            image=image,
            replicas=req.replicas,
            labels=labels,
            configmap_name=f"{req.name}-config" if req.env_vars else None,
            pvc_name=pvc_name,
            cpu_request=req.cpu_request,
            cpu_limit=req.cpu_limit,
            mem_request=req.mem_request,
            mem_limit=req.mem_limit,
            env_vars=req.env_vars,
            advanced_config=req.advanced_config,
        )
        await k8s.apply(
            k8s.apps.create_namespaced_deployment,
            k8s.apps.patch_namespaced_deployment,
            namespace,
            req.name,
            dep,
        )

        # Step 6: create service
        _publish(6, DEPLOY_STEPS[5])
        svc = build_service(req.name, namespace, labels, service_type=req.service_type)
        await k8s.create_or_skip(k8s.core.create_namespaced_service, namespace, svc)

        # Step 7: create ingress (optional)
        _publish(7, DEPLOY_STEPS[6])
        if req.ingress_domain:
            ing = build_ingress(req.name, namespace, req.ingress_domain, labels)
            await k8s.create_or_skip(k8s.networking.create_namespaced_ingress, namespace, ing)

        # Step 8: network policy (if advanced_config has peers)
        _publish(8, DEPLOY_STEPS[7])
        if req.advanced_config and req.advanced_config.get("network", {}).get("peers"):
            peer_ids = req.advanced_config["network"]["peers"]
            # Resolve peer namespaces from DB
            peer_namespaces = []
            for pid in peer_ids:
                peer_result = await db.execute(select(Instance).where(Instance.id == pid))
                peer_inst = peer_result.scalar_one_or_none()
                if peer_inst:
                    peer_namespaces.append(peer_inst.namespace)
            if peer_namespaces:
                np = build_network_policy(
                    f"{req.name}-allow-peers", namespace, labels, peer_namespaces
                )
                try:
                    await k8s.networking.create_namespaced_network_policy(namespace, np)
                except Exception:
                    await k8s.networking.patch_namespaced_network_policy(
                        f"{req.name}-allow-peers", namespace, np
                    )

        # Step 9: wait for deployment ready
        _publish(9, DEPLOY_STEPS[8])
        # Simple readiness poll (max 60s)
        import asyncio

        for _ in range(30):
            dep_status = await k8s.get_deployment_status(namespace, req.name)
            if dep_status["ready_replicas"] >= req.replicas:
                break
            await asyncio.sleep(2)

        # Mark success
        record.status = DeployStatus.success
        record.finished_at = datetime.now(timezone.utc)
        instance.status = InstanceStatus.running
        instance.available_replicas = dep_status.get("available_replicas", 0)
        await db.commit()

        _publish(total, "完成", status="success", message="部署成功")

    except Exception as e:
        logger.exception("Deploy failed for %s", req.name)
        record.status = DeployStatus.failed
        record.message = str(e)[:500]
        record.finished_at = datetime.now(timezone.utc)
        instance.status = InstanceStatus.failed
        await db.commit()

        _publish(total, "失败", status="failed", message=str(e)[:200])
        raise

    return record.id
