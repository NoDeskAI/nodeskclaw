"""ResourceBuilder: construct K8s resource manifests for OpenClaw instances."""

import base64
import json

from kubernetes_asyncio.client import (
    V1ConfigMap,
    V1ConfigMapVolumeSource,
    V1Container,
    V1ContainerPort,
    V1Deployment,
    V1DeploymentSpec,
    V1DeploymentStrategy,
    V1EmptyDirVolumeSource,
    V1EnvVar,
    V1EnvVarSource,
    V1ConfigMapKeySelector,
    V1HTTPGetAction,
    V1HTTPIngressPath,
    V1HTTPIngressRuleValue,
    V1Ingress,
    V1IngressBackend,
    V1IngressRule,
    V1IngressSpec,
    V1IngressServiceBackend,
    V1IngressTLS,
    V1KeyToPath,
    V1LabelSelector,
    V1LocalObjectReference,
    V1ObjectMeta,
    V1PersistentVolumeClaim,
    V1PersistentVolumeClaimSpec,
    V1PodSpec,
    V1PodTemplateSpec,
    V1Probe,
    V1ResourceQuota,
    V1ResourceQuotaSpec,
    V1ResourceRequirements,
    V1Secret,
    V1SecretVolumeSource,
    V1Service,
    V1ServiceBackendPort,
    V1ServicePort,
    V1ServiceSpec,
    V1Volume,
    V1VolumeMount,
)

from app.services.k8s.client_manager import GATEWAY_NS

MANAGED_BY = "nodeskclaw"

# 系统保留标签前缀 -- 用户自定义标签不可覆盖
_RESERVED_LABEL_PREFIXES = ("app.kubernetes.io/", "nodeskclaw/")


def build_labels(instance_name: str, instance_id: str, image_tag: str = "") -> dict:
    labels = {
        "app.kubernetes.io/name": instance_name,
        "app.kubernetes.io/managed-by": MANAGED_BY,
        "nodeskclaw/instance-id": instance_id,
    }
    if image_tag:
        labels["nodeskclaw/image-tag"] = image_tag
    return labels


REGISTRY_SECRET_NAME = "nodeskclaw-registry"


def build_registry_secret(
    namespace: str,
    registry_url: str,
    username: str,
    password: str,
) -> V1Secret:
    """构建 Docker Registry 认证 Secret（kubernetes.io/dockerconfigjson 类型）。

    用于 imagePullSecrets，让 K8s 能从私有镜像仓库拉取镜像。
    """
    # 从完整镜像地址中提取 registry 主机（如 cr-xxx.<CLOUD_VENDOR_DOMAIN>）
    # 注意：不加 https:// 前缀，containerd 按纯域名匹配 imagePullSecrets
    server = registry_url.split("/")[0] if "/" in registry_url else registry_url

    docker_config = {
        "auths": {
            server: {
                "username": username,
                "password": password,
                "auth": base64.b64encode(f"{username}:{password}".encode()).decode(),
            }
        }
    }

    return V1Secret(
        metadata=V1ObjectMeta(name=REGISTRY_SECRET_NAME, namespace=namespace),
        type="kubernetes.io/dockerconfigjson",
        data={
            ".dockerconfigjson": base64.b64encode(
                json.dumps(docker_config).encode()
            ).decode(),
        },
    )


def _merge_custom_labels(base_labels: dict, custom_labels: dict | None) -> dict:
    """Merge user-provided labels into base labels; reserved prefixes are rejected."""
    if not custom_labels:
        return base_labels
    merged = dict(base_labels)
    for k, v in custom_labels.items():
        if any(k.startswith(prefix) for prefix in _RESERVED_LABEL_PREFIXES):
            continue  # skip reserved
        merged[k] = v
    return merged


def build_configmap(
    name: str, namespace: str, env_vars: dict[str, str], labels: dict
) -> V1ConfigMap:
    return V1ConfigMap(
        metadata=V1ObjectMeta(name=name, namespace=namespace, labels=labels),
        data=env_vars,
    )


