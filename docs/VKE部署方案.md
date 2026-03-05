# NoDeskClaw - 火山云 VKE 部署方案

> 解决核心问题：NoDeskClaw 怎么往火山云 VKE 集群里创建 OpenClaw 的 K8s 资源

---

## 一、部署到 K8s 的两件事

NoDeskClaw 要部署两类东西到 VKE：

```
火山云 VKE 集群
│
├── 1. NoDeskClaw 自身（一次性人工部署）
│     Deployment + Service + Ingress
│     管理后台，部署一次就行
│
└── 2. OpenClaw 实例（通过 NoDeskClaw 页面一键部署，可以 N 个）
      每个实例 = Deployment + Service + ConfigMap + (可选)Ingress
      这是核心功能，通过 kubernetes-asyncio 直接创建 K8s 资源
```

---

## 二、VKE 集群接入

### 2.1 获取 KubeConfig

从火山云控制台获取：

```
火山引擎控制台 → 容器服务 → 集群管理 → 选择集群 → 连接信息 → 下载 KubeConfig
```

VKE 提供两种 KubeConfig：

| 类型 | 网络要求 | 适用场景 |
|------|----------|----------|
| **公网 KubeConfig** | 通过公网访问 API Server | NoDeskClaw 部署在 VKE 集群外部 |
| **内网 KubeConfig** | 通过 VPC 内网访问 | NoDeskClaw 部署在同一 VKE 集群或同 VPC |

**推荐**：NoDeskClaw 自身部署在 VKE 集群内，用 **ServiceAccount + RBAC** 访问本集群，不需要 KubeConfig 文件。管理其他集群时才需要导入 KubeConfig。

### 2.2 NoDeskClaw 内访问本集群

NoDeskClaw 跑在 VKE 里时，用 Pod 自带的 ServiceAccount Token 就行：

```python
# kubernetes-asyncio 支持自动检测 in-cluster 环境
from kubernetes_asyncio import config

# 方式 1: Pod 内自动加载 ServiceAccount Token
await config.load_incluster_config()

# 方式 2: 外部开发环境，加载本地 kubeconfig
await config.load_kube_config()
```

需要给 NoDeskClaw 的 ServiceAccount 足够权限（见第六节 RBAC）。

### 2.3 NoDeskClaw 内访问其他集群

用户通过页面上传 KubeConfig → AES 加密存入 DB → 使用时解密内存加载：

```
用户上传 KubeConfig (公网类型)
       │
       ▼
K8sClientManager.get_or_create(cluster_id, kubeconfig_enc)
       │
       ├─ 解密 → 解析认证方式 + Token 过期时间
       ├─ Token 过期检测（已过期则拒绝 + 告警）
       ├─ 内存加载 → ApiClient
       ├─ 健康检查 (GET /version)
       └─ 缓存，下次直接用
```

### 2.4 VKE KubeConfig 认证方式与 Token 过期

VKE 的 KubeConfig 支持两种认证方式：

| 认证方式 | 有效期 | VKE 控制台选项 | 推荐 |
|----------|--------|---------------|------|
| **客户端证书** (client-certificate) | 通常 1 年 | 下载时选择「证书认证」 | ✅ 推荐 |
| **Token** (bearer token) | **48 小时** | 下载时选择「Token 认证」 | ⚠️ 短期有效 |

**Token 过期处理**：
- NoDeskClaw 后台 `ClusterHealthChecker` 每 60 秒巡检所有集群
- Token 不足 6 小时 → 后端标记 `health_status=token_expiring`，前端轮询 `GET /clusters/:id/health` 展示黄色告警
- Token 已过期 → 后端标记 `health_status=token_expired`，阻止所有操作，前端轮询时展示红色告警，用户需重新上传 KubeConfig
- 用户上传新 KubeConfig 后，`K8sClientManager` 自动重建连接

### 2.5 VKE StorageClass

VKE 集群预置的存储类（用于高级配置中的 PVC）：

| StorageClass | 说明 | 适用场景 |
|-------------|------|----------|
| `ebs-ssd` | 火山云 SSD 云盘 | 数据库、高 IO 场景 |
| `ebs-ssd-pl0` | SSD 性能级别 PL0 | 通用存储 |
| `ebs-flexpl` | 弹性 ESSD | 性价比场景 |
| `nas` | 文件存储 NAS (ReadWriteMany) | 多 Pod 共享存储 |

AdvancedConfig 中 `VolumeConfig.storage_class` 可指定上述值。不指定则使用集群默认 StorageClass。

---

## 三、实例隔离策略

### 3.1 核心原则：每实例独占一个 Namespace

不同 OpenClaw 实例之间通过 **Namespace 隔离 + ResourceQuota + NetworkPolicy** 三层机制实现隔离：

```
火山云 VKE 集群
│
├── Namespace: nodeskclaw              ← NoDeskClaw 自身
│
├── Namespace: oc-prod-main           ← OpenClaw 生产主力
│   ├── ResourceQuota (4c / 8Gi)
│   ├── LimitRange (单容器上限 2c/4Gi)
│   ├── NetworkPolicy (仅允许同 NS + NoDeskClaw + Ingress)
│   └── 业务资源: ConfigMap + Deployment + Service + Ingress
│
├── Namespace: oc-staging             ← OpenClaw 预发
│   ├── ResourceQuota (2c / 4Gi)
│   ├── LimitRange
│   ├── NetworkPolicy
│   └── 业务资源 ...
│
├── Namespace: oc-dev-zhangsan        ← 开发实例
│   ├── ResourceQuota (1c / 2Gi)
│   └── ...
│
└── Namespace: oc-test-pr-123         ← PR 测试实例
    ├── ResourceQuota (1c / 2Gi)
    └── ...
```

隔离效果：

| 隔离维度 | 机制 | 效果 |
|---------|------|------|
| 资源名不冲突 | Namespace | 每个 NS 内资源名独立 |
| 资源配额上限 | ResourceQuota | 单实例最多用 N 核 / N GB，不会吃光集群 |
| 容器默认限制 | LimitRange | 兜底，没设 limits 的容器也有上限 |
| 网络隔离 | NetworkPolicy | 不同实例的 Pod 互不可访问 |
| 存储隔离 | PVC namespace-scoped | 天然隔离 |
| 权限边界 | RBAC namespace-scoped | 普通用户只能操作自己的 NS |

### 3.2 Namespace 命名规范

```
格式: oc-{实例名}

示例:
  oc-prod-main         生产主力
  oc-staging           预发环境
  oc-dev-zhangsan      张三的开发实例
  oc-test-pr-123       PR 自动测试
```

> 用户在部署表单里只填 **实例名**（如 `prod-main`），Namespace 由 NoDeskClaw 自动生成 `oc-prod-main`。

### 3.3 ResourceQuota（防止资源抢占）

每创建一个实例 Namespace，自动创建一个 ResourceQuota：

```python
def build_resource_quota(
    namespace: str,
    cpu_limit: str = "4",         # 该实例最多用 4 核
    mem_limit: str = "8Gi",       # 该实例最多用 8G 内存
    max_pods: int = 20,           # 最多 20 个 Pod
    storage_limit: str = "200Gi", # 总存储上限
    max_pvcs: int = 5,            # 最多 5 个 PVC
) -> k8s_client.V1ResourceQuota:
    return k8s_client.V1ResourceQuota(
        metadata=k8s_client.V1ObjectMeta(
            name="openclaw-quota",
            namespace=namespace,
        ),
        spec=k8s_client.V1ResourceQuotaSpec(
            hard={
                "requests.cpu": cpu_limit,
                "requests.memory": mem_limit,
                "limits.cpu": cpu_limit,
                "limits.memory": mem_limit,
                "pods": str(max_pods),
                "services.loadbalancers": "1",
                "requests.storage": storage_limit,
                "persistentvolumeclaims": str(max_pvcs),
            }
        ),
    )
```

对应 YAML：

```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: openclaw-quota
  namespace: oc-prod-main
spec:
  hard:
    requests.cpu: "4"
    requests.memory: 8Gi
    limits.cpu: "4"
    limits.memory: 8Gi
    pods: "20"
    services.loadbalancers: "1"       # 每个实例最多 1 个 CLB
```

部署表单提供预设档位（用户可自定义）：

