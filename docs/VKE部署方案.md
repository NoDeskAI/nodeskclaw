# ClawBuddy - 火山云 VKE 部署方案

> 解决核心问题：ClawBuddy 怎么往火山云 VKE 集群里创建 OpenClaw 的 K8s 资源

---

## 一、部署到 K8s 的两件事

ClawBuddy 要部署两类东西到 VKE：

```
火山云 VKE 集群
│
├── 1. ClawBuddy 自身（一次性人工部署）
│     Deployment + Service + Ingress
│     管理后台，部署一次就行
│
└── 2. OpenClaw 实例（通过 ClawBuddy 页面一键部署，可以 N 个）
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
| **公网 KubeConfig** | 通过公网访问 API Server | ClawBuddy 部署在 VKE 集群外部 |
| **内网 KubeConfig** | 通过 VPC 内网访问 | ClawBuddy 部署在同一 VKE 集群或同 VPC |

**推荐**：ClawBuddy 自身部署在 VKE 集群内，用 **ServiceAccount + RBAC** 访问本集群，不需要 KubeConfig 文件。管理其他集群时才需要导入 KubeConfig。

### 2.2 ClawBuddy 内访问本集群

ClawBuddy 跑在 VKE 里时，用 Pod 自带的 ServiceAccount Token 就行：

```python
# kubernetes-asyncio 支持自动检测 in-cluster 环境
from kubernetes_asyncio import config

# 方式 1: Pod 内自动加载 ServiceAccount Token
await config.load_incluster_config()

# 方式 2: 外部开发环境，加载本地 kubeconfig
await config.load_kube_config()
```

需要给 ClawBuddy 的 ServiceAccount 足够权限（见第六节 RBAC）。

### 2.3 ClawBuddy 内访问其他集群

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
- ClawBuddy 后台 `ClusterHealthChecker` 每 60 秒巡检所有集群
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
├── Namespace: clawbuddy              ← ClawBuddy 自身
│
├── Namespace: oc-prod-main           ← OpenClaw 生产主力
│   ├── ResourceQuota (4c / 8Gi)
│   ├── LimitRange (单容器上限 2c/4Gi)
│   ├── NetworkPolicy (仅允许同 NS + ClawBuddy + Ingress)
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

> 用户在部署表单里只填 **实例名**（如 `prod-main`），Namespace 由 ClawBuddy 自动生成 `oc-prod-main`。

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

| 档位 | CPU 配额 | 内存配额 | 最大 Pod 数 | 适用场景 |
|------|---------|---------|-----------|---------|
| 小型 | 2c | 4Gi | 10 | 开发/测试 |
| 中型 | 4c | 8Gi | 20 | 预发/小规模生产 |
| 大型 | 8c | 16Gi | 50 | 生产主力 |
| 自定义 | 用户填写 | 用户填写 | 用户填写 | 特殊需求 |

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
    - 允许从 clawbuddy Namespace 访问（管理：健康检查、日志）
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
                # ClawBuddy 管理访问
                {"from": [{"namespaceSelector": {
                    "matchLabels": {"app.kubernetes.io/name": "clawbuddy"}
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
clawbuddy 的 Pod     ──✓──→  任何 oc-* 的 Pod           (允许，管理需要)
ingress-nginx        ──✓──→  任何 oc-* 的 Pod           (允许，流量入口)
```

> VKE 默认支持 NetworkPolicy（基于 Calico），不需要额外安装组件。

### 3.6 Namespace 创建编排

