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
from urllib.parse import urlparse as _urlparse

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import BadRequestError, NotFoundError

from app.models.cluster import Cluster
from app.models.deploy_record import DeployAction, DeployRecord, DeployStatus
from app.models.instance import Instance, InstanceStatus
from app.models.user import User
from app.schemas.deploy import DeployProgress, DeployRequest, PrecheckItem, PrecheckResult
from app.services.k8s.client_manager import k8s_manager
from app.services.k8s.event_bus import event_bus
from app.services.k8s.k8s_client import K8sClient
from app.services.deploy.factory import get_deploy_adapter
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
from app.services.codex_provider import normalize_selected_models

logger = logging.getLogger(__name__)


def _compute_llm_providers(
    llm_configs: list | None, org_active_providers: list[str],
) -> list[str] | None:
    """Merge user-requested providers with org active providers into a snapshot list."""
    providers: set[str] = set(org_active_providers)
    if llm_configs:
        for c in llm_configs:
            providers.add(c.provider)
    return sorted(providers) if providers else None

# 正在运行的部署任务引用（deploy_id -> asyncio.Task）
_running_tasks: dict[str, asyncio.Task] = {}


def register_deploy_task(deploy_id: str, task: asyncio.Task) -> None:
    """注册后台部署任务，供取消时使用。"""
    _running_tasks[deploy_id] = task


def _unregister_deploy_task(deploy_id: str) -> None:
    """任务结束后移除引用。"""
    _running_tasks.pop(deploy_id, None)


_bg_tasks: set[asyncio.Task] = set()
_PV_CLEANUP_DELAY = 15
_PV_CLEANUP_RETRIES = 3
_K8S_NAME_MAX = 63
_DEPLOY_NAME_MAX = 35


def _truncate_slug_preserve_suffix(slug: str, max_len: int) -> str:
    """截断 slug 使其不超过 max_len，保留末尾随机后缀段，只截断前面的拼音部分。

    Portal slug 格式: {pinyin-part}-{random_suffix_6chars}
    Admin slug 格式:  {pinyin-part}
    """
    if len(slug) <= max_len:
        return slug

    last_dash = slug.rfind("-")
    suffix = ""
    prefix_part = slug

    if last_dash > 0:
        tail = slug[last_dash + 1:]
        if len(tail) <= 8:
            suffix = slug[last_dash:]
            prefix_part = slug[:last_dash]

    available = max_len - len(suffix)
    if available < 4:
        return slug[:max_len].rstrip("-")

    truncated = prefix_part[:available]
    inner_dash = truncated.rfind("-")
    if inner_dash > available // 2:
        truncated = truncated[:inner_dash]
    truncated = truncated.rstrip("-")

    return truncated + suffix


def _schedule_pv_cleanup(k8s: K8sClient, namespace: str) -> None:
    """Namespace 删除后，延迟清理残留的 Released PV。"""
    async def _run():
        for attempt in range(1, _PV_CLEANUP_RETRIES + 1):
            await asyncio.sleep(_PV_CLEANUP_DELAY)
            try:
                deleted = await k8s.cleanup_released_pvs(namespace)
                if deleted:
                    logger.info("后台清理了 %d 个 Released PV (namespace=%s)", deleted, namespace)
                return
            except Exception as e:
                logger.warning(
                    "后台清理 PV 第 %d 次失败 (namespace=%s): %s",
                    attempt, namespace, e,
                )

    task = asyncio.create_task(_run())
    _bg_tasks.add(task)
    task.add_done_callback(_bg_tasks.discard)

async def cancel_deploy(deploy_id: str) -> str:
    """立即取消部署：清理 K8s namespace + 更新 DB + 杀掉后台协程。

    Returns: 操作结果描述
    """
    from app.core.deps import async_session_factory

    async with async_session_factory() as db:
        # 1. 查部署记录 + 实例
        rec_result = await db.execute(
            select(DeployRecord).where(
                DeployRecord.id == deploy_id,
                DeployRecord.deleted_at.is_(None),
            )
        )
        record = rec_result.scalar_one_or_none()
        if not record:
            return "部署记录不存在"
        if record.status != DeployStatus.running:
            return f"部署已结束（状态: {record.status}）"

        inst_result = await db.execute(
            select(Instance).where(
                Instance.id == record.instance_id,
                Instance.deleted_at.is_(None),
            )
        )
        instance = inst_result.scalar_one_or_none()
        if not instance:
            return "实例记录不存在"

        # 2. 先杀后台协程（防止它继续操作 K8s / DB）
        task = _running_tasks.pop(deploy_id, None)
        if task and not task.done():
            task.cancel()

        # 3. 清理资源（K8s namespace 或 Docker container）
        ns_cleaned = False
        cluster = None
        try:
            if instance.compute_provider == "docker":
                from app.services.runtime.registries.compute_registry import COMPUTE_REGISTRY
                from app.services.runtime.compute.base import ComputeHandle
                docker_spec = COMPUTE_REGISTRY.get("docker")
                if docker_spec and docker_spec.provider:
                    adv = _json.loads(instance.advanced_config) if instance.advanced_config else {}
                    handle = ComputeHandle(
                        provider="docker", instance_id=instance.id,
                        namespace=instance.namespace, endpoint=instance.ingress_domain or "",
                        status=instance.status,
                        extra={"compose_path": adv.get("compose_path", ""), "slug": instance.slug},
                    )
                    await docker_spec.provider.destroy_instance(handle)
                    ns_cleaned = True
                    logger.info("取消部署，已清理 Docker 容器: %s", instance.slug)
            else:
                cluster_result = await db.execute(
                    select(Cluster).where(
                        Cluster.id == instance.cluster_id,
                        Cluster.deleted_at.is_(None),
                    )
                )
                cluster = cluster_result.scalar_one_or_none()
                if cluster and cluster.is_k8s and cluster.credentials_encrypted:
                    from app.services.runtime.registries.compute_registry import require_k8s_client
                    k8s = await require_k8s_client(cluster)
                    await k8s.core.delete_namespace(instance.namespace)
                    ns_cleaned = True
                    logger.info("取消部署，已清理命名空间: %s", instance.namespace)
                    _schedule_pv_cleanup(k8s, instance.namespace)
        except Exception:
            logger.warning("取消部署，清理资源失败: %s", instance.namespace)

        if cluster and cluster.proxy_endpoint:
            try:
                from app.services.k8s.client_manager import GATEWAY_NS
                gateway_api = await k8s_manager.get_gateway_client()
                gateway_k8s = K8sClient(gateway_api)
                k8s_name = instance.slug or instance.name
                await gateway_k8s.networking.delete_namespaced_ingress(
                    f"proxy-{k8s_name}", GATEWAY_NS,
                )
                logger.info("取消部署，已清理网关代理 Ingress: proxy-%s", k8s_name)
            except Exception:
                logger.warning("取消部署，清理网关代理 Ingress proxy-%s 失败", instance.slug or instance.name)

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
            step=len(DEPLOY_STEPS_BASE),
            total_steps=len(DEPLOY_STEPS_BASE),
            current_step="已取消",
            status="failed",
            message=f"部署已取消{'，命名空间已清理' if ns_cleaned else ''}",
            percent=100,
        ).model_dump(),
    )

    return "已取消" + ("，命名空间已清理" if ns_cleaned else "")


