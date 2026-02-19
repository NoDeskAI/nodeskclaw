"""LLM config service: write proxy config to openclaw.json via kubectl exec."""

import asyncio
import json
import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.llm_proxy import PROVIDER_DEFAULTS
from app.core.config import settings
from app.models.base import not_deleted
from app.models.cluster import Cluster
from app.models.instance import Instance
from app.models.user_llm_config import UserLlmConfig
from app.services.k8s.client_manager import k8s_manager
from app.services.k8s.k8s_client import K8sClient

logger = logging.getLogger(__name__)

OPENCLAW_CONFIG_PATH = "/root/.openclaw/openclaw.json"


def _k8s_name(instance: Instance) -> str:
    return instance.slug or instance.name


def _build_providers_config(configs: list[UserLlmConfig], proxy_token: str) -> dict:
    """Build the models.providers section for openclaw.json."""
    host = settings.CLAWBUDDY_HOST.rstrip("/") if settings.CLAWBUDDY_HOST else ""
    providers: dict = {}
    for cfg in configs:
        provider = cfg.provider
        if host:
            base_url = f"{host}/llm-proxy/{provider}/v1"
        else:
            base_url = f"http://localhost:8000/llm-proxy/{provider}/v1"
        providers[provider] = {
            "baseUrl": base_url,
            "apiKey": proxy_token,
        }
    return providers


async def _get_running_pod(k8s: K8sClient, instance: Instance) -> str | None:
    label_selector = f"app.kubernetes.io/name={_k8s_name(instance)}"
    pods = await k8s.list_pods(instance.namespace, label_selector)
    running = [p for p in pods if p["phase"] == "Running"]
    return running[0]["name"] if running else None


async def sync_openclaw_llm_config(instance: Instance, db: AsyncSession) -> None:
    """Write proxy LLM config to openclaw.json and restart OpenClaw."""
    configs_result = await db.execute(
        select(UserLlmConfig).where(
            UserLlmConfig.user_id == instance.created_by,
            UserLlmConfig.org_id == instance.org_id,
            not_deleted(UserLlmConfig),
        )
    )
    configs = configs_result.scalars().all()

    if not configs:
        logger.info("实例 %s 无 LLM 配置，跳过写入", instance.name)
        return

    proxy_token = instance.proxy_token
    if not proxy_token:
        logger.warning("实例 %s 缺少 proxy_token，无法写入 LLM 配置", instance.name)
        return

    providers = _build_providers_config(configs, proxy_token)

    cluster_result = await db.execute(
        select(Cluster).where(Cluster.id == instance.cluster_id)
    )
    cluster = cluster_result.scalar_one_or_none()
    if not cluster or not cluster.kubeconfig_encrypted:
        logger.error("实例 %s 的集群不可用", instance.name)
        return

    api_client = await k8s_manager.get_or_create(cluster.id, cluster.kubeconfig_encrypted)
    k8s = K8sClient(api_client)

    pod_name = await _get_running_pod(k8s, instance)
    if not pod_name:
        logger.warning("实例 %s 无运行中 Pod，无法写入配置", instance.name)
        return

    existing_json = {}
    try:
        raw = await k8s.exec_in_pod(
            instance.namespace, pod_name,
            ["cat", OPENCLAW_CONFIG_PATH],
        )
        if raw:
            existing_json = json.loads(raw)
    except Exception:
        logger.info("读取已有 openclaw.json 失败（可能不存在），将创建新文件")

    if "models" not in existing_json:
        existing_json["models"] = {}
    existing_json["models"]["providers"] = providers

    config_str = json.dumps(existing_json, indent=2, ensure_ascii=False)
    escaped = config_str.replace("'", "'\\''")
    await k8s.exec_in_pod(
        instance.namespace, pod_name,
        ["sh", "-c", f"mkdir -p /root/.openclaw && echo '{escaped}' > {OPENCLAW_CONFIG_PATH}"],
    )
    logger.info("已写入 openclaw.json LLM 配置: instance=%s providers=%s", instance.name, list(providers.keys()))


async def restart_openclaw(instance: Instance, db: AsyncSession) -> dict:
    """Update openclaw.json and gracefully restart OpenClaw (SIGTERM PID 1)."""
    await sync_openclaw_llm_config(instance, db)

    cluster_result = await db.execute(
        select(Cluster).where(Cluster.id == instance.cluster_id)
    )
    cluster = cluster_result.scalar_one_or_none()
    if not cluster or not cluster.kubeconfig_encrypted:
        return {"status": "error", "message": "集群不可用"}

    api_client = await k8s_manager.get_or_create(cluster.id, cluster.kubeconfig_encrypted)
    k8s = K8sClient(api_client)

    pod_name = await _get_running_pod(k8s, instance)
    if not pod_name:
        return {"status": "error", "message": "无运行中的 Pod"}

    await k8s.exec_in_pod(
        instance.namespace, pod_name,
        ["kill", "-SIGTERM", "1"],
    )
    logger.info("已发送 SIGTERM 到实例 %s 的 PID 1", instance.name)

    for _ in range(30):
        await asyncio.sleep(2)
        pods = await k8s.list_pods(
            instance.namespace,
            f"app.kubernetes.io/name={_k8s_name(instance)}",
        )
        running = [p for p in pods if p["phase"] == "Running"]
        if running:
            for p in running:
                ready = all(c.get("ready", False) for c in p.get("containers", []))
                if ready:
                    logger.info("实例 %s OpenClaw 重启完成", instance.name)
                    return {"status": "ok", "message": "重启完成"}

    return {"status": "timeout", "message": "重启超时（60s），请检查实例状态"}
