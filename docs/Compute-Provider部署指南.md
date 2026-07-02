# Compute Provider 部署指南

> 面向管理员：如何在 NoDeskClaw 中配置计算集群，让 AI 实例有地方跑。

---

## 一、概念总览

NoDeskClaw 通过 **Compute Provider**（计算提供方）抽象来管理 AI 实例的运行环境。一个"集群"本质上就是一个计算提供方的实例，实例部署当前支持 Kubernetes：

| Compute Provider | 适用场景 | 凭证要求 | 实例运行方式 |
|---|---|---|---|
| `k8s` | 生产、多实例 | KubeConfig | Deployment + Service + Ingress |

> `process`（本地进程）已在注册表中，但未接入标准部署流程，仅预留。

### 架构位置

```
用户在 Portal 创建实例
        │
        ▼
  deploy_service 判断集群类型
        │
        └── compute_provider == "k8s"
                └── K8s 内置部署管道
                        └── Namespace → ConfigMap → PVC → Deployment → Service → Ingress
```

---

## 二、K8s 集群

### 前提条件

- 一个可用的 Kubernetes 集群（v1.24+）
- 拥有足够权限的 **KubeConfig**
- 集群内已部署 **Ingress Controller**（默认 nginx）
- `.env` 中已配置 **`ENCRYPTION_KEY`**（用于加密存储 KubeConfig）

### 2.1 KubeConfig 权限要求

NoDeskClaw 需要以下 K8s API 权限来管理实例：

| 资源 | 操作 | 说明 |
|---|---|---|
| `namespaces` | create, get, delete | 每个实例独占一个 namespace |
| `deployments` | create, get, patch, delete, list | 实例容器编排 |
| `services` | create, get, delete | 网络暴露 |
| `ingresses` | create, get, delete | 域名路由（需 Ingress Controller） |
| `configmaps` | create, get, patch, delete | 实例配置 |
| `persistentvolumeclaims` | create, get, delete | 数据持久化 |
| `networkpolicies` | create, get, delete | 出站流量控制 |
| `pods` | get, list, log | 状态查询和日志 |
| `nodes` | get, list | 集群概览、连接测试 |
| `events` | list | 部署事件追踪 |

> 建议为 NoDeskClaw 创建专用 ServiceAccount + ClusterRole，避免使用 admin kubeconfig。

### 2.2 添加 K8s 集群

在 Portal **组织设置 → 集群** 页面操作：

1. 点击"添加集群"
2. 选择 **Kubernetes** 类型
3. 选择云厂商标签（VKE / ACK / TKE / 自建）— 仅用于 UI 标识，不影响功能
4. 粘贴 KubeConfig 内容
5. 设置 Ingress Class（默认 `nginx`）
6. （可选）填写 Proxy Endpoint — 用于通过网关集群代理流量到实例集群
7. 提交后系统自动执行连接测试（`VersionApi.get_code` + `list_node`）

### 2.3 KubeConfig 认证方式

系统自动解析 KubeConfig 并识别认证方式：

| auth_type | 说明 | 注意事项 |
|---|---|---|
| `token` | Bearer Token 静态认证 | 注意 Token 有效期 |
| `client-certificate` | 客户端证书认证 | 证书过期需更新 KubeConfig |
| `exec-based` | 通过外部命令获取凭证 | 后端环境需安装对应 CLI 工具 |
| `oidc` | OpenID Connect | 需确保 OIDC Provider 可达 |

### 2.4 集群配置项

创建集群时写入 `provider_config`（JSONB）的字段：

| 字段 | 说明 | 默认值 |
|---|---|---|
| `cloud_vendor` | 云厂商标签（vke/ack/tke/custom） | 来自请求 |
| `auth_type` | 认证方式（自动解析） | — |
| `api_server_url` | K8s API Server 地址（自动解析） | — |
| `ingress_class` | Ingress Controller class 名称 | `nginx` |
| `k8s_version` | K8s 版本（连接测试时获取） | — |

### 2.5 K8s 实例部署流程

当用户在 K8s 集群上创建实例时，后端执行完整的异步部署管道：