| 档位 | CPU 配额 | 内存配额 | 存储空间 | 最大 Pod 数 | 适用场景 |
|------|---------|---------|---------|-----------|---------|
| 小型 | 2c | 4Gi | 20Gi | 10 | 开发/测试 |
| 中型 | 4c | 8Gi | 80Gi | 20 | 预发/小规模生产 |
| 大型 | 8c | 16Gi | 160Gi | 50 | 生产主力 |
| 自定义 | 用户填写 | 用户填写 | 用户填写（>=20Gi） | 用户填写 | 特殊需求 |

> **存储配额说明**：每个实例最低存储空间为 **20Gi**。组织级别通过 `max_storage_total` 字段限制总存储用量。套餐默认存储配额：免费版 100Gi、专业版 500Gi、企业版 2000Gi。部署时会校验实例数 + CPU + 内存 + 存储是否超出组织配额。K8s 层面通过 ResourceQuota 的 `requests.storage` 字段进行兜底限制。

### 3.4 LimitRange（兜底默认值）

防止用户创建的容器没有设 limits，消耗无上限：

```python
def build_limit_range(namespace: str) -> k8s_client.V1LimitRange:
    return k8s_client.V1LimitRange(
        metadata=k8s_client.V1ObjectMeta(
            name="openclaw-limits",
            namespace=namespace,
        ),
        spec=k8s_client.V1LimitRangeSpec(
            limits=[
                k8s_client.V1LimitRangeItem(
                    type="Container",
                    default={"cpu": "1", "memory": "1Gi"},
                    default_request={"cpu": "0.5", "memory": "512Mi"},
                    max={"cpu": "2", "memory": "4Gi"},
                )
            ]
        ),
    )
```

### 3.5 NetworkPolicy（网络隔离）

默认 K8s 里所有 Pod 互通。加 NetworkPolicy 后，不同实例之间完全不能访问：

```python
def build_network_policy(namespace: str) -> dict:
    """
    网络隔离策略:
    - 允许同 Namespace 内 Pod 互访（同一实例内部通信）
    - 允许从 nodeskclaw Namespace 访问（管理：健康检查、日志）
    - 允许 Ingress Controller 流量进入
    - 禁止其他 Namespace（其他 OpenClaw 实例）访问
    - 出站不限制（OpenClaw 需要访问外部 API）
    """
    return {
        "apiVersion": "networking.k8s.io/v1",
        "kind": "NetworkPolicy",
        "metadata": {
            "name": "openclaw-isolation",
            "namespace": namespace,
        },
        "spec": {
            "podSelector": {},
            "policyTypes": ["Ingress", "Egress"],
            "ingress": [
                # 同 Namespace 内互访
                {"from": [{"podSelector": {}}]},
                # NoDeskClaw 管理访问
                {"from": [{"namespaceSelector": {
                    "matchLabels": {"app.kubernetes.io/name": "nodeskclaw"}
                }}]},
                # Ingress Controller 流量
                {"from": [{"namespaceSelector": {
                    "matchLabels": {"app.kubernetes.io/name": "ingress-nginx"}
                }}]},
            ],
            "egress": [
                {"to": [{}]},       # 出站不限制
            ],
        },
    }
```

效果示意：

```
oc-prod-main 的 Pod  ──✗──→  oc-staging 的 Pod         (禁止)
oc-prod-main 的 Pod  ──✗──→  oc-dev-zhangsan 的 Pod    (禁止)
oc-prod-main 的 Pod  ──✓──→  oc-prod-main 的 Pod       (允许，同 NS)
nodeskclaw 的 Pod     ──✓──→  任何 oc-* 的 Pod           (允许，管理需要)
ingress-nginx        ──✓──→  任何 oc-* 的 Pod           (允许，流量入口)
```

> VKE 默认支持 NetworkPolicy（基于 Calico），不需要额外安装组件。

### 3.6 Namespace 创建编排

部署时 NoDeskClaw 自动创建 Namespace 并配置隔离：

```python
async def ensure_namespace_with_isolation(
    k8s: K8sClient,
    namespace: str,
    quota_cpu: str = "4",
    quota_mem: str = "8Gi",
    max_pods: int = 20,
):
    """创建 Namespace + ResourceQuota + LimitRange + NetworkPolicy（一步到位）"""

    # 1. 创建 Namespace（带管理标签）
    ns_body = k8s_client.V1Namespace(
        metadata=k8s_client.V1ObjectMeta(
            name=namespace,
            labels={
                "app.kubernetes.io/managed-by": "nodeskclaw",
                "nodeskclaw.io/type": "openclaw-instance",
            },
        )
    )
    try:
        await k8s.core.create_namespace(body=ns_body)
    except k8s_client.ApiException as e:
        if e.status != 409:    # 409 = 已存在，跳过
            raise

    # 2. ResourceQuota（限制该 NS 的资源总量）
    quota = build_resource_quota(namespace, quota_cpu, quota_mem, max_pods)
    await _apply_resource(
        k8s.core.create_namespaced_resource_quota,
        k8s.core.patch_namespaced_resource_quota,
        namespace, "openclaw-quota", quota,
    )

    # 3. LimitRange（兜底默认 limits）
    lr = build_limit_range(namespace)
    await _apply_resource(
        k8s.core.create_namespaced_limit_range,
        k8s.core.patch_namespaced_limit_range,
        namespace, "openclaw-limits", lr,
    )

    # 4. NetworkPolicy（网络隔离）
    np = build_network_policy(namespace)
    await _apply_network_policy(k8s, namespace, np)


async def _apply_resource(create_fn, patch_fn, namespace, name, body):
    """创建或更新资源（幂等）"""
    try:
        await create_fn(namespace=namespace, body=body)
    except k8s_client.ApiException as e:
        if e.status == 409:
            await patch_fn(name=name, namespace=namespace, body=body)
        else:
            raise
```

---

## 四、OpenClaw 部署到 VKE 会创建什么资源

一次 "一键部署" 在 K8s 里创建的资源全景：

```
Namespace: oc-prod-main (每实例独占)
│
├── ResourceQuota: openclaw-quota        ← 自动创建，资源配额上限
│   └── limits: 4c/8Gi, maxPods: 20, storage: 200Gi, pvc: 5
│
├── LimitRange: openclaw-limits          ← 自动创建，容器默认 limits
│   └── default: 1c/1Gi, max: 2c/4Gi
│
├── NetworkPolicy: openclaw-isolation    ← 自动创建，网络隔离
│   └── 仅允许同 NS + NoDeskClaw + Ingress
│
├── PVC: prod-main-root-data             ← 自动创建，实例持久化存储
│   ├── size: 100Gi (默认)
│   ├── storageClass: ebs-ssd (VKE 默认)
│   ├── accessMode: ReadWriteOnce
│   └── 挂载到 /root，持久化 OpenClaw 全部数据
│
├── ConfigMap: prod-main-config
│   └── 环境变量（FEISHU_CHANNEL、LOG_LEVEL 等）
│
├── Deployment: prod-main
│   └── Pod × N (replicas)
│       ├── initContainer: root-init     ← 首次部署初始化 .openclaw/ 用户数据
│       │   ├── image: 同主容器
│       │   ├── command: /init-container.sh（检查 PVC → 首次则初始化用户数据目录）
│       │   └── volumeMount: PVC → /init-data
│       │
│       └── Container: openclaw
│           ├── image: cr-cn-beijing.volces.com/nodeskclaw/openclaw:v1.0.0
│           ├── command: entrypoint 内 exec openclaw gateway --allow-unconfigured --bind lan
│           ├── resources: {requests: 0.5c/512Mi, limits: 1c/1Gi}
│           ├── envFrom: ConfigMap + Secret
│           ├── ports: 18789
│           ├── volumeMount: PVC → /root  ← 持久化 home 目录
│           ├── livenessProbe: exec ["openclaw", "health"]
│           ├── readinessProbe: exec ["openclaw", "health"]
│           └── terminationGracePeriodSeconds: 30
│
├── Service: prod-main
│   ├── type: ClusterIP (默认)
│   │         NodePort (可选)
│   │         LoadBalancer (可选，创建火山云 CLB)
│   └── port: 80 → targetPort: 18789
│
└── Ingress: prod-main (可选，需要域名时)
    ├── ingressClassName: nginx        ← VKE 特有
    ├── host: prod-main.example.com
    └── path: / → Service:80
```

**OpenClaw 容器内关键路径**（Init Container 和 PVC 设计依据）：