DEPLOY_STEPS_BASE = [
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

    if cluster.compute_provider == "docker":
        try:
            proc = await asyncio.create_subprocess_exec(
                "docker", "compose", "version",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=10)
            if proc.returncode == 0:
                items.append(PrecheckItem(name="Docker", status="pass", message=stdout.decode().strip()))
            else:
                err_text = stderr.decode().strip()
                if "permission denied" in err_text.lower() or "connect" in err_text.lower():
                    err_text = "无法连接 Docker daemon，请确认 Docker socket 已挂载（/var/run/docker.sock）"
                items.append(PrecheckItem(name="Docker", status="fail", message=err_text or "Docker Compose 不可用"))
                return PrecheckResult(passed=False, items=items)
        except FileNotFoundError:
            items.append(PrecheckItem(name="Docker", status="fail", message="Docker CLI 未安装"))
            return PrecheckResult(passed=False, items=items)
        except asyncio.TimeoutError:
            items.append(PrecheckItem(name="Docker", status="fail", message="Docker 环境检查超时"))
            return PrecheckResult(passed=False, items=items)
        except Exception:
            items.append(PrecheckItem(name="Docker", status="fail", message="Docker 环境检查失败"))
            return PrecheckResult(passed=False, items=items)
    else:
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

    # Image version — fall back to catalog default when not specified
    if not req.image_version:
        from app.services import engine_version_service
        default_ev = await engine_version_service.get_default(req.runtime, db)
        if default_ev:
            req.image_version = default_ev.image_tag
        else:
            items.append(PrecheckItem(
                name="镜像", status="fail",
                message="未指定镜像版本且管理员未设置默认版本，请联系管理员在引擎版本管理中发布并设置默认版本",
            ))
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
    storage_class: str | None
    storage_size: str
    quota_cpu: str
    quota_mem: str
    env_vars: dict | None
    advanced_config: dict | None
    proxy_endpoint: str | None = None
    api_server_url: str | None = None
    org_id: str | None = None
    has_llm_configs: bool = False
    template_id: str | None = None
    template_gene_slugs: list[str] | None = None
    compute_provider: str = "k8s"
    runtime: str = "openclaw"
    pvc_access_mode: str | None = None


async def deploy_instance(
    req: DeployRequest, user: User, db: AsyncSession, org_id: str | None = None
) -> str:
    """
    同步阶段：创建 Instance + DeployRecord，立即返回 record.id。
    不执行任何 K8s 操作，由调用方用 asyncio.create_task 启动后台管道。
    """
    adapter = get_deploy_adapter()
    effective_cluster_id, org = await adapter.resolve_cluster(
        req.cluster_id, db, org_id,
        cpu_limit=req.cpu_limit,
        mem_limit=req.mem_limit,
        storage_size=req.storage_size,
    )

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

    # namespace: adapter 决定命名格式，K8s 限制 63 字符
    auto_ns = adapter.build_namespace(slug, org)
    max_slug_len = min(_K8S_NAME_MAX - (len(auto_ns) - len(slug)), _DEPLOY_NAME_MAX)
    if len(slug) > max_slug_len:
        original_slug = slug
        slug = _truncate_slug_preserve_suffix(slug, max_slug_len)
        auto_ns = adapter.build_namespace(slug, org)
        logger.info("slug 截断: %s -> %s (max_slug_len=%d)", original_slug, slug, max_slug_len)

    namespace = req.namespace or auto_ns

    is_docker = cluster.compute_provider == "docker"

    # Docker: 分配宿主机端口
    docker_host_port: int | None = None
    if is_docker:
        from app.services.docker_constants import DOCKER_BASE_PORT
        used_ports: set[int] = set()
        port_result = await db.execute(
            select(Instance.env_vars).where(
                Instance.compute_provider == "docker",
                Instance.deleted_at.is_(None),
            )
        )
        for row in port_result.scalars().all():
            if row:
                try:
                    ev = _json.loads(row)
                    p = ev.get("DOCKER_HOST_PORT")
                    if p:
                        used_ports.add(int(p))
                except (ValueError, TypeError):
                    pass
        docker_host_port = DOCKER_BASE_PORT
        while docker_host_port in used_ports:
            docker_host_port += 1
        namespace = f"docker-{slug}"

    if not is_docker:
        _parsed = _urlparse(settings.AGENT_API_BASE_URL or "")
        if _parsed.hostname in ("localhost", "127.0.0.1", "0.0.0.0", "::1"):
            raise BadRequestError(
                message="AGENT_API_BASE_URL 当前为 localhost，K8s 集群中的 AI 员工无法通过此地址连接后端。"
                        "请在后端 .env 中将 AGENT_API_BASE_URL 设置为 K8s Pod 可达的外部地址后重启后端。",
                message_key="errors.deploy.localhost_not_reachable",
            )

        from app.services.config_service import get_config
        _ingress_domain = await get_config("ingress_base_domain", db)
        if not _ingress_domain:
            raise BadRequestError(
                message="K8s 部署需要配置访问域名（ingress_base_domain），"
                        "否则 AI 员工将无法通过浏览器访问 Web UI。"
                        "请在系统设置中配置后再部署。",
                message_key="errors.deploy.ingress_base_domain_required",
            )

    from app.models.org_llm_key import OrgModelProvider
    org_prov_result = await db.execute(
        select(OrgModelProvider.provider).where(
            OrgModelProvider.org_id == (org_id or org.id),
            OrgModelProvider.is_active.is_(True),
            OrgModelProvider.deleted_at.is_(None),
        )
    )
    org_active_providers = [r[0] for r in org_prov_result.all()]

    env_vars = dict(req.env_vars) if req.env_vars else {}
    gateway_token = env_vars.get("GATEWAY_TOKEN") or env_vars.get("OPENCLAW_GATEWAY_TOKEN")
    if not gateway_token:
        gateway_token = _secrets.token_hex(24)
    env_vars["GATEWAY_TOKEN"] = gateway_token
    env_vars["OPENCLAW_GATEWAY_TOKEN"] = gateway_token
    env_vars["NODESKCLAW_TOKEN"] = gateway_token

    env_vars.setdefault("NODESKCLAW_API_URL", settings.AGENT_API_BASE_URL)
    if settings.TUNNEL_BASE_URL:
        env_vars.setdefault("NODESKCLAW_TUNNEL_URL", settings.TUNNEL_BASE_URL)

    if docker_host_port is not None:
        env_vars["DOCKER_HOST_PORT"] = str(docker_host_port)

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
        service_type="ClusterIP" if not is_docker else "docker",
        ingress_domain=f"localhost:{docker_host_port}" if is_docker else None,
        compute_provider="docker" if is_docker else "k8s",
        proxy_token=gateway_token,
        wp_api_key=f"nodeskclaw-wp-{_secrets.token_hex(32)}",
        env_vars=_json.dumps(env_vars),
        advanced_config=_json.dumps(req.advanced_config) if req.advanced_config else None,
        llm_providers=_compute_llm_providers(req.llm_configs, org_active_providers),
        storage_class=req.storage_class,
        storage_size=req.storage_size,
        runtime=req.runtime,
        status=InstanceStatus.deploying,
        created_by=user.id,
        org_id=org_id,
    )
    db.add(instance)
    await db.commit()
    await db.refresh(instance)

    env_vars["NODESKCLAW_INSTANCE_ID"] = str(instance.id)
    instance.env_vars = _json.dumps(env_vars)
    await db.commit()

    from app.models.instance_member import InstanceMember, InstanceRole
    db.add(InstanceMember(
        instance_id=instance.id, user_id=user.id, role=InstanceRole.admin,
    ))
    await db.commit()

    if req.llm_configs:
        from app.models.base import not_deleted
        from app.models.instance_provider_config import InstanceProviderConfig

        for item in req.llm_configs:
            selected_models = normalize_selected_models(item.provider, item.selected_models)
            if item.key_source == "personal" or selected_models or item.base_url or item.api_type:
                db.add(InstanceProviderConfig(
                    instance_id=instance.id,
                    provider=item.provider,
                    key_source=item.key_source,
                    selected_models=selected_models,
                    base_url=item.base_url,
                    api_type=item.api_type,
                ))
        await db.commit()
        logger.info(
            "已保存实例 provider 配置: instance=%s providers=%s",
            instance.id, [c.provider for c in req.llm_configs],
        )

    # 解析模板基因
    template_gene_slugs: list[str] | None = None
    if req.template_id:
        from app.services.instance_template_service import get_template_gene_slugs
        template_gene_slugs = await get_template_gene_slugs(db, req.template_id, org_id)

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
        proxy_endpoint=cluster.proxy_endpoint,
        api_server_url=cluster.api_server_url,
        org_id=org_id,
        has_llm_configs=bool(req.llm_configs),
        template_id=req.template_id,
        template_gene_slugs=template_gene_slugs,
        compute_provider=instance.compute_provider,
        runtime=instance.runtime,
        pvc_access_mode=req.pvc_access_mode,
    )


