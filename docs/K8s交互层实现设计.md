# ClawBuddy - K8s 交互层实现设计

> 补充后端架构设计，详解后端与 K8s 的全部交互逻辑

---

## 一、核心问题

后端需要跟 K8s 交互的场景有 **6 类**：

```
后端 ←→ K8s 的 6 类交互
│
├── 1. 集群连接      KubeConfig 加载 → 建立连接 → 验证可用性
├── 2. 资源查询      查 Node/Pod/Deployment/Service/Ingress 状态
├── 3. 资源变更      创建/修改/删除 ConfigMap、Deployment、Service、Ingress、
│                    ResourceQuota、LimitRange、NetworkPolicy，扩缩容、重启
├── 4. 日志读取      一次性拉取历史日志 + 实时流式日志
├── 5. 事件监听      Watch API 长连接，实时感知 Pod 状态变化和 K8s Events
└── 6. 指标采集      从 Metrics Server 拉取 CPU/内存使用数据
```

> **设计决策**：不使用 Helm Chart，所有 K8s 资源通过 `kubernetes-asyncio` 直接创建/更新/删除。
> 好处：零外部依赖、更细粒度控制、调试友好。

---

## 二、库选型

| 库 | 类型 | 适配 FastAPI | 选择 |
|----|------|-------------|------|
| `kubernetes` | 同步 | 需要 `asyncio.to_thread()` 包装，Watch/Stream 不友好 | ❌ |
| **`kubernetes-asyncio`** | 原生 async | 原生 `await`，Watch/Stream 天然支持 | ✅ |

---

## 三、整体交互架构

```
┌──────────────────────────────────────────────────────────────────┐
│  Service Layer                                                    │
│  (DeployService, InstanceService, LogService, MonitorService)    │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│  K8sClientManager (连接池 + Token 检测 + 健康检查)                │
│                                                                  │
│  cluster_id → ClientEntry { ApiClient, KubeConfigMeta, healthy } │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                                ▼
┌──────────────────────────────────────────────────────────────────┐
│  K8sClient (单集群操作封装)                                       │
│                                                                  │
│  CoreV1Api          ← Pod, Service, Namespace, Node, ConfigMap   │
│  AppsV1Api          ← Deployment, ReplicaSet                     │
│  NetworkingV1Api    ← Ingress, NetworkPolicy                     │
│  CustomObjectsApi   ← Metrics (metrics.k8s.io)                   │
└───────────────────────────────┬──────────────────────────────────┘
                                │
                                ▼
                    K8s API Server (via KubeConfig)
```

---

## 四、KubeConfig 管理

### 4.1 存储与加密

KubeConfig 是访问集群的钥匙，**必须加密存储**，且需要处理 **Token 过期** 问题。

```
用户上传 KubeConfig 明文
        │
        ▼
┌─────────────────────────────────────────────────┐
│  后端收到明文                                      │
│  1. yaml.safe_load 校验格式                        │
│  2. 检测认证方式:                                  │
│     ├── client-certificate → 证书模式 (长期有效)    │
│     ├── token              → Token 模式 (会过期!)   │
│     └── exec / authProvider → 外部命令模式          │
│  3. 如果是 Token 模式，解析 JWT exp → 记录过期时间  │
│  4. 测试连接（临时加载 → 查版本）                   │
│  5. AES-256-GCM 加密                               │
│  6. 存入 DB (kubeconfig_enc + auth_type + expires) │
└─────────────────────────────────────────────────┘
        │
        ▼  使用时
┌─────────────────────────────────────────────────┐
│  1. 从 DB 读取密文                                │
│  2. AES 解密 → 得到明文                           │
│  3. 检查 Token 是否过期（Token 模式）              │
│     ├── 已过期 → 抛异常，通知用户重新上传          │
│     └── 即将过期 (< 6h) → 广播告警               │
│  4. kubernetes-asyncio 内存加载（不落盘）          │
│  5. 健康检查 → 不健康则重建 client                 │
└─────────────────────────────────────────────────┘
```