| 路径 | 说明 | 是否需要持久化 |
|------|------|-------------|
| `/usr/local/bin/openclaw` | CLI 入口（npm -g 安装） | 否（镜像层，换镜像自动更新） |
| `/usr/local/lib/node_modules/openclaw/` | OpenClaw 核心代码 | 否（镜像层） |
| `/root/.openclaw/openclaw.json` | 主配置（模型、agent 设置） | 是（用户数据，不可覆盖） |
| `/root/.openclaw/agents/main/sessions/` | 会话历史 | 是 |
| `/root/.openclaw/credentials/` | API Key 等凭证 | 是 |
| `/root/.openclaw/extensions/` | 插件代码（内置 + 用户自定义） | 是 |
| `/root/.openclaw/workspace/` | 办公室（SKILL、项目文件） | 是 |
| `/root/.openclaw/memory/` | 长期记忆 | 是 |
| `/root/.openclaw/data/` | 持久化数据（去重记录等） | 是 |
| `/tmp/jiti/` | TypeScript 编译缓存 | 否（临时文件，不挂载） |

> 程序文件（Node.js + OpenClaw）在镜像层 `/usr/local/`，不在 PVC 中。换镜像即升级程序，Init Container 只负责用户数据初始化。

---

## 四、资源构建器 — 直接创建 K8s 资源

不使用 Helm Chart，而是通过 `kubernetes-asyncio` 直接以 Python 代码创建所有 K8s 资源。这样做的好处：

- **零外部依赖**：不需要在容器里安装 `helm` CLI
- **更细粒度控制**：每个资源创建步骤都能实时广播进度
- **调试友好**：出错时能精确定位到哪个资源创建失败
- **代码即配置**：资源定义就是 Python 代码，IDE 有补全和类型提示

### 4.1 资源构建函数

```python
# app/services/resource_builder.py

from kubernetes_asyncio import client as k8s_client

def build_labels(instance_name: str, instance_id: str, image_tag: str) -> dict:
    """统一标签，所有 NoDeskClaw 管理的资源都带这组标签"""
    return {
        "app.kubernetes.io/name": "openclaw",
        "app.kubernetes.io/instance": instance_name,
        "app.kubernetes.io/version": image_tag,
        "app.kubernetes.io/managed-by": "nodeskclaw",
        "nodeskclaw.io/instance-id": instance_id,
    }

def build_selector_labels(instance_name: str) -> dict:
    """Pod selector 标签（Deployment.spec.selector 和 Service.spec.selector）"""
    return {
        "app.kubernetes.io/name": "openclaw",
        "app.kubernetes.io/instance": instance_name,
    }
```

### 4.2 ConfigMap 构建

```python
def build_configmap(
    name: str, namespace: str,
    env_vars: dict[str, str],
    labels: dict,
) -> k8s_client.V1ConfigMap:
    """构建环境变量 ConfigMap"""
    return k8s_client.V1ConfigMap(
        metadata=k8s_client.V1ObjectMeta(
            name=f"{name}-config",
            namespace=namespace,
            labels=labels,
        ),
        data={k: str(v) for k, v in env_vars.items()},
    )
```

### 4.3 Deployment 构建

```python
def build_deployment(
    name: str, namespace: str,
    image: str, replicas: int,
    cpu_request: str, cpu_limit: str,
    mem_request: str, mem_limit: str,
    has_configmap: bool,
    labels: dict, selector_labels: dict,
) -> k8s_client.V1Deployment:
    """构建 Deployment 对象"""

    # 容器定义
    container = k8s_client.V1Container(
        name="openclaw",
        image=image,
        image_pull_policy="IfNotPresent",
        ports=[k8s_client.V1ContainerPort(container_port=18789, name="http")],
        resources=k8s_client.V1ResourceRequirements(
            requests={"cpu": cpu_request, "memory": mem_request},
            limits={"cpu": cpu_limit, "memory": mem_limit},
        ),
        liveness_probe=k8s_client.V1Probe(
            _exec=k8s_client.V1ExecAction(command=["openclaw", "health"]),
            initial_delay_seconds=10,
            period_seconds=10,
        ),
        readiness_probe=k8s_client.V1Probe(
            _exec=k8s_client.V1ExecAction(command=["openclaw", "health"]),
            initial_delay_seconds=5,
            period_seconds=5,
        ),
    )

    # envFrom: ConfigMap + Secret
    container.env_from = []
    if has_configmap:
        container.env_from.append(
            k8s_client.V1EnvFromSource(
                config_map_ref=k8s_client.V1ConfigMapEnvSource(name=f"{name}-config")
            )
        )
    container.env_from.append(
        k8s_client.V1EnvFromSource(
            secret_ref=k8s_client.V1SecretEnvSource(name=f"{name}-secret", optional=True)
        )
    )

    # PVC 挂载到 /root
    pvc_name = f"{name}-root-data"
    container.volume_mounts = [
        k8s_client.V1VolumeMount(name="root-data", mount_path="/root")
    ]

    # Init Container: 首次部署初始化 .openclaw/ 用户数据
    init_container = k8s_client.V1Container(
        name="root-init",
        image=image,
        command=["/init-container.sh"],
        volume_mounts=[
            k8s_client.V1VolumeMount(name="root-data", mount_path="/init-data")
        ],
    )

    return k8s_client.V1Deployment(
        metadata=k8s_client.V1ObjectMeta(
            name=name,
            namespace=namespace,
            labels=labels,
        ),
        spec=k8s_client.V1DeploymentSpec(
            replicas=1,  # 固定单副本（PVC ReadWriteOnce）
            selector=k8s_client.V1LabelSelector(match_labels=selector_labels),
            strategy=k8s_client.V1DeploymentStrategy(
                type="RollingUpdate",
                rolling_update=k8s_client.V1RollingUpdateDeployment(
                    max_surge=1,
                    max_unavailable=0,
                ),
            ),
            template=k8s_client.V1PodTemplateSpec(
                metadata=k8s_client.V1ObjectMeta(
                    labels=selector_labels,
                    annotations={"nodeskclaw.io/restartedAt": ""},
                ),
                spec=k8s_client.V1PodSpec(
                    init_containers=[init_container],
                    containers=[container],
                    termination_grace_period_seconds=30,
                    volumes=[
                        k8s_client.V1Volume(
                            name="root-data",
                            persistent_volume_claim=k8s_client.V1PersistentVolumeClaimVolumeSource(
                                claim_name=pvc_name
                            ),
                        )
                    ],
                ),
            ),
        ),
    )
```

### 4.4 PVC 构建

```python
def build_pvc(
    name: str, namespace: str,
    storage_size: str,            # 如 "100Gi"
    labels: dict,
    storage_class: str = "",      # VKE StorageClass，空则用集群默认
) -> k8s_client.V1PersistentVolumeClaim:
    """构建 PVC — 每个实例一个，挂载到 /root"""
    return k8s_client.V1PersistentVolumeClaim(
        metadata=k8s_client.V1ObjectMeta(
            name=f"{name}-root-data",
            namespace=namespace,
            labels=labels,
        ),
        spec=k8s_client.V1PersistentVolumeClaimSpec(
            access_modes=["ReadWriteOnce"],
            storage_class_name=storage_class or None,
            resources=k8s_client.V1ResourceRequirements(
                requests={"storage": storage_size}
            ),
        ),
    )
```

### 4.5 Service 构建

```python
def build_service(
    name: str, namespace: str,
    service_type: str,            # "ClusterIP" / "NodePort" / "LoadBalancer"
    annotations: dict | None,
    labels: dict, selector_labels: dict,
) -> k8s_client.V1Service:
    """构建 Service 对象"""
    return k8s_client.V1Service(
        metadata=k8s_client.V1ObjectMeta(
            name=name,
            namespace=namespace,
            labels=labels,
            annotations=annotations or {},
        ),
        spec=k8s_client.V1ServiceSpec(
            type=service_type,
            ports=[
                k8s_client.V1ServicePort(
                    port=80,
                    target_port=18789,
                    protocol="TCP",
                    name="http",
                )
            ],
            selector=selector_labels,
        ),
    )


def build_vke_annotations(req) -> dict | None:
    """火山云 VKE LoadBalancer 专用 annotation"""
    if req.service_type != ServiceType.load_balancer:
        return None
    return {
        "service.beta.kubernetes.io/volcengine-loadbalancer-subnet-id": settings.vke_subnet_id,
        "service.beta.kubernetes.io/volcengine-loadbalancer-address-type": "PUBLIC",
    }
```

### 4.5 Ingress 构建