def build_pvc(
    name: str,
    namespace: str,
    storage_size: str,
    storage_class: str | None,
    labels: dict,
    access_modes: list[str] | None = None,
) -> V1PersistentVolumeClaim:
    return V1PersistentVolumeClaim(
        metadata=V1ObjectMeta(name=name, namespace=namespace, labels=labels),
        spec=V1PersistentVolumeClaimSpec(
            access_modes=access_modes or ["ReadWriteOnce"],
            resources=V1ResourceRequirements(requests={"storage": storage_size}),
            storage_class_name=storage_class,
        ),
    )


def build_resource_quota(
    name: str,
    namespace: str,
    cpu: str,
    mem: str,
    max_pods: int = 20,
    storage: str | None = None,
) -> V1ResourceQuota:
    """Build a Namespace-level ResourceQuota."""
    hard = {
        "requests.cpu": cpu,
        "requests.memory": mem,
        "limits.cpu": cpu,
        "limits.memory": mem,
        "pods": str(max_pods),
    }
    if storage:
        hard["requests.storage"] = storage
    return V1ResourceQuota(
        metadata=V1ObjectMeta(name=name, namespace=namespace),
        spec=V1ResourceQuotaSpec(hard=hard),
    )


def _build_volume_from_config(vol: dict) -> tuple[V1Volume | None, V1VolumeMount | None]:
    """Build V1Volume + V1VolumeMount from an advanced-config volume entry."""
    vol_name = vol.get("name", "")
    mount_path = vol.get("mount_path", "")
    vol_type = vol.get("volume_type", "pvc")

    if not vol_name or not mount_path:
        return None, None

    volume: V1Volume | None = None

    if vol_type == "pvc":
        pvc_claim = vol.get("pvc", "")
        if not pvc_claim:
            return None, None
        volume = V1Volume(name=vol_name, persistent_volume_claim={"claimName": pvc_claim})

    elif vol_type == "emptyDir":
        volume = V1Volume(name=vol_name, empty_dir=V1EmptyDirVolumeSource())

    elif vol_type == "configMap":
        cm_name = vol.get("config_map_name", "")
        if not cm_name:
            return None, None
        items_raw = vol.get("items")
        items = None
        if items_raw:
            items = [V1KeyToPath(key=it.get("key", ""), path=it.get("path", "")) for it in items_raw if it.get("key")]
        volume = V1Volume(
            name=vol_name,
            config_map=V1ConfigMapVolumeSource(name=cm_name, items=items),
        )

    elif vol_type == "secret":
        secret_name = vol.get("secret_name", "")
        if not secret_name:
            return None, None
        items_raw = vol.get("items")
        items = None
        if items_raw:
            items = [V1KeyToPath(key=it.get("key", ""), path=it.get("path", "")) for it in items_raw if it.get("key")]
        volume = V1Volume(
            name=vol_name,
            secret=V1SecretVolumeSource(secret_name=secret_name, items=items),
        )

    if volume is None:
        return None, None

    mount = V1VolumeMount(
        name=vol_name,
        mount_path=mount_path,
        sub_path=vol.get("sub_path"),
        read_only=vol.get("read_only", False),
    )
    return volume, mount