VKE 的 Token 默认 **48 小时**过期。证书模式有效期通常 1 年。推荐在 VKE 控制台选择证书模式。

### 4.2 核心模块

| 模块 | 文件 | 职责 |
|------|------|------|
| `KubeConfigCrypto` | `app/utils/crypto.py` | AES-256-GCM 加解密，nonce + ciphertext 拼接后 Base64 存储 |
| `load_client_from_kubeconfig_str()` | `app/utils/kubeconfig_parser.py` | 从明文字符串内存加载 ApiClient（不写临时文件） |
| `parse_kubeconfig_meta()` | `app/utils/kubeconfig_parser.py` | 解析 KubeConfig 元信息：认证方式、Token 过期时间、API Server 地址 |
| `check_token_status()` | `app/utils/kubeconfig_parser.py` | 返回 Token 状态：`ok` / `expiring_soon` / `expired` / `not_token` |

加载原理：`kubernetes-asyncio` 的 `KubeConfigLoader` 支持从 dict 加载，无需文件 I/O。

### 4.3 Token 过期策略

| Token 状态 | 判定条件 | 处理 |
|------------|----------|------|
| `expired` | 已超过 JWT `exp` 时间 | 阻止操作，标记集群 `token_expired`，前端轮询 `/clusters/:id/health` 时展示红色告警 |
| `expiring_soon` | 距过期不足 6 小时 | 允许操作，SSE 推送 warning 提醒用户更新 |
| `ok` | 有效期充足 | 正常使用 |
| `not_token` | 证书模式 / exec 模式 | 无需检查过期 |

### 4.4 KubeConfigMeta 数据结构

| 字段 | 类型 | 说明 |
|------|------|------|
| `auth_type` | str | `"certificate"` / `"token"` / `"exec"` / `"unknown"` |
| `server` | str | API Server 地址 |
| `token_expires_at` | datetime / None | Token JWT exp 时间（仅 token 模式） |
| `cluster_name` | str | context 中的 cluster name |

---

## 五、K8sClientManager — 连接池

管理多集群的 K8s API Client，按 `cluster_id` 缓存。

### 5.1 增强能力

1. **Token 过期检测** — 每次获取 client 前检查 Token 状态
2. **连接健康检查** — 调用 `GET /version` 探活，超时 5 秒视为不健康
3. **自动重建** — 不健康的 client 自动关闭并重新创建
4. **元信息缓存** — 缓存 `KubeConfigMeta` 避免重复解析

### 5.2 缓存条目结构

每个集群缓存一个 `ClientEntry`：

| 字段 | 类型 | 说明 |
|------|------|------|
| `api_client` | `ApiClient` | kubernetes-asyncio 客户端实例 |
| `meta` | `KubeConfigMeta` | 认证元信息（含过期时间） |
| `created_at` | datetime | 创建时间 |
| `last_health_check` | datetime / None | 最近健康检查时间 |
| `healthy` | bool | 当前是否健康 |

### 5.3 接口设计

```python
class K8sClientManager:
    async def get_or_create(cluster_id, kubeconfig_enc, *, check_health=True) -> ApiClient: ...
    async def rebuild(cluster_id, kubeconfig_enc) -> ApiClient: ...
    async def remove(cluster_id): ...
    async def close_all(): ...
    async def init_from_db(db_session): ...
    def get_meta(cluster_id) -> KubeConfigMeta | None: ...
    def get_all_status() -> dict[str, dict]: ...

class TokenExpiredError(Exception):
    cluster_id: str
    expired_at: datetime | None
```

### 5.4 get_or_create 流程