```python
def build_ingress(
    name: str, namespace: str,
    host: str,
    labels: dict,
) -> k8s_client.V1Ingress:
    """构建 Ingress 对象（VKE 使用 nginx IngressClass）"""
    return k8s_client.V1Ingress(
        metadata=k8s_client.V1ObjectMeta(
            name=name,
            namespace=namespace,
            labels=labels,
        ),
        spec=k8s_client.V1IngressSpec(
            ingress_class_name="nginx",       # VKE 固定写法
            rules=[
                k8s_client.V1IngressRule(
                    host=host,
                    http=k8s_client.V1HTTPIngressRuleValue(
                        paths=[
                            k8s_client.V1HTTPIngressPath(
                                path="/",
                                path_type="Prefix",
                                backend=k8s_client.V1IngressBackend(
                                    service=k8s_client.V1IngressServiceBackend(
                                        name=name,
                                        port=k8s_client.V1ServiceBackendPort(number=80),
                                    )
                                ),
                            )
                        ]
                    ),
                )
            ],
        ),
    )
```

---

## 五、NoDeskClaw 怎么创建 K8s 资源

### 5.1 页面表单 → 资源对象

用户在页面上填的配置，直接转成 kubernetes-asyncio 的资源对象：

```python
# app/services/deploy_service.py

from app.services.resource_builder import (
    build_labels, build_selector_labels,
    build_configmap, build_deployment, build_service,
    build_ingress, build_vke_annotations,
)

async def create_openclaw_instance(
    k8s: K8sClient,
    req: DeployRequest,
    instance_id: str,
):
    """
    通过 kubernetes-asyncio 直接创建所有 K8s 资源。
    按顺序创建：Namespace → ConfigMap → Deployment → Service → Ingress
    """
    image = f"{settings.openclaw_image_registry}:{req.image_version}"
    labels = build_labels(req.name, instance_id, req.image_version)
    selector_labels = build_selector_labels(req.name)

    # 1. ConfigMap（有环境变量时才创建）
    if req.env_vars:
        cm = build_configmap(req.name, req.namespace, req.env_vars, labels)
        await k8s.core.create_namespaced_config_map(namespace=req.namespace, body=cm)

    # 2. Deployment
    deploy = build_deployment(
        name=req.name, namespace=req.namespace,
        image=image, replicas=req.replicas,
        cpu_request=req.cpu_request, cpu_limit=req.cpu_limit,
        mem_request=req.mem_request, mem_limit=req.mem_limit,
        has_configmap=bool(req.env_vars),
        labels=labels, selector_labels=selector_labels,
    )
    await k8s.apps.create_namespaced_deployment(namespace=req.namespace, body=deploy)

    # 3. Service
    svc = build_service(
        name=req.name, namespace=req.namespace,
        service_type=req.service_type.value,
        annotations=build_vke_annotations(req),
        labels=labels, selector_labels=selector_labels,
    )
    await k8s.core.create_namespaced_service(namespace=req.namespace, body=svc)

    # 4. Ingress（可选，有域名时才创建）
    if req.ingress_domain:
        ing = build_ingress(req.name, req.namespace, req.ingress_domain, labels)
        await k8s.networking.create_namespaced_ingress(namespace=req.namespace, body=ing)
```

### 5.2 执行部署（异步任务）

```python
async def _do_deploy(self, deploy_id: str):
    """部署核心流程（后台异步任务）"""
    record = await self._get_deploy_record(deploy_id)
    instance = record.instance
    cluster = instance.cluster

    k8s = K8sClient(await self._k8s_manager.get_or_create(cluster.id, cluster.kubeconfig_enc))

    # Step 1: 确保 Namespace + 隔离策略（ResourceQuota + LimitRange + NetworkPolicy）
    await self._broadcast_step(deploy_id, "namespace", "running")
    await ensure_namespace_with_isolation(
        k8s, instance.namespace,
        quota_cpu=record.request.quota_cpu,
        quota_mem=record.request.quota_mem,
    )
    await self._broadcast_step(deploy_id, "namespace", "done")

    # Step 2: 创建 K8s 资源（ConfigMap + Deployment + Service + Ingress）
    await self._broadcast_step(deploy_id, "create_resources", "running")
    try:
        await create_openclaw_instance(k8s, record.request, str(instance.id))
    except k8s_client.ApiException as e:
        if e.status == 409:
            # 资源已存在，执行更新
            await update_openclaw_instance(k8s, record.request, str(instance.id))
        else:
            raise
    await self._broadcast_step(deploy_id, "create_resources", "done")

    # Step 3: 等待 Pod Ready
    await self._broadcast_step(deploy_id, "waiting_pods", "running")
    await self._wait_for_pods_ready(k8s, instance, deploy_id, timeout=300)
    await self._broadcast_step(deploy_id, "waiting_pods", "done")

    # Step 4: 验证 Service
    await self._broadcast_step(deploy_id, "service_ready", "running")
    svc_info = await k8s.get_service(instance.namespace, instance.name)
    await self._broadcast_step(deploy_id, "service_ready", "done", extra=svc_info)

    # 完成
    await self._broadcast_progress(deploy_id, 100, "success")
```

### 5.3 更新实例（滚动更新 / 配置变更）

```python
async def update_openclaw_instance(
    k8s: K8sClient,
    req: DeployRequest,
    instance_id: str,
):
    """
    更新已有实例的 K8s 资源（patch 方式，触发滚动更新）
    配置变更时在 ConfigMap 中设 OPENCLAW_FORCE_RECONFIG=true，
    Pod 重启后 entrypoint 从模板重新生成 openclaw.json，
    更新完成后再将 FORCE_RECONFIG 改回 false。
    """
    image = f"{settings.openclaw_image_registry}:{req.image_version}"
    labels = build_labels(req.name, instance_id, req.image_version)

    # 1. 更新 ConfigMap（配置变更时含 OPENCLAW_FORCE_RECONFIG=true）
    if req.env_vars:
        cm = build_configmap(req.name, req.namespace, req.env_vars, labels)
        try:
            await k8s.core.patch_namespaced_config_map(
                name=f"{req.name}-config", namespace=req.namespace, body=cm
            )
        except k8s_client.ApiException as e:
            if e.status == 404:
                await k8s.core.create_namespaced_config_map(namespace=req.namespace, body=cm)
            else:
                raise

    # 2. 更新 Deployment（镜像 / 副本数 / 资源配额）
    deploy = build_deployment(
        name=req.name, namespace=req.namespace,
        image=image, replicas=req.replicas,
        cpu_request=req.cpu_request, cpu_limit=req.cpu_limit,
        mem_request=req.mem_request, mem_limit=req.mem_limit,
        has_configmap=bool(req.env_vars),
        labels=labels, selector_labels=build_selector_labels(req.name),
    )
    await k8s.apps.patch_namespaced_deployment(
        name=req.name, namespace=req.namespace, body=deploy
    )

    # 3. 更新 Service
    svc = build_service(
        name=req.name, namespace=req.namespace,
        service_type=req.service_type.value,
        annotations=build_vke_annotations(req),
        labels=labels, selector_labels=build_selector_labels(req.name),
    )
    await k8s.core.patch_namespaced_service(
        name=req.name, namespace=req.namespace, body=svc
    )
```

### 5.4 回滚实例（从 DB 历史记录恢复）

```python
async def rollback_openclaw_instance(
    k8s: K8sClient,
    instance,
    target_record: DeployRecord,
):
    """从 DB 历史记录回滚，不依赖 Helm revision"""
    config = target_record.config_snapshot    # JSON，完整配置快照
    image = f"{settings.openclaw_image_registry}:{config['image_version']}"

    # 回滚 Deployment（镜像 + 副本数 + 资源配额）
    await k8s.update_deployment_image(instance.namespace, instance.name, image)
    await k8s.scale_deployment(instance.namespace, instance.name, config["replicas"])

    # 回滚 ConfigMap
    if config.get("env_vars"):
        labels = build_labels(instance.name, str(instance.id), config["image_version"])
        cm = build_configmap(instance.name, instance.namespace, config["env_vars"], labels)
        await k8s.core.patch_namespaced_config_map(
            name=f"{instance.name}-config", namespace=instance.namespace, body=cm
        )
```

### 5.5 删除实例（清理所有资源）