async def execute_deploy_pipeline(ctx: _DeployContext) -> None:
    """
    后台异步阶段：根据 compute_provider 选择部署方式。
    K8s 走完整的内置管道；Docker/Process 等委托给 ComputeProvider。
    """
    if ctx.compute_provider != "k8s":
        try:
            await _execute_via_compute_provider(ctx)
        finally:
            _unregister_deploy_task(ctx.record_id)
        return

    from app.core.deps import async_session_factory
    from app.services.config_service import get_config

    steps = list(DEPLOY_STEPS_BASE)
    if ctx.has_llm_configs:
        steps.append("应用实例配置")
    if ctx.template_gene_slugs:
        steps.append("安装模板技能基因")
    total = len(steps)

    try:
        await _execute_deploy_inner(ctx, async_session_factory, get_config, total, steps)
    finally:
        _unregister_deploy_task(ctx.record_id)


DOCKER_DEPLOY_STEPS = ["环境预检查", "启动容器", "等待容器就绪", "部署完成"]


async def _execute_via_compute_provider(ctx: _DeployContext) -> None:
    """非 K8s 环境：通过 COMPUTE_REGISTRY 查找对应 provider 并委托部署。"""
    from app.core.deps import async_session_factory
    from app.services.runtime.registries.compute_registry import COMPUTE_REGISTRY
    from app.services.runtime.registries.runtime_registry import RUNTIME_REGISTRY
    from app.services.runtime.compute.base import InstanceComputeConfig

    spec = COMPUTE_REGISTRY.get(ctx.compute_provider)
    if spec is None or spec.provider is None:
        logger.error("未注册的 compute_provider: %s", ctx.compute_provider)
        await _mark_deploy_failed(ctx, f"未注册的 compute_provider: {ctx.compute_provider}")
        return

    provider = spec.provider
    total = len(DOCKER_DEPLOY_STEPS)
    step_names = list(DOCKER_DEPLOY_STEPS)

    env_vars = dict(ctx.env_vars or {})
    if "DOCKER_IMAGE" not in env_vars:
        async with async_session_factory() as db:
            from app.services.registry_service import resolve_image_registry
            image_registry = await resolve_image_registry(db, ctx.runtime) or ctx.runtime or "openclaw"
            env_vars["DOCKER_IMAGE"] = f"{image_registry}:{ctx.image_version}"

    rt_spec = RUNTIME_REGISTRY.get(ctx.runtime)
    gw_port = rt_spec.gateway_port if rt_spec else 18789

    config = InstanceComputeConfig(
        instance_id=ctx.instance_id,
        name=ctx.name,
        slug=ctx.name,
        namespace=ctx.namespace,
        image_version=ctx.image_version,
        runtime=ctx.runtime,
        gateway_port=gw_port,
        replicas=ctx.replicas,
        cpu_request=ctx.cpu_request,
        cpu_limit=ctx.cpu_limit,
        mem_request=ctx.mem_request,
        mem_limit=ctx.mem_limit,
        storage_class=ctx.storage_class,
        storage_size=ctx.storage_size,
        env_vars=env_vars,
        advanced_config=ctx.advanced_config or {},
    )

    event_bus.publish(
        "deploy_progress",
        DeployProgress(
            deploy_id=ctx.record_id, step=1, total_steps=total,
            current_step=step_names[0], status="in_progress",
            message=None, percent=10,
            step_names=step_names,
        ).model_dump(),
    )

    event_bus.publish(
        "deploy_progress",
        DeployProgress(
            deploy_id=ctx.record_id, step=2, total_steps=total,
            current_step=step_names[1], status="in_progress",
            message=None, percent=30,
        ).model_dump(),
    )

    try:
        result = await provider.create_instance(config)
        logger.info("ComputeProvider[%s] 部署完成: %s", ctx.compute_provider, result)
    except Exception as e:
        logger.exception("ComputeProvider[%s] 部署失败", ctx.compute_provider)
        await _mark_deploy_failed(ctx, str(e)[:500])
        event_bus.publish(
            "deploy_progress",
            DeployProgress(
                deploy_id=ctx.record_id, step=total, total_steps=total,
                current_step="失败", status="failed",
                message=str(e)[:200], percent=100,
            ).model_dump(),
        )
        return

    # ── 等待容器就绪（对齐 K8s Step 9 的 readiness 门控） ──
    probe_path = rt_spec.health_probe_path if rt_spec else "/healthz"
    container_ready = False

    event_bus.publish(
        "deploy_progress",
        DeployProgress(
            deploy_id=ctx.record_id, step=3, total_steps=total,
            current_step=step_names[2], status="in_progress",
            message=None, percent=50,
        ).model_dump(),
    )

    if probe_path and result.endpoint:
        from app.services.runtime.compute.base import http_probe

        for tick in range(30):  # 30 x 2s = 60s
            probe_result = await http_probe(result.endpoint, path=probe_path)
            if probe_result.get("healthy"):
                container_ready = True
                break
            pct = 50 + min(tick, 15)  # 50 → 65, 不超过 65
            event_bus.publish(
                "deploy_progress",
                DeployProgress(
                    deploy_id=ctx.record_id, step=3, total_steps=total,
                    current_step=step_names[2], status="in_progress",
                    message=f"等待容器健康检查通过... ({(tick + 1) * 2}s/60s)",
                    percent=pct,
                ).model_dump(),
            )
            await asyncio.sleep(2)
    else:
        await asyncio.sleep(5)
        container_ready = True

    if not container_ready:
        timeout_msg = "容器健康检查超时（60s）"
        logger.error("Docker 部署超时: instance=%s endpoint=%s path=%s", ctx.name, result.endpoint, probe_path)
        try:
            await provider.destroy_instance(result)
        except Exception:
            logger.warning("健康检查超时后清理容器失败", exc_info=True)
        await _mark_deploy_failed(ctx, timeout_msg)
        event_bus.publish(
            "deploy_progress",
            DeployProgress(
                deploy_id=ctx.record_id, step=total, total_steps=total,
                current_step="失败", status="failed",
                message=timeout_msg, percent=100,
            ).model_dump(),
        )
        return

    async with async_session_factory() as db:
        rec_result = await db.execute(
            select(DeployRecord).where(
                DeployRecord.id == ctx.record_id,
                DeployRecord.deleted_at.is_(None),
            )
        )
        record = rec_result.scalar_one()
        record.status = DeployStatus.success
        record.finished_at = datetime.now(timezone.utc)

        inst_result = await db.execute(
            select(Instance).where(
                Instance.id == ctx.instance_id,
                Instance.deleted_at.is_(None),
            )
        )
        instance = inst_result.scalar_one()
        instance.status = InstanceStatus.running

        if hasattr(result, "extra") and result.extra.get("compose_path"):
            adv = _json.loads(instance.advanced_config) if instance.advanced_config else {}
            adv["compose_path"] = result.extra["compose_path"]
            instance.advanced_config = _json.dumps(adv)

        await db.commit()

        if ctx.runtime == "openclaw":
            from app.services.llm_config_service import (
                ensure_openclaw_gateway_config,
                sync_openclaw_llm_config,
            )
            try:
                await ensure_openclaw_gateway_config(instance, db)
                if ctx.has_llm_configs:
                    await sync_openclaw_llm_config(instance, db)
            except Exception as e:
                logger.warning(
                    "Docker 部署后注入配置失败（非致命） [deploy_id=%s, instance_id=%s]: %s",
                    ctx.record_id,
                    ctx.instance_id,
                    e,
                    exc_info=True,
                )

    event_bus.publish(
        "deploy_progress",
        DeployProgress(
            deploy_id=ctx.record_id, step=total, total_steps=total,
            current_step=step_names[-1], status="success",
            message="部署成功", percent=100,
        ).model_dump(),
    )