def build_deployment(
    name: str,
    namespace: str,
    image: str,
    replicas: int,
    labels: dict,
    configmap_name: str | None = None,
    pvc_name: str | None = None,
    cpu_request: str = "500m",
    cpu_limit: str = "2",
    mem_request: str = "2Gi",
    mem_limit: str = "2Gi",
    port: int = 18789,
    env_vars: dict[str, str] | None = None,
    advanced_config: dict | None = None,
    image_pull_secret: str | None = None,
    health_probe_path: str | None = "/healthz",
    readiness_probe_path: str | None = "/healthz",
    has_init_script: bool = True,
) -> V1Deployment:
    """Build Deployment manifest with optional advanced config."""

    # Environment variables from ConfigMap
    env = []
    if configmap_name and env_vars:
        for key in env_vars:
            env.append(
                V1EnvVar(
                    name=key,
                    value_from=V1EnvVarSource(
                        config_map_key_ref=V1ConfigMapKeySelector(name=configmap_name, key=key)
                    ),
                )
            )

    volumes = []
    volume_mounts = []

    # PVC for /root persistence
    if pvc_name:
        volumes.append(V1Volume(name="root-data", persistent_volume_claim={"claimName": pvc_name}))
        volume_mounts.append(V1VolumeMount(name="root-data", mount_path="/root"))

    # Init container for first-time setup
    # 注意：当命名空间有 ResourceQuota（设置了 limits）时，所有容器必须指定 resource limits
    init_containers = []
    if pvc_name and has_init_script:
        init_containers.append(
            V1Container(
                name="init-root-data",
                image=image,
                command=["/init-container.sh"],
                volume_mounts=[V1VolumeMount(name="root-data", mount_path="/init-data")],
                resources=V1ResourceRequirements(
                    requests={"cpu": "50m", "memory": "64Mi"},
                    limits={"cpu": "200m", "memory": "256Mi"},
                ),
            )
        )

    # ── Advanced config: extra volumes (multi-type) ──
    custom_labels: dict[str, str] = {}
    custom_annotations: dict[str, str] = {}

    if advanced_config:
        for vol in advanced_config.get("volumes", []):
            v, m = _build_volume_from_config(vol)
            if v and m:
                volumes.append(v)
                volume_mounts.append(m)

        # Custom labels / annotations
        custom_labels = advanced_config.get("custom_labels") or {}
        custom_annotations = advanced_config.get("custom_annotations") or {}

    # ── Advanced config: init containers ──
    if advanced_config:
        for ic in advanced_config.get("init_containers", []):
            ic_env = [V1EnvVar(name=k, value=v) for k, v in ic.get("env_vars", {}).items()]
            init_containers.append(
                V1Container(
                    name=ic["name"],
                    image=ic["image"],
                    command=ic.get("command") or None,
                    args=ic.get("args") or None,
                    env=ic_env or None,
                )
            )

    if health_probe_path is not None:
        liveness_get = V1HTTPGetAction(path=health_probe_path, port=port)
        readiness_get = V1HTTPGetAction(path=readiness_probe_path or health_probe_path, port=port)
        startup_probe = V1Probe(
            http_get=liveness_get,
            initial_delay_seconds=5,
            period_seconds=3,
            failure_threshold=20,
            timeout_seconds=2,
        )
        readiness_probe = V1Probe(
            http_get=readiness_get,
            period_seconds=5,
            failure_threshold=3,
            success_threshold=1,
            timeout_seconds=2,
        )
        liveness_probe = V1Probe(
            http_get=liveness_get,
            period_seconds=15,
            failure_threshold=3,
            timeout_seconds=3,
        )
    else:
        startup_probe = None
        readiness_probe = None
        liveness_probe = None

    container = V1Container(
        name=name,
        image=image,
        ports=[
            V1ContainerPort(container_port=port),
            V1ContainerPort(container_port=9721, name="sse"),
        ],
        env=env or None,
        resources=V1ResourceRequirements(
            requests={"cpu": cpu_request, "memory": mem_request},
            limits={"cpu": cpu_limit, "memory": mem_limit},
        ),
        volume_mounts=volume_mounts or None,
        startup_probe=startup_probe,
        readiness_probe=readiness_probe,
        liveness_probe=liveness_probe,
    )

    # ── Advanced config: sidecar containers ──
    all_containers = [container]
    if advanced_config:
        for sc in advanced_config.get("sidecars", []):
            sc_env = [V1EnvVar(name=k, value=v) for k, v in sc.get("env_vars", {}).items()]
            sc_ports = [V1ContainerPort(container_port=p) for p in sc.get("ports", [])]
            all_containers.append(
                V1Container(
                    name=sc["name"],
                    image=sc["image"],
                    command=sc.get("command") or None,
                    args=sc.get("args") or None,
                    env=sc_env or None,
                    ports=sc_ports or None,
                    resources=V1ResourceRequirements(
                        requests={
                            "cpu": sc.get("cpu_request", "100m"),
                            "memory": sc.get("mem_request", "128Mi"),
                        },
                        limits={
                            "cpu": sc.get("cpu_limit", "500m"),
                            "memory": sc.get("mem_limit", "512Mi"),
                        },
                    ),
                )
            )

    # Merge custom labels/annotations into pod template
    pod_labels = _merge_custom_labels(labels, custom_labels)
    pod_annotations: dict[str, str] | None = custom_annotations if custom_annotations else None

    # 镜像拉取凭据
    pull_secrets = [V1LocalObjectReference(name=image_pull_secret)] if image_pull_secret else None

    return V1Deployment(
        metadata=V1ObjectMeta(name=name, namespace=namespace, labels=labels),
        spec=V1DeploymentSpec(
            replicas=replicas,
            strategy=V1DeploymentStrategy(type="Recreate"),
            selector=V1LabelSelector(match_labels={"app.kubernetes.io/name": labels["app.kubernetes.io/name"]}),
            template=V1PodTemplateSpec(
                metadata=V1ObjectMeta(labels=pod_labels, annotations=pod_annotations),
                spec=V1PodSpec(
                    hostname=name,
                    automount_service_account_token=False,
                    init_containers=init_containers or None,
                    containers=all_containers,
                    volumes=volumes or None,
                    image_pull_secrets=pull_secrets,
                ),
            ),
        ),
    )