```python
async def delete_openclaw_instance(k8s: K8sClient, namespace: str, name: str):
    """删除实例的所有 K8s 资源"""
    # 按依赖倒序删除
    # 1. Ingress（可能不存在）
    try:
        await k8s.networking.delete_namespaced_ingress(name=name, namespace=namespace)
    except k8s_client.ApiException as e:
        if e.status != 404:
            raise

    # 2. Service
    try:
        await k8s.core.delete_namespaced_service(name=name, namespace=namespace)
    except k8s_client.ApiException as e:
        if e.status != 404:
            raise

    # 3. Deployment（会自动级联删除 ReplicaSet 和 Pod）
    await k8s.apps.delete_namespaced_deployment(name=name, namespace=namespace)

    # 4. ConfigMap + Secret（可能不存在）
    for resource_name in [f"{name}-config", f"{name}-secret"]:
        try:
            await k8s.core.delete_namespaced_config_map(
                name=resource_name, namespace=namespace
            )
        except k8s_client.ApiException:
            pass  # 忽略 404

    # 5. Namespace — 级联删除所有资源（PVC、ResourceQuota 等）
    await k8s.core.delete_namespace(name=namespace)
    # 6. 后台延迟清理 Released PV（reclaimPolicy=Delete 已自动回收，此为兜底）
    _schedule_pv_cleanup(k8s, namespace)
```

### 5.6 等待 Pod Ready（轮询）

```python
async def _wait_for_pods_ready(self, k8s: K8sClient, instance, deploy_id: str, timeout: int = 300):
    """轮询 Deployment 状态直到所有 Pod Ready"""
    start = time.time()

    while time.time() - start < timeout:
        status = await k8s.get_deployment_status(instance.namespace, instance.name)

        total = status["replicas"]
        ready = status["ready_replicas"]
        progress = int((ready / total) * 70 + 20) if total > 0 else 20  # 20-90% 区间

        await self._broadcast_progress(
            deploy_id, progress, "in_progress",
            message=f"Pod 就绪: {ready}/{total}"
        )

        if ready == total and total > 0:
            return  # 全部 Ready

        await asyncio.sleep(3)

    raise DeployError(40003, f"部署超时: {timeout}s 内 Pod 未全部就绪")
```

---

## 六、RBAC — NoDeskClaw 需要的 K8s 权限

NoDeskClaw 部署在 VKE 集群内时，需要 ServiceAccount 有足够权限操作其他 Namespace 的资源：

```yaml
# deploy/k8s/rbac.yaml

# 1. ServiceAccount
apiVersion: v1
kind: ServiceAccount
metadata:
  name: nodeskclaw-sa
  namespace: nodeskclaw

---
# 2. ClusterRole（集群级别权限）
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: nodeskclaw-role
rules:
  # Namespace 管理
  - apiGroups: [""]
    resources: ["namespaces"]
    verbs: ["get", "list", "create", "patch"]

  # Node 查看（集群概览）
  - apiGroups: [""]
    resources: ["nodes"]
    verbs: ["get", "list"]

  # Pod 操作（查看、日志、exec）
  - apiGroups: [""]
    resources: ["pods", "pods/log", "pods/exec"]
    verbs: ["get", "list", "watch", "delete", "create"]

  # Secret 操作（敏感配置注入）
  - apiGroups: [""]
    resources: ["secrets"]
    verbs: ["get", "list", "create", "update", "patch", "delete"]

  # Service 操作
  - apiGroups: [""]
    resources: ["services"]
    verbs: ["get", "list", "create", "update", "patch", "delete"]

  # ConfigMap 操作
  - apiGroups: [""]
    resources: ["configmaps"]
    verbs: ["get", "list", "create", "update", "patch", "delete"]

  # Deployment 操作
  - apiGroups: ["apps"]
    resources: ["deployments", "deployments/scale", "replicasets"]
    verbs: ["get", "list", "watch", "create", "update", "patch", "delete"]

  # Ingress + NetworkPolicy 操作
  - apiGroups: ["networking.k8s.io"]
    resources: ["ingresses", "networkpolicies"]
    verbs: ["get", "list", "create", "update", "patch", "delete"]

  # ResourceQuota + LimitRange（实例隔离）
  - apiGroups: [""]
    resources: ["resourcequotas", "limitranges"]
    verbs: ["get", "list", "create", "update", "patch", "delete"]

  # PersistentVolumeClaim（实例持久化存储）
  - apiGroups: [""]
    resources: ["persistentvolumeclaims"]
    verbs: ["get", "list", "create", "update", "patch", "delete"]

  # Events 查看
  - apiGroups: [""]
    resources: ["events"]
    verbs: ["get", "list", "watch"]

  # Metrics（Pod 资源使用）
  - apiGroups: ["metrics.k8s.io"]
    resources: ["pods", "nodes"]
    verbs: ["get", "list"]

---
# 3. ClusterRoleBinding
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: nodeskclaw-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: nodeskclaw-role
subjects:
  - kind: ServiceAccount
    name: nodeskclaw-sa
    namespace: nodeskclaw
```

---

## 七、火山云 VKE 特有配置速查

### 7.1 Service LoadBalancer 的 Annotation

VKE 用 Annotation 控制 CLB（Cloud Load Balancer）行为：

| Annotation | 值 | 说明 |
|-----------|-----|------|
| `service.beta.kubernetes.io/volcengine-loadbalancer-subnet-id` | `subnet-xxx` | **必填**，CLB 所在子网 |
| `service.beta.kubernetes.io/volcengine-loadbalancer-address-type` | `PUBLIC` / `PRIVATE` | 公网或内网 |
| `service.beta.kubernetes.io/volcengine-loadbalancer-id` | `clb-xxx` | 复用已有 CLB（不写则自动创建） |
| `service.beta.kubernetes.io/volcengine-loadbalancer-bandwidth-package-id` | `bwp-xxx` | 共享带宽包 |

示例：自动创建公网 CLB

```yaml
apiVersion: v1
kind: Service
metadata:
  name: openclaw-prod-1
  annotations:
    service.beta.kubernetes.io/volcengine-loadbalancer-subnet-id: "subnet-abc123"
    service.beta.kubernetes.io/volcengine-loadbalancer-address-type: "PUBLIC"
spec:
  type: LoadBalancer
  ports:
    - port: 80
      targetPort: 18789
  selector:
    app.kubernetes.io/instance: openclaw-prod-1
```

### 7.2 Ingress（Nginx Ingress Controller）

VKE 集群需要先安装 `ingress-nginx` 组件：

```
VKE 控制台 → 集群 → 组件管理 → 安装 ingress-nginx
```

然后 Ingress 使用 `ingressClassName: nginx`：

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: openclaw-prod-1
spec:
  ingressClassName: nginx              # VKE 固定写法
  rules:
    - host: openclaw.example.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: openclaw-prod-1
                port:
                  number: 80
```

### 7.3 VKE 环境变量配置

NoDeskClaw 的 `.env` 需要配置 VKE 相关参数：

```bash
# 火山云 VKE 专用
NODESKCLAW_VKE_SUBNET_ID=subnet-abc123          # CLB 子网 ID
NODESKCLAW_VKE_DEFAULT_ADDRESS_TYPE=PUBLIC       # 默认 CLB 类型
NODESKCLAW_VKE_INGRESS_CLASS=nginx               # Ingress Class

# 镜像仓库（火山云 CR）
NODESKCLAW_IMAGE_REGISTRY=cr-xxx.volcengine.com/openclaw/openclaw
```

---

## 八、完整部署流程图

```
用户点击 [🚀 确认部署]
│
▼
┌─────────────────────────────────────────────────────────────┐
│ POST /api/v1/deploy                                          │
│                                                              │
│ DeployRequest:                                               │
│   name: "openclaw-prod-1"                                    │
│   # namespace 由后端自动生成: oc-openclaw-prod-1              │
│   image_version: "v2.1.0"                                    │
│   storage_size: "100Gi"                                      │
│   service_type: "LoadBalancer"                               │
│   env_vars: {"OPENCLAW_MODEL_PROVIDER": "anthropic"}         │
└─────────────┬───────────────────────────────────────────────┘
              │
              ▼
┌─────────────────────────────────────────────────────────────┐
│ DeployService                                                │
│                                                              │
│ 1. 写 Instance + DeployRecord 到 DB                          │
│ 2. asyncio.create_task(_do_deploy)                           │
│ 3. 返回 deploy_id → 前端连 SSE 接收进度                      │
└─────────────┬───────────────────────────────────────────────┘
              │
              ▼  (后台异步)