async def _mark_deploy_failed(ctx: _DeployContext, message: str) -> None:
    """标记部署记录为失败并软删除实例。"""
    from app.core.deps import async_session_factory

    try:
        async with async_session_factory() as db:
            rec_result = await db.execute(
                select(DeployRecord).where(
                    DeployRecord.id == ctx.record_id,
                    DeployRecord.deleted_at.is_(None),
                )
            )
            record = rec_result.scalar_one()
            record.status = DeployStatus.failed
            record.message = message
            record.finished_at = datetime.now(timezone.utc)

            inst_result = await db.execute(
                select(Instance).where(
                    Instance.id == ctx.instance_id,
                    Instance.deleted_at.is_(None),
                )
            )
            instance = inst_result.scalar_one()
            instance.soft_delete()
            await db.execute(
                update(DeployRecord)
                .where(DeployRecord.instance_id == ctx.instance_id, DeployRecord.deleted_at.is_(None))
                .values(deleted_at=func.now())
            )
            await db.commit()
    except Exception:
        logger.exception("标记部署失败状态时出错")


async def _execute_deploy_inner(ctx, async_session_factory, get_config, total, steps) -> None:
    """实际的部署管道逻辑（拆出来方便 finally 注销任务）。"""

    first_event = True

    def _publish(
        step: int, step_name: str, status: str = "in_progress",
        message: str | None = None, logs: list[str] | None = None,
    ):
        nonlocal first_event
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
                step_names=steps if first_event else None,
            ).model_dump(),
        )
        first_event = False

    await asyncio.sleep(0.3)

    async with async_session_factory() as db:
        try:
            # Step 1: 预检（同步阶段已完成，标记通过）
            _publish(1, steps[0])

            cluster_result = await db.execute(
                select(Cluster).where(
                    Cluster.id == ctx.cluster_id,
                    Cluster.deleted_at.is_(None),
                )
            )
            cluster = cluster_result.scalar_one()
            from app.services.runtime.registries.compute_registry import require_k8s_client
            k8s = await require_k8s_client(cluster)

            labels = build_labels(ctx.name, ctx.instance_id, ctx.image_version)

            # Step 2: 创建命名空间 + ResourceQuota
            _publish(2, steps[1])
            adapter = get_deploy_adapter()
            ns_labels = adapter.get_namespace_labels(ctx.org_id)
            await k8s.ensure_namespace(ctx.namespace, extra_labels=ns_labels)
            rq = build_resource_quota(
                f"{ctx.namespace}-quota", ctx.namespace,
                cpu=ctx.quota_cpu, mem=ctx.quota_mem,
                storage=ctx.storage_size,
            )
            await k8s.create_or_skip(k8s.core.create_namespaced_resource_quota, ctx.namespace, rq)

            # Step 3: 创建 ConfigMap
            _publish(3, steps[2])
            if ctx.env_vars:
                cm = build_configmap(f"{ctx.name}-config", ctx.namespace, ctx.env_vars, labels)
                await k8s.create_or_skip(k8s.core.create_namespaced_config_map, ctx.namespace, cm)

            # Step 4: 创建 PVC（使用实例指定的 StorageClass）
            _publish(4, steps[3])
            pvc_name = f"{ctx.name}-root-data"
            logger.info("使用 StorageClass: %s, 存储大小: %s", ctx.storage_class, ctx.storage_size)
            access_modes = [ctx.pvc_access_mode] if ctx.pvc_access_mode else None
            pvc = build_pvc(pvc_name, ctx.namespace, ctx.storage_size, ctx.storage_class, labels, access_modes=access_modes)
            await k8s.create_or_skip(k8s.core.create_namespaced_persistent_volume_claim, ctx.namespace, pvc)

            # Step 5: 创建 Deployment（含镜像拉取凭据）
            _publish(5, steps[4])
            from app.services.registry_service import resolve_image_registry
            from app.services.runtime.registries.runtime_registry import RUNTIME_REGISTRY as _RT_REG
            image_registry = await resolve_image_registry(db, ctx.runtime) or "openclaw"
            image = f"{image_registry}:{ctx.image_version}"
            _rt_spec = _RT_REG.get(ctx.runtime)
            gw_port = _rt_spec.gateway_port if _rt_spec else 18789

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

            _liveness_path = _rt_spec.health_probe_path if _rt_spec else "/healthz"
            _readiness_path = _rt_spec.readiness_probe_path if _rt_spec else None
            _has_init = _rt_spec.has_init_script if _rt_spec else True
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
                port=gw_port,
                env_vars=ctx.env_vars,
                advanced_config=ctx.advanced_config,
                image_pull_secret=pull_secret_name,
                health_probe_path=_liveness_path,
                readiness_probe_path=_readiness_path or _liveness_path,
                has_init_script=_has_init,
            )
            await k8s.apply(
                k8s.apps.create_namespaced_deployment,
                k8s.apps.patch_namespaced_deployment,
                ctx.namespace,
                ctx.name,
                dep,
            )

            # Step 6: 创建 Service（固定 ClusterIP）
            _publish(6, steps[5])
            svc = build_service(ctx.name, ctx.namespace, labels, port=gw_port)
            await k8s.create_or_skip(k8s.core.create_namespaced_service, ctx.namespace, svc)

            # Step 7: 创建 Ingress（自动子域名路由）
            _publish(7, steps[6])
            ingress_base_domain = await get_config("ingress_base_domain", db)
            subdomain_suffix = await get_config("ingress_subdomain_suffix", db)
            tls_secret_name = await get_config("tls_secret_name", db)
            if ingress_base_domain:
                if subdomain_suffix:
                    ingress_host = f"{ctx.name}-{subdomain_suffix}.{ingress_base_domain}"
                else:
                    ingress_host = f"{ctx.name}.{ingress_base_domain}"
                inst_tls = adapter.get_tls_secret(tls_secret_name, bool(ctx.proxy_endpoint))
                ing = build_ingress(
                    ctx.name, ctx.namespace, ingress_host, labels,
                    port=gw_port,
                    tls_secret_name=inst_tls,
                    ingress_class=cluster.ingress_class,
                )
                await k8s.create_or_skip(k8s.networking.create_namespaced_ingress, ctx.namespace, ing)
                inst_result = await db.execute(
                    select(Instance).where(
                        Instance.id == ctx.instance_id,
                        Instance.deleted_at.is_(None),
                    )
                )
                instance = inst_result.scalar_one()
                instance.ingress_domain = ingress_host
                await db.commit()
                await adapter.setup_proxy(ctx, ingress_host)
            else:
                logger.error("ingress_base_domain 未配置但部署已进入异步管道（前置校验应已拦截）")

            # Step 8: 配置网络策略（多租户隔离）
            _publish(8, steps[7])
            np_ingress_enabled = (await get_config("network_policy_ingress_enabled", db) or "true") != "false"
            np_egress_enabled = (await get_config("network_policy_egress_enabled", db) or "true") != "false"

            if not np_ingress_enabled and not np_egress_enabled:
                logger.info("NetworkPolicy disabled (both ingress & egress off), skipping for %s", ctx.namespace)
            else:
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

                deny_str = await get_config("egress_deny_cidrs", db) or ""
                ports_str = await get_config("egress_allow_ports", db) or ""
                ingress_cidrs_str = await get_config("ingress_allow_cidrs", db) or ""

                deny_cidrs = [c.strip() for c in deny_str.split(",") if c.strip()]
                allow_ports = [int(p.strip()) for p in ports_str.split(",") if p.strip()]
                ingress_cidrs = [c.strip() for c in ingress_cidrs_str.split(",") if c.strip()]

                if ctx.advanced_config:
                    inst_egress = ctx.advanced_config.get("network", {}).get("egress", {})
                    if inst_egress.get("deny_cidrs") is not None:
                        deny_cidrs = inst_egress["deny_cidrs"]
                    if inst_egress.get("allow_ports") is not None:
                        allow_ports = inst_egress["allow_ports"]

                np = build_network_policy(
                    f"{ctx.name}-isolation", ctx.namespace, labels,
                    peer_namespaces,
                    org_id=adapter.get_network_policy_org_id(ctx.org_id),
                    egress_deny_cidrs=deny_cidrs,
                    egress_allow_ports=allow_ports,
                    platform_namespace=settings.PLATFORM_NAMESPACE,
                    ingress_enabled=np_ingress_enabled,
                    egress_enabled=np_egress_enabled,
                    ingress_allow_cidrs=ingress_cidrs,
                )
                try:
                    await k8s.networking.create_namespaced_network_policy(ctx.namespace, np)
                except Exception:
                    await k8s.networking.patch_namespaced_network_policy(
                        f"{ctx.name}-isolation", ctx.namespace, np
                    )

            # Step 9: 等待 Deployment 就绪（最多 300 秒）
            _publish(9, steps[8], logs=["开始等待 Pod 就绪..."])
            dep_status: dict = {"ready_replicas": 0, "available_replicas": 0}
            deployment_ready = False
            label_selector = f"app.kubernetes.io/name={ctx.name}"

            for tick in range(150):  # 150 x 2s = 300s
                dep_status = await k8s.get_deployment_status(ctx.namespace, ctx.name)
                if dep_status["ready_replicas"] >= ctx.replicas:
                    deployment_ready = True
                    break

                # 每 4 秒（2 个 tick）推送一次 Pod 诊断日志
                if tick % 2 == 1:
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
                        logger.warning("Failed to list PVCs for deploy diag in %s", ctx.namespace, exc_info=True)

                    # ── K8s Events（最近 5 条） ──
                    try:
                        events = await k8s.core.list_namespaced_event(ctx.namespace)
                        recent = sorted(events.items, key=lambda e: e.last_timestamp or e.metadata.creation_timestamp or "", reverse=True)[:5]
                        for ev in recent:
                            diag_lines.append(f"Event: {ev.reason} — {(ev.message or '')[:200]}")
                    except Exception:
                        logger.warning("Failed to list Events for deploy diag in %s", ctx.namespace, exc_info=True)

                    # ── Deployment conditions ──
                    for cond in dep_status.get("conditions", []):
                        diag_lines.append(f"{cond['type']}: {cond.get('message', '')[:100]}")

                    elapsed = (tick + 1) * 2
                    diag_lines.append(f"已等待 {elapsed}s / 300s")
                    # 同时写入后端日志文件，方便事后排查
                    logger.info("[%s] 等待就绪诊断:\n  %s", ctx.name, "\n  ".join(diag_lines))
                    _publish(9, steps[8], logs=diag_lines)

                await asyncio.sleep(2)

            rec_result = await db.execute(
                select(DeployRecord).where(
                    DeployRecord.id == ctx.record_id,
                    DeployRecord.deleted_at.is_(None),
                )
            )
            record = rec_result.scalar_one()
            inst_result = await db.execute(
                select(Instance).where(
                    Instance.id == ctx.instance_id,
                    Instance.deleted_at.is_(None),
                )
            )
            instance = inst_result.scalar_one()

            if deployment_ready:
                record.status = DeployStatus.success
                record.finished_at = datetime.now(timezone.utc)
                instance.status = InstanceStatus.running
                instance.available_replicas = dep_status.get("available_replicas", 0)
                await db.commit()

                llm_sync_warning = ""
                if ctx.runtime == "openclaw":
                    from app.services.llm_config_service import (
                        ensure_openclaw_gateway_config,
                        sync_openclaw_llm_config,
                    )

                    try:
                        if ctx.has_llm_configs:
                            config_step = len(DEPLOY_STEPS_BASE) + 1
                            _publish(config_step, "应用实例配置")
                            await ensure_openclaw_gateway_config(instance, db)
                            await sync_openclaw_llm_config(instance, db)
                            _publish(config_step, "应用实例配置", status="success")
                        else:
                            await ensure_openclaw_gateway_config(instance, db)
                    except Exception as e:
                        logger.warning(
                            "LLM 配置同步失败（非致命） [deploy_id=%s, instance_id=%s]: %s",
                            ctx.record_id, ctx.instance_id, e, exc_info=True,
                        )
                        llm_sync_warning = "（LLM 配置同步失败，可在管理后台手动重试）"
                        if ctx.has_llm_configs:
                            _publish(config_step, "应用实例配置", status="failed",
                                     message=str(e)[:200])

                gene_install_warning = ""
                if ctx.template_gene_slugs:
                    gene_step = len(steps)
                    _publish(gene_step, "安装模板技能基因")
                    failed_genes: list[str] = []
                    max_retries = 2
                    from app.services.gene_service import install_gene_prerestart
                    for idx, gene_slug in enumerate(ctx.template_gene_slugs):
                        installed = False
                        for attempt in range(max_retries + 1):
                            try:
                                await install_gene_prerestart(ctx.instance_id, gene_slug)
                                installed = True
                                break
                            except Exception as ge:
                                if attempt < max_retries:
                                    logger.warning(
                                        "模板基因安装失败（第 %d 次重试）: slug=%s err=%s",
                                        attempt + 1, gene_slug, ge,
                                    )
                                    await asyncio.sleep(2)
                                else:
                                    logger.warning(
                                        "模板基因安装失败（已重试 %d 次）: slug=%s err=%s",
                                        max_retries, gene_slug, ge,
                                    )
                                    failed_genes.append(gene_slug)
                        if installed and idx < len(ctx.template_gene_slugs) - 1:
                            await asyncio.sleep(1)

                    installed_count = len(ctx.template_gene_slugs) - len(failed_genes)
                    if installed_count > 0:
                        try:
                            from app.services.instance_service import restart_instance
                            await restart_instance(ctx.instance_id, db)
                        except Exception as restart_err:
                            logger.warning("模板基因安装后重启失败: %s", restart_err)

                    if failed_genes:
                        gene_install_warning = f"（{len(failed_genes)} 个基因安装失败: {', '.join(failed_genes)}）"
                        _publish(gene_step, "安装模板技能基因", status="success",
                                 message=f"{len(ctx.template_gene_slugs) - len(failed_genes)}/{len(ctx.template_gene_slugs)} 安装成功")
                    else:
                        _publish(gene_step, "安装模板技能基因", status="success")

                    if ctx.template_id:
                        try:
                            from app.services.instance_template_service import increment_use_count
                            await increment_use_count(db, ctx.template_id)
                        except Exception:
                            logger.warning("Failed to increment template use count for %s", ctx.template_id, exc_info=True)

                success_msg = f"部署成功{llm_sync_warning}{gene_install_warning}"
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
                    _schedule_pv_cleanup(k8s, ctx.namespace)
                except Exception:
                    logger.warning("清理命名空间 %s 失败", ctx.namespace)

                await adapter.cleanup_proxy(ctx)

                record.status = DeployStatus.failed
                record.message = f"就绪超时: {cond_msg}"[:500]
                record.finished_at = datetime.now(timezone.utc)

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
            logger.info("部署协程被取消: %s", ctx.name)
            return

        except Exception as e:
            logger.exception("部署失败: %s", ctx.name)
            ns_cleaned = False
            try:
                cleanup_k8s = await require_k8s_client(cluster)
                await cleanup_k8s.core.delete_namespace(ctx.namespace)
                ns_cleaned = True
                logger.info("部署异常，已清理命名空间: %s", ctx.namespace)
                _schedule_pv_cleanup(cleanup_k8s, ctx.namespace)
            except Exception:
                logger.warning("清理命名空间 %s 失败", ctx.namespace)

            await adapter.cleanup_proxy(ctx)

            try:
                rec_result = await db.execute(
                    select(DeployRecord).where(
                        DeployRecord.id == ctx.record_id,
                        DeployRecord.deleted_at.is_(None),
                    )
                )
                record = rec_result.scalar_one()
                record.status = DeployStatus.failed
                record.message = str(e)[:500]
                record.finished_at = datetime.now(timezone.utc)

                inst_result = await db.execute(
                    select(Instance).where(
                        Instance.id == ctx.instance_id,
                        Instance.deleted_at.is_(None),
                    )
                )
                instance = inst_result.scalar_one()

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


