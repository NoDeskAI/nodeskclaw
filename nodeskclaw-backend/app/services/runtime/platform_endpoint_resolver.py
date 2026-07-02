"""Resolve platform endpoints from the runtime network point of view."""

from __future__ import annotations

import ipaddress
from dataclasses import dataclass
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit


LOCAL_HOSTS = {"localhost", "127.0.0.1", "0.0.0.0", "::1"}


class PlatformEndpointConfigError(ValueError):
    pass


@dataclass(frozen=True)
class PlatformEndpoints:
    llm_proxy_base_url: str
    agent_api_base_url: str
    tunnel_base_url: str | None = None


def resolve_platform_endpoints(
    *,
    compute_provider: str,
    runtime: str,
    instance_namespace: str | None,
    cluster_proxy_endpoint: str | None,
    platform_namespace: str,
    settings: Any,
) -> PlatformEndpoints:
    compute = (compute_provider or "").strip().lower()
    remote_k8s = compute == "k8s" and bool((cluster_proxy_endpoint or "").strip())

    llm_proxy_url = _resolve_llm_proxy_base_url(
        compute_provider=compute,
        cluster_proxy_endpoint=cluster_proxy_endpoint,
        platform_namespace=platform_namespace,
        external_url=getattr(settings, "LLM_PROXY_URL", ""),
        internal_url=getattr(settings, "LLM_PROXY_INTERNAL_URL", ""),
    )
    agent_api_url = resolve_runtime_url(
        getattr(settings, "AGENT_API_BASE_URL", ""),
        compute_provider=compute,
        platform_namespace=platform_namespace,
        remote_k8s=remote_k8s,
        label="AGENT_API_BASE_URL",
    )
    tunnel_url = resolve_runtime_url(
        getattr(settings, "TUNNEL_BASE_URL", ""),
        compute_provider=compute,
        platform_namespace=platform_namespace,
        remote_k8s=remote_k8s,
        label="TUNNEL_BASE_URL",
        optional=True,
    )

    return PlatformEndpoints(
        llm_proxy_base_url=llm_proxy_url,
        agent_api_base_url=agent_api_url,
        tunnel_base_url=tunnel_url,
    )


def resolve_runtime_url(
    url: str | None,
    *,
    compute_provider: str,
    platform_namespace: str,
    remote_k8s: bool = False,
    label: str = "URL",
    optional: bool = False,
) -> str | None:
    normalized = (url or "").strip().rstrip("/")
    if not normalized:
        if optional:
            return None
        raise PlatformEndpointConfigError(f"{label} 未配置，无法生成运行时可达地址")

    compute = (compute_provider or "").strip().lower()
    if compute == "k8s":
        return _resolve_k8s_url(
            normalized,
            platform_namespace=platform_namespace,
            remote_k8s=remote_k8s,
            label=label,
        )
    return normalized


def _resolve_llm_proxy_base_url(
    *,
    compute_provider: str,
    cluster_proxy_endpoint: str | None,
    platform_namespace: str,
    external_url: str | None,
    internal_url: str | None,
) -> str:
    remote_k8s = compute_provider == "k8s" and bool((cluster_proxy_endpoint or "").strip())
    if remote_k8s:
        source = (external_url or "").strip()
        if not source:
            raise PlatformEndpointConfigError(
                "远端 K8s 实例需要配置 LLM_PROXY_URL，不能下发平台集群内部 Service 地址"
            )
        return resolve_runtime_url(
            source,
            compute_provider=compute_provider,
            platform_namespace=platform_namespace,
            remote_k8s=True,
            label="LLM_PROXY_URL",
        ) or ""

    if compute_provider == "process":
        source = (external_url or internal_url or "").strip()
    else:
        source = (internal_url or external_url or "").strip()

    if not source:
        raise PlatformEndpointConfigError("LLM Proxy 地址未配置，请设置 LLM_PROXY_INTERNAL_URL 或 LLM_PROXY_URL")

    return resolve_runtime_url(
        source,
        compute_provider=compute_provider,
        platform_namespace=platform_namespace,
        remote_k8s=False,
        label="LLM Proxy 地址",
    ) or ""


def _resolve_k8s_url(
    url: str,
    *,
    platform_namespace: str,
    remote_k8s: bool,
    label: str,
) -> str:
    parsed = urlsplit(url)
    if not parsed.scheme or not parsed.netloc:
        return url

    host = parsed.hostname
    if _is_local_host(host):
        raise PlatformEndpointConfigError(f"{label} 当前为 localhost，K8s 实例无法访问")
    if not host or _is_ip_address(host) or "." in host:
        return url
    if remote_k8s:
        raise PlatformEndpointConfigError(f"{label} 当前为单标签 Service 名，远端 K8s 实例无法解析")
    if not platform_namespace:
        raise PlatformEndpointConfigError(f"{label} 使用 Service 短名时必须配置 PLATFORM_NAMESPACE")
    return _replace_hostname(parsed, f"{host}.{platform_namespace}.svc.cluster.local")


def _replace_hostname(parsed: SplitResult, hostname: str) -> str:
    port = f":{parsed.port}" if parsed.port else ""
    return urlunsplit((parsed.scheme, f"{hostname}{port}", parsed.path, parsed.query, parsed.fragment))


def _is_local_host(hostname: str | None) -> bool:
    return (hostname or "").strip().lower() in LOCAL_HOSTS


def _is_ip_address(hostname: str | None) -> bool:
    if not hostname:
        return False
    try:
        ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return True