┌─────────────────────────────────────────────────────────────┐
│ _do_deploy                                                   │
│                                                              │
│ Step 1: ensure_namespace_with_isolation("oc-prod-main")       │
│   └─ 创建 Namespace (带管理标签)                              │
│   └─ 创建 ResourceQuota (4c/8Gi/20 pods)                    │
│   └─ 创建 LimitRange (单容器上限 2c/4Gi)                     │
│   └─ 创建 NetworkPolicy (同 NS + NoDeskClaw + Ingress 放行)   │
│                                                              │
│ Step 2: create_openclaw_instance(k8s, request, instance_id)  │
│   通过 kubernetes-asyncio 直接创建:                           │
│                                                              │
│   2a. ConfigMap: openclaw-prod-1-config                      │
│       └─ CoreV1Api.create_namespaced_config_map()            │
│       └─ data: {"FEISHU_CHANNEL": "xxx"}                     │
│                                                              │
│   2b. Deployment: openclaw-prod-1 (3 replicas)               │
│       └─ AppsV1Api.create_namespaced_deployment()            │
│       └─ image: registry/openclaw:v2.1.0                     │
│       └─ resources: {requests: 0.5c/512Mi, limits: 1c/1Gi}  │
│                                                              │
│   2c. Service: openclaw-prod-1 (type: LoadBalancer)          │
│       └─ CoreV1Api.create_namespaced_service()               │
│       └─ annotations:                                        │
│           volcengine-loadbalancer-subnet-id: "subnet-xxx"    │
│           volcengine-loadbalancer-address-type: "PUBLIC"     │
│       └─ VKE 自动创建 CLB + 分配公网 IP                      │
│                                                              │
│   2d. (无 Ingress，因为用了 LoadBalancer)                     │
│                                                              │
│ Step 3: 轮询等待 Pod Ready                                   │
│   └─ 每 3s 查 Deployment status                             │
│   └─ EventBus.publish → SSE → 前端进度条                     │
│   └─ 3/3 Ready → 完成                                       │
│                                                              │
│ Step 4: 获取 Service 信息                                    │
│   └─ external_ip: CLB 分配的公网 IP                          │
│   └─ 返回给前端展示                                          │
│                                                              │
│ 更新 DB: Instance.status = "running"                         │
│ 广播: {status: "success", service: {external_ip: "x.x.x.x"}}│
└─────────────────────────────────────────────────────────────┘
              │
              ▼
        前端展示 ✅ 部署成功
        访问地址: http://x.x.x.x
```

---

## 九、NoDeskClaw 自身的 VKE 部署

### 9.0 CI/CD 自动化脚本

项目提供了统一的构建部署脚本 `deploy/deploy.sh`，支持三个独立组件的镜像构建、推送和 K8s 滚动更新：

```
deploy/
├── deploy.sh         # 统一构建推送部署脚本
├── init-secrets.sh   # 首次部署初始化
└── k8s/
    ├── backend.yaml  # 后端 Deployment + Service
    ├── admin.yaml    # Admin 前端 Deployment + Service
    └── portal.yaml   # Portal 前端 Deployment + Service
```

三个组件均部署在 `nodeskclaw-system` Namespace，镜像推送到火山云 CR `nodesk-center-cn-beijing.cr.volces.com/base-image/`：

| 组件 | 镜像名 | Dockerfile | Build Context | 端口 |
|------|--------|-----------|---------------|------|
| backend | `nodeskclaw-backend:TAG` | `nodeskclaw-backend/Dockerfile` | 项目根目录（需包含 `openclaw-channel-nodeskclaw/`） | 8000 |
| admin | `nodeskclaw-admin:TAG` | `nodeskclaw-frontend/Dockerfile` (多阶段 Node+Nginx) | `nodeskclaw-frontend/` | 80 |
| portal | `nodeskclaw-portal:TAG` | `nodeskclaw-portal/Dockerfile` (多阶段 Node+Nginx) | `nodeskclaw-portal/` | 80 |

Admin 和 Portal 前端的 Nginx 配置将 `/api` 请求反向代理到 `http://nodeskclaw-backend:8000`（K8s Service DNS），Admin 额外代理 `/stream`（SSE 事件流）。

```bash
# 日常更新：构建 + 推送 + K8s 滚动更新
./deploy/deploy.sh all              # 全量
./deploy/deploy.sh backend          # 仅后端
./deploy/deploy.sh admin            # 仅 Admin 前端
./deploy/deploy.sh portal           # 仅 Portal 前端

# 高级用法
./deploy/deploy.sh backend --build-only    # 仅构建推送，不更新 K8s
./deploy/deploy.sh admin --deploy-only --tag 20260218-b0f6ad1  # 仅更新到指定版本
./deploy/deploy.sh portal --no-cache       # 不使用 Docker 缓存
```

镜像标签格式：`YYYYMMDD-<git-short-hash>`（如 `20260218-b0f6ad1`）

### 9.1 首次部署

```bash
# 1. 连接 VKE 集群
export KUBECONFIG=~/.kube/vke-prod.yaml

# 2. 确保 Namespace 和镜像拉取密钥已存在
kubectl create namespace nodeskclaw-system   # 如果不存在
# cr-pull-secret 应已在集群中创建

# 3. 初始化：从 .env 创建 K8s Secret + 应用部署清单
./deploy/init-secrets.sh

# 4. 构建、推送、部署全部组件
./deploy/deploy.sh all

# 5. 验证
kubectl -n nodeskclaw-system get pods
kubectl -n nodeskclaw-system get svc
```

### 9.2 NoDeskClaw 自身的 Deployment YAML

```yaml
# deploy/k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: nodeskclaw
  namespace: nodeskclaw
spec:
  replicas: 2
  selector:
    matchLabels:
      app: nodeskclaw
  template:
    metadata:
      labels:
        app: nodeskclaw
    spec:
      serviceAccountName: nodeskclaw-sa    # 使用有权限的 SA
      containers:
        - name: nodeskclaw
          image: cr-xxx.volcengine.com/nodeskclaw/nodeskclaw:v0.1.0
          ports:
            - containerPort: 8000
          envFrom:
            - secretRef:
                name: nodeskclaw-secret
            - configMapRef:
                name: nodeskclaw-config
          # 数据库使用火山云 RDS PostgreSQL，无需本地 volume
          livenessProbe:
            httpGet:
              path: /api/v1/health
              port: 8000
            initialDelaySeconds: 10
          readinessProbe:
            httpGet:
              path: /api/v1/health
              port: 8000
            initialDelaySeconds: 5
      volumes:
        - name: data
          persistentVolumeClaim:
            claimName: nodeskclaw-data
```

---

## 十、LLM Proxy 独立服务部署

### 10.1 概述

LLM Proxy 是独立于 NoDeskClaw 后端的微服务，负责组织 Key 模式下的 LLM 请求代理转发。独立部署到 K8s 后，OpenClaw 实例通过私网域名访问该服务。

项目目录：`nodeskclaw-llm-proxy/`，包含代码、Dockerfile、构建脚本和 K8s 部署清单。

### 10.2 架构

#### 10.2.1 Pod 内部架构

```
LLM Proxy Pod (nodeskclaw-system namespace)
┌──────────────────────────────────┐
│ ┌──────────────┐                 │
│ │  LLM Proxy   │──── DB (RDS)   │
│ │  FastAPI     │                 │
│ │  :8080       │                 │
│ └──────┬───────┘                 │
│        │ HTTP_PROXY=127.0.0.1:7890
│ ┌──────┴───────┐                 │
│ │  Clash       │──── OpenAI / Anthropic / ...
│ │  mihomo      │                 │
│ │  :7890       │                 │
│ └──────────────┘                 │
└──────────────────────────────────┘
```

- **LLM Proxy**（FastAPI :8080）：接收 OpenClaw 的 LLM 请求，通过 `wp_api_key`（格式 `nodeskclaw-wp-{hex}`）鉴权，解析组织/个人 Key，转发到目标 Provider，记录 usage
- **Clash Sidecar**（mihomo :7890）：提供出站 HTTPS 代理，用于访问 OpenAI/Anthropic 等需要翻墙的外部 API

#### 10.2.2 网络链路（实际部署方案）

LLM Proxy 复用已有的 Controller ALB + Nginx Ingress Controller，不单独创建 ALB：

```
OpenClaw Pod
  │
  │ HTTPS (llm-proxy-claw.nodeskai.com)
  ▼
Controller ALB (私网 10.3.32.251, HTTPS:443)
  │ *.nodeskai.com 通配转发规则
  ▼
Nginx Ingress Controller Pod (nodeskclaw-system)
  │ Host: llm-proxy-claw.nodeskai.com
  ▼
LLM Proxy Service (ClusterIP, port:80 -> targetPort:8080)
  │
  ▼
LLM Proxy Pod (:8080)
```