```
get_or_create(cluster_id, kubeconfig_enc)
  │
  ├─ 不存在 → 解密 → 解析 meta → 创建 ApiClient → 缓存
  │
  ├─ Token 已过期 → 抛出 TokenExpiredError
  ├─ Token 即将过期 → 记录 warning（调用方推送告警）
  │
  ├─ check_health=True:
  │   ├─ GET /version 成功 → 返回 client
  │   └─ 失败 → 关闭旧 client → 重建新 client
  │
  └─ 返回 ApiClient
```

### 5.5 启动初始化

`init_from_db()` 在应用启动时从 DB 加载所有集群：
- 连接成功 → `health_status = "healthy"`
- Token 过期 → `health_status = "token_expired"`
- 连接失败 → `health_status = "unhealthy"`

---

## 六、K8sClient — 单集群操作封装

把 kubernetes-asyncio 的原始 API 封装成业务友好的方法。

### 6.1 内部 API 客户端

| API 客户端 | 管理的资源 |
|-----------|-----------|
| `CoreV1Api` | Pod, Service, Namespace, Node, Event, ConfigMap, PVC |
| `AppsV1Api` | Deployment, ReplicaSet |
| `NetworkingV1Api` | Ingress, NetworkPolicy |
| `VersionApi` | 集群版本 |
| `CustomObjectsApi` | Metrics Server (metrics.k8s.io) |

### 6.2 方法清单

**集群级**

| 方法 | K8s API | 说明 |
|------|---------|------|
| `test_connection()` | `VersionApi.get_code()` | 测试连接，返回版本信息 |
| `get_cluster_overview()` | `list_node()` + `list_pod_for_all_namespaces()` | 聚合节点数、CPU/内存总量和已用量 |

**Namespace**

| 方法 | K8s API | 说明 |
|------|---------|------|
| `list_namespaces()` | `list_namespace()` | 列出所有 NS 名称 |
| `ensure_namespace(name)` | `read/create_namespace()` | 不存在则创建 |
| `ensure_namespace_with_isolation(ns, quota_cpu, quota_mem, max_pods, storage_quota)` | 见下方隔离策略 | 创建 NS + 三层隔离 |

**Namespace 隔离策略**（`ensure_namespace_with_isolation` 内部步骤）：

```
ensure_namespace_with_isolation("oc-prod-main", "4", "8Gi", 20, "200Gi")
  │
  ├─ 1. 创建 Namespace（带 managed-by 标签）
  │
  ├─ 2. 创建 ResourceQuota "openclaw-quota"
  │     requests.cpu=4, requests.memory=8Gi, pods=20
  │     requests.storage=200Gi, persistentvolumeclaims=5
  │     services.loadbalancers=1
  │
  ├─ 3. 创建 LimitRange "openclaw-limits"
  │     Container default: cpu=1, memory=1Gi
  │     Container defaultRequest: cpu=0.5, memory=512Mi
  │     Container max: cpu=2, memory=4Gi
  │
  └─ 4. 创建 NetworkPolicy "openclaw-isolation"
        入站：仅允许同 NS + ClawBuddy NS + Ingress Controller
        出站：不限制（OpenClaw 需要访问外部 API）
```

**Deployment**

| 方法 | K8s API | 说明 |
|------|---------|------|
| `get_deployment(ns, name)` | `read_namespaced_deployment()` | 获取 Deployment |
| `get_deployment_status(ns, name)` | `read_namespaced_deployment_status()` | 实时状态：replicas / ready / conditions |
| `scale_deployment(ns, name, replicas)` | `patch_namespaced_deployment_scale()` | 扩缩容 |
| `restart_deployment(ns, name)` | `patch_namespaced_deployment()` | 修改 annotation 触发滚动重启 |
| `update_deployment_image(ns, name, image)` | `patch_namespaced_deployment()` | 更新镜像版本触发 rolling update |

**Pod**

| 方法 | K8s API | 说明 |
|------|---------|------|
| `list_pods(ns, label_selector)` | `list_namespaced_pod()` | Pod 列表（含重启次数、容器状态） |
| `get_pod_logs(ns, pod, container, tail_lines)` | `read_namespaced_pod_log()` | 一次性历史日志 |
| `stream_pod_logs(ns, pod, container, tail_lines)` | `read_namespaced_pod_log(follow=True)` | 实时流式日志（AsyncIterator） |