```
① 创建 Namespace（nodeskclaw-default-{slug}）
    ↓
② 创建 ConfigMap（实例配置）
    ↓
③ 创建 PVC（持久化存储，使用 StorageClass）
    ↓
④ 创建 Deployment（DeskClaw 容器）
    ↓
⑤ 创建 Service（ClusterIP）
    ↓
⑥ 创建 Ingress（域名路由）
    ↓
⑦ 创建 NetworkPolicy（出站流量控制）
    ↓
⑧ 等待 Pod Ready
    ↓
⑨ 后置步骤（LLM 配置同步、Gene 安装等）
```

### 2.6 K8s 集群基础设施要求

#### Ingress Controller

实例通过 Ingress 暴露 HTTP(S) 访问，集群中必须有对应 Ingress Controller：

- 默认期望 `ingressClassName: nginx`
- 可在创建集群时自定义 `ingress_class`
- 参考 `nodeskclaw-artifacts/ingress-controller/` 中的部署说明

#### 存储（PVC）

每个实例创建一个 PVC 用于数据持久化：

- 默认 StorageClass：使用集群标记为 default 的 SC（用户可在创建实例时手动选择）
- 默认容量：`80Gi`
- 可在部署时通过创建实例页面调整

#### 网络策略

部署时自动创建 NetworkPolicy 控制实例出站流量，相关环境变量：

| 变量 | 说明 | 示例 |
|---|---|---|
| `EGRESS_DENY_CIDRS` | 禁止出站的 CIDR 列表 | `10.0.0.0/8,172.16.0.0/12` |
| `EGRESS_ALLOW_PORTS` | 允许出站的端口列表 | `443,80` |

### 2.7 网络连通性要求（AI 员工 → 后端）

K8s 集群上的 AI 员工 Pod 需要能**主动回连**后端的两个端点：

| 协议 | 用途 | 配置项 |
|---|---|---|
| HTTP(S) | Channel 插件 API 调用 | `AGENT_API_BASE_URL` |
| WebSocket | Tunnel 长连接（消息/状态推送） | `TUNNEL_BASE_URL`（可选，不设则从 `AGENT_API_BASE_URL` 推导） |

#### 后端为 Docker Compose 部署时

Docker Compose 默认监听 `localhost:4510`，K8s Pod 无法访问宿主机 localhost。
必须将 `AGENT_API_BASE_URL` 改为 K8s Pod 可达的地址：

```bash
# .env 示例 — 通过公网域名
AGENT_API_BASE_URL=https://your-nodeskclaw-domain.com/api/v1

# .env 示例 — 通过内网地址（后端和 K8s 集群在同一 VPC）
AGENT_API_BASE_URL=http://192.168.1.100:4510/api/v1
```

> 如果 `AGENT_API_BASE_URL` 仍为默认的 `localhost`，部署 K8s 实例时后端会直接返回 400 错误并提示修改。

#### `TUNNEL_BASE_URL`（可选）

通常不需要设置。仅当 WebSocket 需要走独立入口（如独立 wss:// 域名或不同端口）时才需要：

```bash
TUNNEL_BASE_URL=wss://ws.your-domain.com/api/v1/tunnel/connect
```

不设置时，OpenClaw channel 插件会将 `AGENT_API_BASE_URL` 中的 `http(s)://` 转换为 `ws(s)://` 并拼接 `/tunnel/connect` 作为 tunnel 地址。

#### NetworkPolicy 对回连端口的影响

默认 NetworkPolicy 只放行 `80` 和 `443` 端口的出站流量（由 `EGRESS_ALLOW_PORTS` 控制）。如果后端运行在非标准端口（如 `4510`），K8s Pod 的出站流量会被 NetworkPolicy 拦截。

解决方法（任选其一）：

1. **推荐**：后端通过 Nginx/ALB 反向代理，使用标准 443 端口对外提供服务
2. 在 `.env` 中将后端端口加入放行列表：`EGRESS_ALLOW_PORTS=80,443,4510`

---

## 三、关键环境变量参考