涉及的 K8s 资源：

| 资源 | 名称 | 命名空间 | 说明 |
|------|------|----------|------|
| Ingress (alb) | `nodeskclaw-controller-alb-route` | nodeskclaw-system | `*.nodeskai.com` 通配，转发到 Nginx Controller |
| Ingress (nginx) | `nodeskclaw-llm-proxy` | nodeskclaw-system | 匹配 `llm-proxy-claw.nodeskai.com`，转发到 LLM Proxy Service |
| Service | `nodeskclaw-llm-proxy` | nodeskclaw-system | ClusterIP，port 80 -> targetPort 8080 |
| Deployment | `nodeskclaw-llm-proxy` | nodeskclaw-system | 1 副本，含 Clash sidecar |

DNS 配置：`llm-proxy-claw.nodeskai.com` 解析到 Controller ALB 的私网 VIP `10.3.32.251`（可用 `*.nodeskai.com` 通配 A 记录覆盖）。

### 10.3 部署步骤

```bash
# 1. 构建并推送镜像
cd nodeskclaw-llm-proxy
./build-and-push.sh

# 2. 创建 Secret（DATABASE_URL）
kubectl apply -f deploy/secret.yaml

# 3. 创建 Clash 配置
kubectl apply -f deploy/clash-config.yaml

# 4. 部署 Deployment + Service
kubectl apply -f deploy/deployment.yaml
kubectl apply -f deploy/service.yaml

# 5. 创建 Nginx Ingress（复用 Controller ALB）
kubectl apply -f - <<EOF
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: nodeskclaw-llm-proxy
  namespace: nodeskclaw-system
spec:
  ingressClassName: nginx
  rules:
  - host: llm-proxy-claw.nodeskai.com
    http:
      paths:
      - path: /
        pathType: Prefix
        backend:
          service:
            name: nodeskclaw-llm-proxy
            port:
              number: 80
EOF

# 6. 验证
kubectl exec -n <any-openclaw-namespace> <pod> -- \
  curl -sk https://llm-proxy-claw.nodeskai.com/health
# 期望返回: {"status":"ok"}
```

### 10.4 后端配置

在 `nodeskclaw-backend/.env` 中设置 LLM Proxy 地址：

```
LLM_PROXY_URL=https://llm-proxy-claw.nodeskai.com
LLM_PROXY_INTERNAL_URL=http://nodeskclaw-llm-proxy.nodeskclaw-system
```

`LLM_PROXY_INTERNAL_URL`（K8s 内网 DNS）优先使用，可绕过 ALB。跨集群实例（inst 集群）无法访问 infra 集群的 K8s 内网 DNS，此时后端自动回退到 `LLM_PROXY_URL`（外部域名，经 ALB）。后端写入 `openclaw.json` 时，组织 Key 的 `baseUrl` 指向 `{LLM_PROXY_URL}/{provider}/v1`，`apiKey` 使用实例的 `wp_api_key`（独立于 gateway token）。

**Proxy 转发上游请求时必须剥离 `Accept-Encoding`**：`_build_auth_headers` 已将 `accept-encoding` 加入剥离清单。Node.js 22 的原生 `fetch`（undici）默认携带 `Accept-Encoding: gzip, deflate`，若 Proxy 原样转发该头给上游 LLM Provider（如 MiniMax），上游返回 gzip 压缩的 SSE 流，但 `httpx` 因 `Accept-Encoding` 非自身添加而跳过自动解压，`aiter_lines()` 遍历到的是压缩二进制，客户端收到乱码导致空回复。剥离后 `httpx` 自行管理压缩协商并自动解压（详见第十一节）。此外 `_handle_stream` 保留了 `Cache-Control: no-transform` + `X-Accel-Buffering: no` 作为防御性措施，防止中间代理（ALB/Nginx）对响应流做二次压缩。

### 10.5 为什么不给 LLM Proxy 单独创建 ALB

早期方案尝试过为 LLM Proxy 创建独立 ALB Ingress（`ingressClassName: alb`），但遇到 VKE ALB 控制器的问题导致失败，详见第十一节。最终采用复用 Controller ALB + Nginx Ingress 的方案，优势：

- 不额外创建 ALB 实例，节省资源
- 复用已有的 `*.nodeskai.com` 通配转发规则和 TLS 证书
- Nginx Ingress 配置简单、行为可预测

---

## 十一、VKE ALB 踩坑记录

> 记录在 VKE 上使用 ALB Ingress 遇到的问题和排障经验，供后续参考。

### 11.1 背景

VKE 支持两种 IngressClass：

| IngressClass | 说明 | 适用场景 |
|-------------|------|----------|
| `nginx` | 通过 Nginx Ingress Controller 路由，所有域名共享一个入口 ALB | 大多数场景 |
| `alb` | 每个 Ingress 可对应一个独立 ALB 实例，VKE ALB 控制器自动管理 | 需要独立 ALB 的场景 |

项目当前架构：一个 Controller ALB（`alb-njd4tb8nlqn9`，私网 `10.3.32.251`）负责所有 `*.nodeskai.com` 流量，通过通配转发规则将请求转给 Nginx Ingress Controller，再由 Nginx 根据 Host header 分发到各个后端 Service。

### 11.2 问题 1：新建 ALB Ingress 后端服务器组为空

**现象**：为 LLM Proxy 创建 `ingressClassName: alb` 的 Ingress，VKE 自动创建了新 ALB 实例，但 ALB 的后端服务器组始终为空（0 个后端），导致 HTTPS 请求返回 503。

**排查过程**：

1. Ingress events 显示 `reconcile alb ingress successfully`，表面上成功
2. 但 ALB 控制台查看服务器组，确认后端数为 0
3. 对比已正常运行的 ALB（`alb-cnh4mmhwgdwk`）的 CRD，发现新 ALB 缺少两个关键字段：

```yaml
# 正常 ALB 的 CRD 有以下字段
spec:
  listeners:
    customizedConfig:
      customizedCfgID: ccfg-xxx
      customizedConfigEnabled: "on"
    enableHTTP2: true

# 新建的 ALB �RD 缺少这两个字段
```

4. Ingress events 中曾出现 `QuotaExceed.ListenerPerCustomizedCfg` 错误

**结论**：VKE ALB 控制器在自动创建 ALB 时，未正确配置 `customizedConfig` 和 `enableHTTP2`，导致后端注册失败但不报错。即使手动补上这两个字段，服务器组仍未被正确填充。

**规避方案**：放弃独立 ALB，改用 Nginx Ingress 复用已有 Controller ALB。

### 11.3 问题 2：共享 ALB 上的 Ingress 增删导致后端服务器组被清空

**现象**：在同一个 ALB（`alb-njd4tb8nlqn9`）上多次创建、删除 LLM Proxy 的 Ingress 资源后，原本正常的 `*.nodeskai.com` 通配规则也开始返回 503，所有域名全部不可用。

**原因**：VKE ALB 控制器在处理同一 ALB 上多个 Ingress 的增删时，内部状态出现异常，导致后端服务器组被错误地清空。

**修复方法**：

```bash
# 给 Ingress 加一个无害的 annotation，触发 VKE 控制器重新同步
kubectl annotate ingress nodeskclaw-controller-alb-route \
  -n nodeskclaw-system \
  force-sync=$(date +%s) --overwrite

# 等待几秒后检查 events
kubectl describe ingress nodeskclaw-controller-alb-route -n nodeskclaw-system
# 应看到: ReconcileALBIngressSuccessfully
```

**经验**：对 ALB 做任何 Ingress 变更后，务必验证既有规则仍然正常。如果发现 503，先尝试 force-sync annotation 触发重新同步。

### 11.4 问题 3：ALB 转发规则路径匹配类型错误

**现象**：ALB 重新同步后，只有根路径 `/` 能正确转发到后端，非根路径（`/health`、`/api`、`/v1/chat/completions` 等）全部返回 503。

**原因**：ALB 控制台上 `*.nodeskai.com` 转发规则的 URL 路径 `/` 被配置为**精确匹配**而非**前缀匹配**。Kubernetes Ingress 中 `pathType: Prefix` 的语义未被正确映射到 ALB 的转发规则。

**修复方法**：在 ALB 控制台手动修改转发规则，将路径匹配从"精确匹配"改为"前缀匹配"，或添加 `/**` 前缀匹配规则。

**验证**：