日志流实现关键：`follow=True` + `_preload_content=False` 返回 `aiohttp.ClientResponse`，逐行异步迭代。

**Watch**

| 方法 | K8s API | 说明 |
|------|---------|------|
| `watch_pods(ns, label_selector)` | `Watch().stream(list_namespaced_pod)` | 监听 Pod 状态变更（ADDED/MODIFIED/DELETED） |
| `watch_events(ns)` | `Watch().stream(list_namespaced_event)` | 监听 K8s Events（Warning = 异常） |

Watch 是长连接。`timeout_seconds=0` 表示持续监听直到连接断开。

**Metrics**

| 方法 | K8s API | 说明 |
|------|---------|------|
| `get_pod_metrics(ns, pod)` | `CustomObjectsApi.get_namespaced_custom_object()` | 单 Pod CPU/内存使用量 |
| `list_pod_metrics(ns)` | `CustomObjectsApi.list_namespaced_custom_object()` | NS 下所有 Pod 指标 |

Metrics 通过 K8s aggregated API：`/apis/metrics.k8s.io/v1beta1/namespaces/{ns}/pods`。

**Service / Ingress**

| 方法 | K8s API | 说明 |
|------|---------|------|
| `get_service(ns, name)` | `read_namespaced_service()` | Service 信息（含 external IP） |
| `get_ingress(ns, name)` | `read_namespaced_ingress()` | Ingress hosts / class |

**内部辅助方法**

| 方法 | 说明 |
|------|------|
| `_create_or_skip(create_fn)` | 创建资源，HTTP 409 则跳过（幂等） |
| `_apply(create_fn, patch_fn, ns, name, body)` | 创建或更新资源（幂等） |

---

## 七、K8sWatcher — 后台常驻监听

Watcher 是实时推送系统的引擎，后台持续运行，监听 K8s 资源变化，通过 Broadcaster 推给前端。

### 7.1 生命周期

- 应用启动时由 lifespan 创建并启动
- 每 10 秒扫描 DB，为每个活跃实例维护一个 watch task
- 实例新增 → 启动 watch task；实例删除 → cancel task
- 应用关闭时 cancel 所有 task

### 7.2 单实例监听流程

```
_watch_instance("openclaw-prod-1"):
  │
  ├─ K8sClient.watch_pods(namespace, label_selector)
  │   └─ Watch API 长连接
  │
  ├─ 收到 event → 聚合所有 Pod 状态 → _compute_instance_status()
  │   ├─ 全部 Running → "running"
  │   ├─ 存在 CrashLoopBackOff / Failed → "failed"
  │   └─ 其他 → "pending"
  │
  ├─ 状态变更 → 更新 DB + EventBus.publish → SSE → 前端
  │
  └─ 连接断开 → 指数退避重连（1s → 2s → 4s → ... → 最大 30s）
```

---

## 八、ResourceBuilder — K8s 资源构建

> 详细资源构建逻辑参考 `docs/VKE部署方案.md` 第四、五节。

### 8.1 核心接口

```python
# app/services/resource_builder.py

def build_labels(instance_name, instance_id, image_tag) -> dict: ...
def build_configmap(name, namespace, env_vars, labels) -> V1ConfigMap: ...
def build_pvc(name, namespace, storage_size, storage_class, labels) -> V1PersistentVolumeClaim: ...
def build_deployment(name, namespace, image, replicas, ..., advanced=None) -> V1Deployment: ...
def build_service(name, namespace, service_type, ...) -> V1Service: ...
def build_ingress(name, namespace, host, labels) -> V1Ingress: ...

async def create_openclaw_instance(k8s, req, instance_id): ...
async def update_openclaw_instance(k8s, req, instance_id): ...
async def delete_openclaw_instance(k8s, namespace, name): ...
async def rollback_openclaw_instance(k8s, instance, target_record): ...
```