def _build_egress_rules(
    peer_namespaces: list[str],
    deny_cidrs: list[str],
    allow_ports: list[int],
    platform_namespace: str = "nodeskclaw-system",
    platform_host_endpoints: list[tuple[str, int]] | None = None,
) -> list[dict]:
    """构建 Egress 规则列表（允许列表模式，未匹配流量默认拒绝）。

    platform_host_endpoints: 宿主机平台服务地址列表 [(ip, port), ...]，
    当后端/LLM Proxy 不在 K8s 集群内时，需要通过 ipBlock 显式放行。
    """
    rules: list[dict] = []

    rules.append({
        "to": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": "kube-system"}}}],
        "ports": [
            {"protocol": "UDP", "port": 53},
            {"protocol": "TCP", "port": 53},
        ],
    })

    rules.append({
        "to": [{"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": platform_namespace}}}],
    })

    rules.append({
        "to": [{"podSelector": {}}],
    })

    for ns in peer_namespaces:
        rules.append({
            "to": [{
                "namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": ns}},
                "podSelector": {"matchLabels": {"app.kubernetes.io/managed-by": MANAGED_BY}},
            }],
        })

    if platform_host_endpoints:
        seen: dict[str, list[int]] = {}
        for ip, port in platform_host_endpoints:
            seen.setdefault(ip, []).append(port)
        for ip, ports_list in seen.items():
            rules.append({
                "to": [{"ipBlock": {"cidr": f"{ip}/32"}}],
                "ports": [{"protocol": "TCP", "port": p} for p in sorted(set(ports_list))],
            })

    ip_block: dict = {"cidr": "0.0.0.0/0"}
    if deny_cidrs:
        ip_block["except"] = deny_cidrs
    ports = [{"protocol": "TCP", "port": p} for p in allow_ports]
    rules.append({
        "to": [{"ipBlock": ip_block}],
        "ports": ports,
    })

    return rules