# ── Rebuild ────────────────────────────────────────────────

REBUILD_STEPS = [
    "检查实例状态",
    "重建命名空间",
    "重建 ConfigMap",
    "重建 PVC",
    "重建 Deployment",
    "重建 Service",
    "重建 Ingress",
    "配置网络策略",
    "等待 Deployment 就绪",
]


async def rebuild_instance(
    instance_id: str, user_id: str, db: AsyncSession, org_id: str | None = None
) -> tuple[str, "_DeployContext"]:
    """从 DB 状态重建 K8s 资源（同步阶段）。"""
    from app.core.exceptions import ConflictError

    result = await db.execute(
        select(Instance).where(Instance.id == instance_id, Instance.deleted_at.is_(None))
    )
    instance = result.scalar_one_or_none()
    if not instance:
        raise NotFoundError("实例不存在", message_key="errors.instance.not_found")
    if org_id and instance.org_id != org_id:
        raise NotFoundError("实例不存在", message_key="errors.instance.not_found")

    transitional_statuses = {
        InstanceStatus.deploying, InstanceStatus.updating,
        InstanceStatus.rebuilding, InstanceStatus.restoring, InstanceStatus.deleting,
    }
    if instance.status in transitional_statuses:
        raise ConflictError(
            message=f"实例正在 {instance.status.value}，请等待完成后再操作",
            message_key="errors.instance.in_transitional_state",
        )

    cluster_result = await db.execute(
        select(Cluster).where(Cluster.id == instance.cluster_id, Cluster.deleted_at.is_(None))
    )
    cluster = cluster_result.scalar_one_or_none()
    if not cluster:
        raise NotFoundError("关联集群不存在", message_key="errors.cluster.not_found")

    instance.status = InstanceStatus.rebuilding
    await db.commit()

    max_rev = await db.execute(
        select(func.coalesce(func.max(DeployRecord.revision), 0)).where(
            DeployRecord.instance_id == instance.id, DeployRecord.deleted_at.is_(None)
        )
    )
    next_rev = max_rev.scalar() + 1

    record = DeployRecord(
        instance_id=instance.id,
        revision=next_rev,
        action=DeployAction.rebuild,
        image_version=instance.image_version,
        status=DeployStatus.running,
        triggered_by=user_id,
        started_at=datetime.now(timezone.utc),
    )
    db.add(record)
    await db.commit()
    await db.refresh(record)

    env_vars = _json.loads(instance.env_vars) if instance.env_vars else {}
    advanced = _json.loads(instance.advanced_config) if instance.advanced_config else None

    ctx = _DeployContext(
        record_id=record.id,
        instance_id=instance.id,
        cluster_id=cluster.id,
        name=instance.slug or instance.name,
        namespace=instance.namespace,
        image_version=instance.image_version,
        replicas=instance.replicas,
        cpu_request=instance.cpu_request,
        cpu_limit=instance.cpu_limit,
        mem_request=instance.mem_request,
        mem_limit=instance.mem_limit,
        storage_class=instance.storage_class,
        storage_size=instance.storage_size,
        quota_cpu=instance.quota_cpu,
        quota_mem=instance.quota_mem,
        env_vars=env_vars,
        advanced_config=advanced,
        proxy_endpoint=cluster.proxy_endpoint,
        api_server_url=cluster.api_server_url,
        org_id=instance.org_id,
        compute_provider=instance.compute_provider,
        runtime=instance.runtime,
    )
    return record.id, ctx