所有资源统一标签：`app.kubernetes.io/managed-by: clawbuddy`，便于识别和批量管理。

### 8.2 默认 PVC + Init Container 设计

每个 OpenClaw 实例标配一个 PVC 挂载到 `/root`，持久化整个 home 目录。

**为什么挂 `/root`**：OpenClaw 的关键数据都在 `/root` 下：

| 路径 | 内容 |
|------|------|
| `/usr/local/bin/openclaw` | OpenClaw 程序（镜像层，非 PVC） |
| `/root/.openclaw/` | 用户数据：配置、会话、凭证、插件、工作区、技能、记忆 |
| `/root/.bashrc` 等 | Shell 配置 |

**Init Container 逻辑**：

```
Init Container (镜像同主容器，PVC 挂载到 /init-data)
  │
  ├─ 检查 /init-data/.openclaw-version 是否存在
  │
  ├─ 不存在（首次部署）
  │   ├─ cp -a /root/.openclaw /init-data/.openclaw
  │   ├─ cp /root/.openclaw-version /init-data/.openclaw-version
  │   └─ cp /root/.bashrc /root/.profile /init-data/
  │
  └─ 已存在（非首次）
      ├─ 对比版本号
      ├─ 版本相同 → 跳过
      └─ 版本不同 → 轻量升级：
          ├─ 更新 .openclaw-version
          ├─ 合并内置插件到 .openclaw/extensions/
          └─ 更新 .bashrc / .profile
```

**PVC 命名**：`{instance-name}-root-data`，如 `prod-main-root-data`。

**删除保护**：实例删除时 PVC **默认不删除**，需用户二次确认后手动清理。

---

## 九、ClusterHealthChecker — 后台健康巡检

定时任务，每 **60 秒** 检查所有集群的连接健康和 Token 有效性。

### 9.1 职责

1. 对所有集群做 `GET /version` 探活
2. 检测 Token 过期状态
3. 更新 DB 中的 `health_status` / `last_health_check`
4. 状态变更写入 DB，前端通过轮询 `GET /clusters/:id/health` 获取最新状态

### 9.2 检查流程

```
_check_one(cluster):
  │
  ├─ 1) Token 检测
  │   ├─ expired → 标记 token_expired → return
  │   └─ expiring_soon → 标记 token_expiring
  │
  ├─ 2) 连接探活（通过 K8sClientManager.get_or_create）
  │   ├─ 成功 → healthy
  │   ├─ TokenExpiredError → token_expired
  │   └─ 其他异常 → unhealthy
  │
  └─ 3) 状态变更 → 写入 DB（前端轮询 /clusters/:id/health 时读取）
```

### 9.3 启动集成

在 `app/main.py` 的 lifespan 中启动和停止，与 K8sClientManager、SSEEventBus 协同工作。

---

## 十、高级实例配置（AdvancedConfig）

部署完成后，用户可能需要：
- **挂载额外 Volume**（配置文件、持久化数据）
- **添加 Sidecar 容器**（日志收集、代理、监控）
- **添加 Init 容器**（数据迁移、依赖检查）
- **打通跨实例网络**（允许实例 A 访问实例 B）

通过 `Instance.advanced_config` JSON 字段存储，按需注入到 K8s 资源中。

### 10.1 配置 Schema

**AdvancedConfig**（顶层）

| 字段 | 类型 | 说明 |
|------|------|------|
| `volumes` | `VolumeConfig[]` | Volume 挂载 |
| `sidecars` | `SidecarConfig[]` | Sidecar 容器 |
| `init_containers` | `InitContainerConfig[]` | Init 容器 |
| `network_allow` | `NetworkAllowConfig[]` | 跨实例网络放行 |
| `annotations` | `dict[str, str]` | 自定义注解 |
| `labels` | `dict[str, str]` | 自定义标签 |