```bash
# 从任意 Pod 测试多个路径
for path in / /health /api /v1/chat/completions; do
  code=$(curl -sk -o /dev/null -w '%{http_code}' \
    https://llm-proxy-claw.nodeskai.com${path})
  echo "${path} -> ${code}"
done
# 所有路径都应返回非 503 的状态码
```

### 11.5 快速排障检查清单

遇到 ALB 相关的 503 时，按以下顺序排查：

| 步骤 | 检查项 | 命令/操作 |
|------|--------|-----------|
| 1 | Nginx Controller Pod 是否 Running | `kubectl get pods -n nodeskclaw-system -l app.kubernetes.io/component=controller` |
| 2 | 直接访问 Nginx Controller Pod 是否正常 | `curl -H "Host: xxx.nodeskai.com" http://<pod-ip>:80/health` |
| 3 | ALB 后端服务器组是否有后端 | ALB 控制台 -> 服务器组 -> 查看后端数量 |
| 4 | ALB 转发规则路径匹配类型 | ALB 控制台 -> 转发规则 -> 确认为"前缀匹配" |
| 5 | DNS 解析是否指向正确的 ALB VIP | `python3 -c "import socket; print(socket.gethostbyname('xxx.nodeskai.com'))"` |
| 6 | 是否有残留的 Ingress 或 ALB 资源 | `kubectl get ingress -A` / `kubectl get alb` |
| 7 | 强制重新同步 | `kubectl annotate ingress <name> -n nodeskclaw-system force-sync=$(date +%s) --overwrite` |

### 11.4 问题 3：LLM Proxy 转发 Accept-Encoding 导致上游返回压缩 SSE 流

**现象**：OpenClaw 实例通过 LLM Proxy 调用 MiniMax，流式请求返回 HTTP 200 但 OpenClaw 显示空回复。Session 文件中 assistant 消息 `content:[]`、`usage:{totalTokens:0}`。Proxy 日志显示上游返回 200 且有数据。

**排查过程**：

1. `curl --compressed` 从 Pod 内测试 LLM Proxy 流式端点，SSE 事件正常（`curl` 自动解压）
2. `curl` 不带 `--compressed` 但手动加 `-H "Accept-Encoding: gzip, deflate"` 测试同一端点，收到二进制乱码
3. 用 OpenAI Node SDK v6（OpenClaw 内置）测试，`for await (chunk of stream)` 循环 0 次迭代
4. 在 OpenClaw Pod 上验证 Node.js 22 的 `fetch` 默认请求头，确认自动携带 `accept-encoding: gzip, deflate`
5. 检查 Proxy 的 `_build_auth_headers` 代码，确认未剥离 `accept-encoding`，原样转发给上游

**根因**：

1. Node.js 22 的原生 `fetch`（undici）默认携带 `Accept-Encoding: gzip, deflate` 请求头
2. LLM Proxy 的 `_build_auth_headers` 将客户端请求头（含 `Accept-Encoding`）原样转发给上游 MiniMax
3. MiniMax 收到 `Accept-Encoding: gzip` 后返回 gzip 压缩的 SSE 流
4. Python `httpx` 的行为：当 `Accept-Encoding` 由调用方显式设置（非 httpx 自动添加）时，**不执行自动解压**
5. Proxy 的 `resp.aiter_lines()` 遍历到的是压缩二进制数据，无法产出有效 SSE 文本行
6. 压缩二进制被原样流式转发给 OpenClaw，OpenAI SDK 解析不到 `data:` 行，0 chunks 产出

**时间线**：此 bug 从 Proxy 创建（2026-02-21）起即存在。2 月 22 日 MiniMax 流式正常工作（`c84653a` 仅修复缺少 `[DONE]` 标记的问题），说明 MiniMax 当时未对 SSE 做压缩。2 月 27 日复现，推断 MiniMax 近期更新服务端行为，开始在收到 `Accept-Encoding` 时压缩 SSE 响应。

**解决方案**：在 `_build_auth_headers` 中将 `accept-encoding` 加入剥离清单：

```python
if lower in ("host", "content-length", "transfer-encoding",
             "authorization", "x-api-key", "accept-encoding"):
    continue
```

剥离后，`httpx` 自行决定是否添加 `Accept-Encoding` 并负责自动解压，Proxy 的 `aiter_lines()` 始终拿到明文 SSE 数据。

此外 `_handle_stream` 保留 `Cache-Control: no-transform` + `X-Accel-Buffering: no` 作为防御性措施，防止中间代理（ALB/Nginx）对 Proxy 返回给客户端的响应流做二次压缩。

**教训**：

- HTTP 代理转发请求时，`Accept-Encoding` 属于 hop-by-hop 语义的头，**必须剥离**，由代理自身与上游协商压缩
- `httpx` 的自动解压仅在 `Accept-Encoding` 由 httpx 自身添加时生效，显式传入时视为"调用方自行处理"
- `curl --compressed` 会自动解压，容易掩盖压缩问题；排查时应同时用 `curl -H "Accept-Encoding: gzip"` 不带 `--compressed` 来暴露原始响应
- LLM Provider 的压缩行为可能随时变化，代理层必须主动防御而非依赖上游不压缩

---

## 十二、Inst 集群基础设施搭建

每个 inst 集群（用于运行 OpenClaw 实例）需要以下基础设施。

### 12.1 安装 nginx-ingress-controller

复用 `nodeskclaw-artifacts/ingress-controller/deploy.yaml`：

```bash
kubectl --context <inst-cluster> apply -f nodeskclaw-artifacts/ingress-controller/deploy.yaml
```

同时复制镜像拉取 Secret：

```bash
kubectl --context <infra-cluster> get secret cr-pull-secret -n nodeskclaw-system -o json \
  | python3 -c "import sys,json; s=json.load(sys.stdin); s['metadata']={'name':s['metadata']['name'],'namespace':'nodeskclaw-system'}; json.dump(s,sys.stdout)" \
  | kubectl --context <inst-cluster> apply -n nodeskclaw-system -f -
```

### 12.2 创建 ALB + 通配符 Ingress

在火山云 VKE 控制台：

1. 为 inst 集群创建 ALB 实例（HTTP 监听 80 端口，TLS 在 infra ALB 终止）
2. 创建绑定该 ALB 的 IngressClass
3. 创建通配符 ALB Ingress：`*.nodeskai.com` -> `nodeskclaw-system-controller:80`

### 12.3 记录 proxy_endpoint

获取 ALB hostname 并在管理后台更新集群的 `proxy_endpoint` 字段。后端会自动在 infra 集群创建对应的 ExternalName Service。

### 12.4 RBAC（infra 集群）

后端 ServiceAccount 需要 `nodeskclaw-gateway-proxy` Role 权限来管理 `nodeskclaw-system` 命名空间的 proxy Ingress 和 ExternalName Service。

---

## 十三、CE/EE 部署差异

NoDeskClaw 的 K8s 部署行为通过 `DeploymentAdapter` 抽象层在 CE 和 EE 之间分化。

### CE 部署模式

- **单集群**：所有实例部署到同一个 K8s 集群
- **Namespace 命名**：`nodeskclaw-default-{slug}`，不含组织前缀
- **无跨集群代理**：Ingress 直接指向本集群 Controller
- **无组织级网络隔离**：NetworkPolicy 不设 org_id 标签
- **无配额检查**：部署不受套餐限制

### EE 部署模式

- **多集群**：支持多个 K8s 集群，组织可配置专属集群
- **Namespace 命名**：`nodeskclaw-{org_slug}-{slug}`，多租户隔离
- **跨集群代理**：通过网关集群的 ExternalName Service + Proxy Ingress 路由到实例集群
- **组织级网络隔离**：Namespace 标签含 `nodeskclaw.io/org-id`，NetworkPolicy 按组织隔离
- **套餐配额检查**：部署前通过 QuotaChecker 校验组织配额

### 对照表

| 维度 | CE (BasicK8sAdapter) | EE (FullK8sAdapter) |
|------|---------------------|---------------------|
| 集群数量 | 单集群 | 多集群 |
| Namespace | `nodeskclaw-default-{slug}` | `nodeskclaw-{org_slug}-{slug}` |
| 跨集群代理 | 无 | ExternalName + Proxy Ingress |
| NetworkPolicy org_id | 无 | 按组织隔离 |
| 配额检查 | 无 | PlanBasedQuotaChecker |
| TLS 处理 | 直接使用集群 TLS Secret | 网关集群终止 TLS |