def build_network_policy(
    name: str,
    namespace: str,
    labels: dict,
    peer_namespaces: list[str],
    org_id: str | None = None,
    egress_deny_cidrs: list[str] | None = None,
    egress_allow_ports: list[int] | None = None,
    platform_namespace: str = "nodeskclaw-system",
    ingress_enabled: bool = True,
    egress_enabled: bool = True,
    ingress_allow_cidrs: list[str] | None = None,
    platform_host_endpoints: list[tuple[str, int]] | None = None,
) -> dict:
    """Build NetworkPolicy for multi-tenant isolation + egress restriction.

    ingress_enabled / egress_enabled 控制 policyTypes 中包含哪些方向。
    两个都为 False 时不应调用此函数（调用方负责跳过）。
    """
    policy_labels = dict(labels)
    if org_id:
        policy_labels["nodeskclaw.io/org-id"] = org_id

    policy_types: list[str] = []
    spec: dict = {"podSelector": {}}

    if ingress_enabled:
        policy_types.append("Ingress")
        ingress_from: list[dict] = [
            {"podSelector": {}},
            {"namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": platform_namespace}}},
        ]
        for ns in peer_namespaces:
            ingress_from.append({
                "namespaceSelector": {"matchLabels": {"kubernetes.io/metadata.name": ns}},
                "podSelector": {"matchLabels": {"app.kubernetes.io/managed-by": MANAGED_BY}},
            })
        for cidr in (ingress_allow_cidrs or []):
            if cidr.strip():
                ingress_from.append({"ipBlock": {"cidr": cidr.strip()}})
        spec["ingress"] = [{"from": ingress_from}]

    if egress_enabled:
        policy_types.append("Egress")
        spec["egress"] = _build_egress_rules(
            peer_namespaces=peer_namespaces,
            deny_cidrs=egress_deny_cidrs or [],
            allow_ports=egress_allow_ports or [80, 443],
            platform_namespace=platform_namespace,
            platform_host_endpoints=platform_host_endpoints,
        )

    spec["policyTypes"] = policy_types

    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {"name": name, "namespace": namespace, "labels": policy_labels},
        "spec": spec,
    }


def build_service(
    name: str,
    namespace: str,
    labels: dict,
    port: int = 18789,
) -> V1Service:
    """构建 ClusterIP Service，端口默认 18789（OpenClaw Gateway）+ 9721（SSE）。"""
    return V1Service(
        metadata=V1ObjectMeta(name=name, namespace=namespace, labels=labels),
        spec=V1ServiceSpec(
            selector={"app.kubernetes.io/name": labels["app.kubernetes.io/name"]},
            ports=[
                V1ServicePort(port=port, target_port=port, protocol="TCP", name="gateway"),
                V1ServicePort(port=9721, target_port=9721, protocol="TCP", name="sse"),
            ],
            type="ClusterIP",
        ),
    )


def build_ingress(
    name: str,
    namespace: str,
    host: str,
    labels: dict,
    service_name: str | None = None,
    port: int = 18789,
    tls_secret_name: str | None = None,
    ingress_class: str = "nginx",
) -> V1Ingress:
    """构建 Ingress 资源，支持子域名路由 + TLS + WebSocket。

    根据 ``ingress_class`` 动态生成 annotations 和 TLS 配置：

    - **nginx**: nginx-ingress 专属注解 + K8s Secret TLS
    - **alb** 等其他类型: 不加控制器专属注解，TLS 由云厂商控制台管理
    """
    svc_name = service_name or name

    annotations: dict[str, str] = {}
    tls: list[V1IngressTLS] | None = None

    if ingress_class == "nginx":
        annotations = {
            "nginx.ingress.kubernetes.io/proxy-read-timeout": "86400",
            "nginx.ingress.kubernetes.io/proxy-send-timeout": "3600",
            "nginx.ingress.kubernetes.io/proxy-http-version": "1.1",
            "nginx.ingress.kubernetes.io/proxy-buffering": "off",
        }
        if tls_secret_name:
            tls = [V1IngressTLS(hosts=[host], secret_name=tls_secret_name)]
            annotations["nginx.ingress.kubernetes.io/ssl-redirect"] = "true"

    return V1Ingress(
        metadata=V1ObjectMeta(
            name=name,
            namespace=namespace,
            labels=labels,
            annotations=annotations or None,
        ),
        spec=V1IngressSpec(
            ingress_class_name=ingress_class,
            tls=tls,
            rules=[
                V1IngressRule(
                    host=host,
                    http=V1HTTPIngressRuleValue(
                        paths=[
                            V1HTTPIngressPath(
                                path="/sse/",
                                path_type="Prefix",
                                backend=V1IngressBackend(
                                    service=V1IngressServiceBackend(
                                        name=svc_name,
                                        port=V1ServiceBackendPort(number=9721),
                                    )
                                ),
                            ),
                            V1HTTPIngressPath(
                                path="/",
                                path_type="Prefix",
                                backend=V1IngressBackend(
                                    service=V1IngressServiceBackend(
                                        name=svc_name,
                                        port=V1ServiceBackendPort(number=port),
                                    )
                                ),
                            ),
                        ]
                    ),
                )
            ],
        ),
    )