| 变量 | 必填 | 说明 | 默认值 |
|---|---|---|---|
| `ENCRYPTION_KEY` | 是 | KubeConfig 加密密钥（32 字节 base64） | — |
| `AGENT_API_BASE_URL` | 是 | AI 员工回连后端的 HTTP 地址，K8s 部署时不能为 localhost | `http://localhost:4510/api/v1` |
| `TUNNEL_BASE_URL` | 否 | AI 员工 WebSocket tunnel 地址，不设则从 AGENT_API_BASE_URL 推导 | — |
| `VKE_SUBNET_ID` | 火山云 VKE 集群需要 | VKE 子网 ID | — |
| `EGRESS_DENY_CIDRS` | 否 | NetworkPolicy 出站拒绝 CIDR | — |
| `EGRESS_ALLOW_PORTS` | 否 | NetworkPolicy 出站允许端口 | — |
| `IMAGE_REGISTRY` | 否 | 镜像仓库地址前缀 | — |
| `TZ` | 否 | Docker Compose 自托管部署时的容器时区，所有服务共用，可在项目根目录 `.env` 中修改 | `Asia/Shanghai` |

---

## 四、集群管理 API

| 方法 | 路径 | 说明 |
|---|---|---|
| `POST` | `/clusters` | 创建集群 |
| `GET` | `/clusters` | 列出集群 |
| `GET` | `/clusters/{id}` | 集群详情 |
| `PUT` | `/clusters/{id}` | 更新集群信息 |
| `DELETE` | `/clusters/{id}` | 删除集群（级联软删除实例） |
| `POST` | `/clusters/{id}/test` | 测试连接（验证 API Server） |
| `POST` | `/clusters/{id}/kubeconfig` | 更新 KubeConfig |
| `GET` | `/clusters/{id}/overview` | 集群资源概览（节点/CPU/内存） |
| `GET` | `/clusters/{id}/health` | 集群健康状态 |

### 创建集群请求示例

```json
{
  "name": "生产集群",
  "compute_provider": "k8s",
  "kubeconfig": "apiVersion: v1\nkind: Config\n...",
  "provider": "vke",
  "ingress_class": "nginx"
}
```

---

## 五、Proxy Endpoint（可选，网关代理）

适用于实例集群不直接暴露公网的场景。设置后系统会在**网关集群**创建 ExternalName Service，将流量通过网关集群的 Ingress 代理到实例集群。

```
用户浏览器 → 网关集群 Ingress → ExternalName Service → 实例集群
```

- 在创建或更新集群时填写 `proxy_endpoint`
- 网关集群的 KubeConfig 通过 `GATEWAY_KUBECONFIG` 环境变量配置

---

## 六、常见问题

### K8s 集群连接测试失败

**排查**：
1. 确认 KubeConfig 中的 API Server 地址从后端网络可达
2. 确认凭证未过期（Token/证书）
3. 确认 `ENCRYPTION_KEY` 配置正确（加解密不一致会导致 KubeConfig 无法解密）

### K8s 实例一直"部署中"

**排查**：
1. 检查 Pod 状态：`kubectl get pods -n nodeskclaw-default-<slug>`
2. 查看 Events：`kubectl describe pod <pod-name> -n <namespace>`
3. 常见原因：镜像拉取失败（ImagePullBackOff）、资源不足（Pending）、PVC 绑定失败

### Windows 环境常见问题

**环境要求**：Windows 10/11 + Git Bash（或 WSL2）

**常见问题与解决方案：**

**1. `dev.sh` 执行报 `$'\r': command not found`**

Git 在 Windows 上默认将 `.sh` 文件检出为 CRLF 行尾。解决方法：

```bash
git config core.autocrlf false
git checkout -- dev.sh
```

项目已配置 `.gitattributes` 确保 `.sh` 文件使用 LF，新 clone 不会再遇到此问题。

**2. `dev.sh` 端口检测跳过（lsof 不可用）**

Git Bash 不含 `lsof` 命令，脚本会自动回退到 `ss`/`netstat`，均不可用时跳过端口检测并给出警告。启动前手动确认 4510/4511 端口未被占用即可。