async def execute_rebuild_pipeline(ctx: _DeployContext) -> None:
    """后台重建管道：从 DB 状态重建全部 K8s 资源（不删除实例记录）。"""
    from app.core.deps import async_session_factory
    from app.services.config_service import get_config
    from app.services.runtime.registries.compute_registry import require_k8s_client

    steps = list(REBUILD_STEPS)
    total = len(steps)

    def _publish(step: int, step_name: str, *, status: str = "in_progress",
                 message: str = "", logs: list[str] | None = None) -> None:
        payload = DeployProgress(
            deploy_id=ctx.record_id,
            step=step,
            total_steps=total,
            current_step=step_name,
            status=status,
            message=message,
            percent=round(step / total * 100) if status in ("success", "failed") else round((step - 0.5) / total * 100),
            logs=logs,
        )
        if step == 1:
            payload.step_names = steps
        event_bus.publish("deploy_progress", payload.model_dump())

    try:
        await asyncio.sleep(0.3)
        async with async_session_factory() as db:
            cluster_result = await db.execute(
                select(Cluster).where(Cluster.id == ctx.cluster_id, Cluster.deleted_at.is_(None))
            )
            cluster = cluster_result.scalar_one()
            k8s = await require_k8s_client(cluster)
            labels = build_labels(ctx.name, ctx.instance_id, ctx.image_version)
            adapter = get_deploy_adapter()

            _publish(1, steps[0])

            # Namespace + ResourceQuota
            _publish(2, steps[1])
            ns_labels = adapter.get_namespace_labels(ctx.org_id)
            await k8s.ensure_namespace(ctx.namespace, labels=ns_labels)
            quota = build_resource_quota(ctx.namespace, ctx.name, ctx.quota_cpu, ctx.quota_mem,
                                         storage_size=ctx.storage_size if ctx.storage_class else None)
            await k8s.create_or_skip(quota)

            # ConfigMap
            _publish(3, steps[2])
            if ctx.env_vars:
                cm = build_configmap(ctx.namespace, ctx.name, ctx.env_vars)
                await k8s.create_or_skip(cm)

            # PVC
            _publish(4, steps[3])
            pvc = build_pvc(ctx.namespace, ctx.name, ctx.storage_class, ctx.storage_size)
            await k8s.create_or_skip(pvc)

            # Deployment
            _publish(5, steps[4])
            from app.services.registry_service import resolve_image_registry
            image_registry = await resolve_image_registry(db, ctx.runtime) or "openclaw"
            image = f"{image_registry}:{ctx.image_version}"

            from app.services.runtime.registries.runtime_registry import RUNTIME_REGISTRY
            rt_spec = RUNTIME_REGISTRY.get(ctx.runtime)
            gw_port = rt_spec.gateway_port if rt_spec else 18789
            health_path = rt_spec.health_probe_path if rt_spec else "/healthz"
            readiness_path = rt_spec.readiness_probe_path if rt_spec else None

            from app.services.k8s.resource_builder import build_registry_secret, REGISTRY_SECRET_NAME
            reg_secret = build_registry_secret(ctx.namespace, image_registry, db_session=None)
            if reg_secret:
                await k8s.create_or_skip(reg_secret)
            deployment = build_deployment(
                namespace=ctx.namespace, name=ctx.name, image=image,
                replicas=ctx.replicas, labels=labels,
                cpu_request=ctx.cpu_request, cpu_limit=ctx.cpu_limit,
                mem_request=ctx.mem_request, mem_limit=ctx.mem_limit,
                has_configmap=bool(ctx.env_vars), storage_size=ctx.storage_size,
                gateway_port=gw_port, health_probe_path=health_path,
                readiness_probe_path=readiness_path,
                advanced_config=ctx.advanced_config,
                image_pull_secrets=[REGISTRY_SECRET_NAME] if reg_secret else None,
            )
            await k8s.apply(deployment)

            # Service
            _publish(6, steps[5])
            svc = build_service(ctx.namespace, ctx.name, gateway_port=gw_port)
            await k8s.create_or_skip(svc)

            # Ingress
            _publish(7, steps[6])
            ingress_base = await get_config("ingress_base_domain", db)
            tls_secret = await get_config("tls_secret_name", db)
            has_proxy = bool(ctx.proxy_endpoint)
            tls_secret = adapter.get_tls_secret(tls_secret, has_proxy)
            if ingress_base:
                ingress_host = f"{ctx.name}.{ingress_base}"
                ingress = build_ingress(ctx.namespace, ctx.name, ingress_host,
                                        tls_secret_name=tls_secret, gateway_port=gw_port)
                await k8s.create_or_skip(ingress)
                async with async_session_factory() as db2:
                    inst = (await db2.execute(
                        select(Instance).where(Instance.id == ctx.instance_id)
                    )).scalar_one()
                    inst.ingress_domain = ingress_host
                    await db2.commit()
                await adapter.setup_proxy(ctx, ingress_host)

            # NetworkPolicy
            _publish(8, steps[7])
            np_ingress_on = (await get_config("network_policy_ingress_enabled", db) or "true") != "false"
            np_egress_on = (await get_config("network_policy_egress_enabled", db) or "true") != "false"
            np_name = f"{ctx.name}-isolation"

            if not np_ingress_on and not np_egress_on:
                logger.info("NetworkPolicy disabled, skipping for %s", ctx.namespace)
                try:
                    await k8s.networking.delete_namespaced_network_policy(np_name, ctx.namespace)
                    logger.info("Cleaned up old NetworkPolicy %s/%s", ctx.namespace, np_name)
                except Exception:
                    pass
            else:
                peer_namespaces: list[str] = []
                if ctx.advanced_config and ctx.advanced_config.get("network", {}).get("peers"):
                    for pid in ctx.advanced_config["network"]["peers"]:
                        peer_result = await db.execute(
                            select(Instance).where(Instance.id == pid, Instance.deleted_at.is_(None))
                        )
                        peer_inst = peer_result.scalar_one_or_none()
                        if peer_inst:
                            peer_namespaces.append(peer_inst.namespace)

                deny_str = await get_config("egress_deny_cidrs", db) or ""
                ports_str = await get_config("egress_allow_ports", db) or ""
                ingress_cidrs_str = await get_config("ingress_allow_cidrs", db) or ""

                deny_cidrs = [c.strip() for c in deny_str.split(",") if c.strip()]
                allow_ports = [int(p.strip()) for p in ports_str.split(",") if p.strip()]
                ingress_cidrs = [c.strip() for c in ingress_cidrs_str.split(",") if c.strip()]

                if ctx.advanced_config:
                    inst_egress = ctx.advanced_config.get("network", {}).get("egress", {})
                    if inst_egress.get("deny_cidrs") is not None:
                        deny_cidrs = inst_egress["deny_cidrs"]
                    if inst_egress.get("allow_ports") is not None:
                        allow_ports = inst_egress["allow_ports"]

                np = build_network_policy(
                    np_name, ctx.namespace, labels,
                    peer_namespaces,
                    org_id=adapter.get_network_policy_org_id(ctx.org_id),
                    egress_deny_cidrs=deny_cidrs,
                    egress_allow_ports=allow_ports,
                    platform_namespace=settings.PLATFORM_NAMESPACE,
                    ingress_enabled=np_ingress_on,
                    egress_enabled=np_egress_on,
                    ingress_allow_cidrs=ingress_cidrs,
                )
                try:
                    await k8s.networking.create_namespaced_network_policy(ctx.namespace, np)
                except Exception:
                    try:
                        await k8s.networking.patch_namespaced_network_policy(
                            np_name, ctx.namespace, np)
                    except Exception:
                        logger.warning("NetworkPolicy create/patch failed for %s", ctx.namespace, exc_info=True)

            # Wait for Deployment ready
            _publish(9, steps[8])
            deployment_ready = False
            dep_status = {}
            for tick in range(150):
                dep_status = await k8s.get_deployment_status(ctx.namespace, ctx.name)
                if dep_status.get("ready"):
                    deployment_ready = True
                    break
                await asyncio.sleep(2)

            rec_result = await db.execute(
                select(DeployRecord).where(DeployRecord.id == ctx.record_id, DeployRecord.deleted_at.is_(None))
            )
            record = rec_result.scalar_one()
            inst_result = await db.execute(
                select(Instance).where(Instance.id == ctx.instance_id, Instance.deleted_at.is_(None))
            )
            instance = inst_result.scalar_one()

            if deployment_ready:
                record.status = DeployStatus.success
                record.finished_at = datetime.now(timezone.utc)
                instance.status = InstanceStatus.running
                instance.available_replicas = dep_status.get("available_replicas", 0)
                await db.commit()
                _publish(total, "完成", status="success", message="重建成功")
                logger.info("重建成功: %s (namespace=%s)", ctx.name, ctx.namespace)
            else:
                record.status = DeployStatus.failed
                record.message = "重建超时: Deployment 未就绪"
                record.finished_at = datetime.now(timezone.utc)
                instance.status = InstanceStatus.failed
                await db.commit()
                _publish(total, "失败", status="failed", message="重建超时: Deployment 未就绪")
                logger.warning("重建超时: %s (namespace=%s)", ctx.name, ctx.namespace)

    except asyncio.CancelledError:
        logger.info("重建协程被取消: %s", ctx.name)
        return

    except Exception as e:
        logger.exception("重建失败: %s", ctx.name)
        try:
            async with async_session_factory() as db:
                rec = (await db.execute(
                    select(DeployRecord).where(DeployRecord.id == ctx.record_id, DeployRecord.deleted_at.is_(None))
                )).scalar_one()
                rec.status = DeployStatus.failed
                rec.message = str(e)[:500]
                rec.finished_at = datetime.now(timezone.utc)
                inst = (await db.execute(
                    select(Instance).where(Instance.id == ctx.instance_id, Instance.deleted_at.is_(None))
                )).scalar_one()
                inst.status = InstanceStatus.failed
                await db.commit()
        except Exception:
            logger.exception("更新重建失败状态时出错")
        _publish(total, "失败", status="failed", message=str(e)[:200])

    finally:
        _unregister_deploy_task(ctx.record_id)