部署时 ClawBuddy 自动创建 Namespace 并配置隔离：

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
                "app.kubernetes.io/managed-by": "clawbuddy",
                "clawbuddy.io/type": "openclaw-instance",
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
│   └── 仅允许同 NS + ClawBuddy + Ingress
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
│           ├── image: cr-cn-beijing.volces.com/clawbuddy/openclaw:v1.0.0
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
| `/root/.openclaw/workspace/` | 工作区（SKILL、项目文件） | 是 |
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
    """统一标签，所有 ClawBuddy 管理的资源都带这组标签"""
    return {
        "app.kubernetes.io/name": "openclaw",
        "app.kubernetes.io/instance": instance_name,
        "app.kubernetes.io/version": image_tag,
        "app.kubernetes.io/managed-by": "clawbuddy",
        "clawbuddy.io/instance-id": instance_id,
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
                    annotations={"clawbuddy.io/restartedAt": ""},
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

## 五、ClawBuddy 怎么创建 K8s 资源

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

    # 5. PVC — 默认不删除，需用户二次确认
    # if delete_pvc:
    #     await k8s.core.delete_namespaced_persistent_volume_claim(
    #         name=f"{name}-root-data", namespace=namespace
    #     )

    # 6. Namespace — 删除 Namespace 会级联删除所有资源（PVC、ResourceQuota 等）
    # 仅在用户确认后执行，默认保留（PVC 中有用户数据）
    # if delete_namespace:
    #     await k8s.core.delete_namespace(name=namespace)
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

## 六、RBAC — ClawBuddy 需要的 K8s 权限

ClawBuddy 部署在 VKE 集群内时，需要 ServiceAccount 有足够权限操作其他 Namespace 的资源：

```yaml
# deploy/k8s/rbac.yaml

# 1. ServiceAccount
apiVersion: v1
kind: ServiceAccount
metadata:
  name: clawbuddy-sa
  namespace: clawbuddy

---
# 2. ClusterRole（集群级别权限）
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: clawbuddy-role
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
  name: clawbuddy-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: clawbuddy-role
subjects:
  - kind: ServiceAccount
    name: clawbuddy-sa
    namespace: clawbuddy
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

ClawBuddy 的 `.env` 需要配置 VKE 相关参数：

```bash
# 火山云 VKE 专用
CLAWBUDDY_VKE_SUBNET_ID=subnet-abc123          # CLB 子网 ID
CLAWBUDDY_VKE_DEFAULT_ADDRESS_TYPE=PUBLIC       # 默认 CLB 类型
CLAWBUDDY_VKE_INGRESS_CLASS=nginx               # Ingress Class

# 镜像仓库（火山云 CR）
CLAWBUDDY_IMAGE_REGISTRY=cr-xxx.volcengine.com/openclaw/openclaw
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
│   └─ 创建 NetworkPolicy (同 NS + ClawBuddy + Ingress 放行)   │
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

## 九、ClawBuddy 自身的 VKE 部署

### 9.1 一次性手工部署

```bash
# 1. 连接 VKE 集群
export KUBECONFIG=~/.kube/vke-prod.yaml

# 2. 创建命名空间
kubectl create namespace clawbuddy

# 3. 创建 Secret（敏感配置）
kubectl create secret generic clawbuddy-secret \
  --namespace clawbuddy \
  --from-literal=JWT_SECRET=your-jwt-secret \
  --from-literal=ENCRYPTION_KEY=your-aes-256-key-hex \
  --from-literal=FEISHU_APP_SECRET=your-feishu-secret

# 4. 创建 ConfigMap（非敏感配置）
kubectl create configmap clawbuddy-config \
  --namespace clawbuddy \
  --from-literal=FEISHU_APP_ID=cli_xxxx \
  --from-literal=FEISHU_REDIRECT_URI=https://clawbuddy.example.com/api/v1/auth/feishu/callback \
  --from-literal=VKE_SUBNET_ID=subnet-xxx \
  --from-literal=IMAGE_REGISTRY=cr-xxx.volcengine.com/openclaw/openclaw

# 5. 部署 RBAC
kubectl apply -f deploy/k8s/rbac.yaml

# 6. 部署应用
kubectl apply -f deploy/k8s/deployment.yaml
kubectl apply -f deploy/k8s/service.yaml
kubectl apply -f deploy/k8s/ingress.yaml

# 7. 验证
kubectl -n clawbuddy get pods
kubectl -n clawbuddy get svc
kubectl -n clawbuddy get ingress
```

### 9.2 ClawBuddy 自身的 Deployment YAML

```yaml
# deploy/k8s/deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: clawbuddy
  namespace: clawbuddy
spec:
  replicas: 2
  selector:
    matchLabels:
      app: clawbuddy
  template:
    metadata:
      labels:
        app: clawbuddy
    spec:
      serviceAccountName: clawbuddy-sa    # 使用有权限的 SA
      containers:
        - name: clawbuddy
          image: cr-xxx.volcengine.com/clawbuddy/clawbuddy:v0.1.0
          ports:
            - containerPort: 8000
          envFrom:
            - secretRef:
                name: clawbuddy-secret
            - configMapRef:
                name: clawbuddy-config
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
            claimName: clawbuddy-data
```