**VolumeConfig**

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` | str | Volume 名 |
| `type` | `"emptyDir" / "pvc" / "configMap" / "secret"` | 类型 |
| `mount_path` | str | 容器内挂载路径 |
| `sub_path` | str? | 子路径 |
| `read_only` | bool | 是否只读 |
| `storage_size` | str? | PVC 大小，如 `"10Gi"` |
| `storage_class` | str? | StorageClass，如 `"ebs-ssd"` |
| `ref_name` | str? | ConfigMap / Secret 名 |

**SidecarConfig**

| 字段 | 类型 | 说明 |
|------|------|------|
| `name` / `image` | str | 容器名和镜像 |
| `command` / `args` | list[str]? | 启动命令 |
| `env` | dict | 环境变量 |
| `ports` | list[int] | 暴露端口 |
| `cpu_request/limit`, `mem_request/limit` | str | 资源配额 |
| `volume_mounts` | list[dict] | Volume 挂载 |

**InitContainerConfig** — 与 Sidecar 类似，无 ports 和资源限制。

**NetworkAllowConfig**

| 字段 | 类型 | 说明 |
|------|------|------|
| `target_namespace` | str | 目标实例的 namespace |
| `target_instance` | str | 目标实例名（备注用） |
| `port` | int? | 允许的端口（None = 所有） |
| `protocol` | `"TCP" / "UDP"` | 协议 |
| `direction` | `"ingress" / "egress" / "both"` | 方向 |

### 10.2 配置注入流程

```
应用高级配置 (POST /instances/:id/advanced-config/apply)
  │
  ├─ 1. 从 DB 读取 Instance.advanced_config
  │
  ├─ 2. Volume 处理
  │   ├─ pvc 类型 → ensure_pvcs() 自动创建 PVC（幂等）
  │   └─ emptyDir / configMap / secret → 直接注入 PodSpec
  │
  ├─ 3. 构建新 Deployment
  │   ├─ 主容器 + volume_mounts
  │   ├─ Sidecar 容器列表 → PodSpec.containers
  │   ├─ Init 容器列表 → PodSpec.initContainers
  │   └─ 自定义 labels / annotations → PodTemplate metadata
  │
  ├─ 4. replace_namespaced_deployment → 触发滚动更新
  │
  └─ 5. 网络放行
      └─ 为每条 NetworkAllowConfig 创建独立 NetworkPolicy
          命名: {instance}-allow-{target_namespace}
          标签: clawbuddy/policy-type: cross-instance