def build_external_name_service(
    cluster_id: str,
    external_name: str,
    api_server_url: str | None = None,
) -> V1Service:
    """构建 ExternalName Service，用于 infra 网关代理到 inst 集群 ALB。

    每个物理 inst 集群对应一个 ExternalName Service，部署在 infra 的 GATEWAY_NS。
    当提供 api_server_url 时，会添加 api-server-hash label 用于物理集群去重。
    """
    labels: dict[str, str] = {
        "app.kubernetes.io/managed-by": MANAGED_BY,
        "nodeskclaw/proxy-type": "inst-cluster",
        "nodeskclaw/cluster-id": cluster_id,
    }
    if api_server_url:
        from app.services.k8s.proxy_helpers import compute_api_server_hash
        labels["nodeskclaw/api-server-hash"] = compute_api_server_hash(api_server_url)
    return V1Service(
        metadata=V1ObjectMeta(
            name=f"proxy-inst-{cluster_id[:8]}",
            namespace=GATEWAY_NS,
            labels=labels,
        ),
        spec=V1ServiceSpec(
            type="ExternalName",
            external_name=external_name,
        ),
    )


def build_proxy_ingress(
    instance_name: str,
    host: str,
    proxy_service_name: str,
) -> V1Ingress:
    """构建代理 Ingress，部署在 infra 网关集群，将实例流量转发到 inst 集群。

    infra nginx 收到实例子域名请求后，通过 ExternalName Service 转发到
    对应 inst 集群的 ALB，再由 inst nginx 路由到实际 Pod。
    """
    return V1Ingress(
        metadata=V1ObjectMeta(
            name=f"proxy-{instance_name}",
            namespace=GATEWAY_NS,
            labels={
                "app.kubernetes.io/managed-by": MANAGED_BY,
                "nodeskclaw/proxy-type": "instance",
                "nodeskclaw/instance-name": instance_name,
            },
            annotations={
                "nginx.ingress.kubernetes.io/proxy-read-timeout": "86400",
                "nginx.ingress.kubernetes.io/proxy-send-timeout": "3600",
                "nginx.ingress.kubernetes.io/proxy-http-version": "1.1",
                "nginx.ingress.kubernetes.io/proxy-buffering": "off",
            },
        ),
        spec=V1IngressSpec(
            ingress_class_name="nginx",
            rules=[
                V1IngressRule(
                    host=host,
                    http=V1HTTPIngressRuleValue(
                        paths=[
                            V1HTTPIngressPath(
                                path="/",
                                path_type="Prefix",
                                backend=V1IngressBackend(
                                    service=V1IngressServiceBackend(
                                        name=proxy_service_name,
                                        port=V1ServiceBackendPort(number=80),
                                    )
                                ),
                            ),
                        ]
                    ),
                )
            ],
        ),
    )