```

### 10.3 操作矩阵

| 操作 | K8s API | 说明 |
|------|---------|------|
| 部署实例 | `create_namespaced_*` | ConfigMap + Deployment + Service + Ingress |
| 重启实例 | `patch_namespaced_deployment` | 修改 annotation 触发滚动重启 |
| 扩缩容 | `patch_namespaced_deployment` | 修改 `spec.replicas` |
| 更新配置 | `replace_namespaced_config_map` + `replace_namespaced_secret` + restart | 更新 ConfigMap/Secret（含 `OPENCLAW_FORCE_RECONFIG=true`）→ 重启 Pod → entrypoint 从模板重新生成 openclaw.json → 后端改回 `FORCE_RECONFIG=false` |
| 挂载 Volume | `ensure_pvcs` + `replace_deployment` | 创建 PVC → 更新 volumes |
| 添加 Sidecar | `replace_namespaced_deployment` | 更新 containers 列表 |
| 添加 Init 容器 | `replace_namespaced_deployment` | 更新 initContainers |
| 打通网络 | `create/replace_network_policy` | 追加 NetworkPolicy 放行规则 |
| 回滚 | `replace_namespaced_deployment` | 恢复历史 PodTemplateSpec |
| 删除实例 | `delete_namespaced_*` + `delete_namespace` | 清理所有资源 |

---

## 十一、调用链路汇总

### 场景 1：一键部署

```
前端 POST /api/v1/deploy
  │
  ├─ API Layer → 参数校验 (DeployRequest)
  │
  ├─ DeployService.create_deploy()
  │   ├─ 写 Instance + DeployRecord 到 DB
  │   └─ asyncio.create_task(_do_deploy) → 立即返回 deploy_id
  │
  └─ 前端连接 SSE GET /stream/deploy/{deploy_id}/progress
      │
      _do_deploy (后台异步):
      │
      ├─ K8sClient.ensure_namespace_with_isolation("oc-prod-main")
      │   ├─ Namespace + 管理标签
      │   ├─ ResourceQuota (CPU/内存/Pod/存储上限)
      │   ├─ LimitRange (容器默认 limits)
      │   └─ NetworkPolicy (网络隔离)
      │
      ├─ create_openclaw_instance(k8s, request, instance_id)
      │   ├─ PVC {name}-root-data (100Gi, 挂载 /root)
      │   ├─ ConfigMap (环境变量)
      │   ├─ Deployment (含 Init Container + 主容器)
      │   │   ├─ Init Container: 首次部署时 cp -a /root/* → PVC
      │   │   └─ Main Container: PVC 挂载到 /root
      │   ├─ Service → Ingress
      │   └─ 如有 advanced_config → 额外 PVC + Sidecar + Init 容器
      │
      ├─ 轮询 get_deployment_status()
      │   └─ EventBus.publish 进度 → SSE → 前端进度条
      │
      └─ 完成 → 更新 DB → broadcast success
```

### 场景 2：实时日志

```
前端连接 SSE GET /stream/instances/:id/logs?pod=xxx&container=openclaw
  │
  ├─ 校验 JWT → 获取 cluster_id
  │
  ├─ K8sClient.stream_pod_logs(follow=True, _preload_content=False)
  │   └─ 返回 aiohttp.ClientResponse (chunked stream)
  │
  └─ async for line in stream → yield SSE event
```

### 场景 3：实例状态实时推送

```
K8sWatcher (后台常驻)
  │
  ├─ 扫描 DB → 为每个活跃实例创建 watch task
  │
  └─ watch_instance:
        K8sClient.watch_pods(namespace, label_selector)
        │
        async for event in watch:
        ├─ MODIFIED, phase Failed → _compute_instance_status → "failed"
        │   ├─ 更新 DB
        │   └─ EventBus.publish → SSE → 前端 Dashboard 卡片变红
        │
        └─ 连接断开 → 指数退避重连
```

### 场景 4：高级配置应用

```
前端 PUT /instances/:id/advanced-config  → 保存到 DB
前端 POST /instances/:id/advanced-config/apply
  │
  ├─ 读取 advanced_config
  ├─ ensure_pvcs (pvc 类型 Volume)
  ├─ build_deployment (注入 volumes/sidecars/init_containers)
  ├─ replace_namespaced_deployment → 滚动更新
  └─ update_network_allow (跨实例放行)
```

---

## 十二、依赖清单

```
kubernetes-asyncio==34.*     # 异步 K8s 客户端
pyyaml==6.*                  # KubeConfig YAML 解析
cryptography==44.*           # AES 加密 KubeConfig
```

---

## 十三、辅助工具函数

放在 `app/utils/k8s_helpers.py`，包括：

| 函数 | 说明 | 示例 |
|------|------|------|
| `_parse_cpu(value)` | K8s CPU 单位 → float 核数 | `"500m"` → `0.5` |
| `_parse_memory(value)` | K8s 内存单位 → bytes | `"1Gi"` → `1073741824` |
| `_format_memory(bytes)` | bytes → 人类可读 | `1073741824` → `"1.0Gi"` |
| `_extract_container_state(state)` | V1ContainerState → 状态字符串 | → `"running"` / `"waiting"` |
| `_extract_container_reason(state)` | 提取异常原因 | → `"CrashLoopBackOff"` |
