# Nginx Ingress Controller 部署清单

NoDeskClaw 使用 Nginx Ingress Controller 实现 OpenClaw 实例的子域名自动路由。

## 架构

### 多集群中心网关模式

```
用户浏览器
  | *.nodeskai.com DNS 泛解析
  v
infra ALB (TLS 终止)
  |
  v
infra nginx-ingress-controller
  | 管理平台子域名 → 本地 Service
  | 实例子域名 → ExternalName Service → inst 集群 ALB
  v
inst nginx-ingress-controller
  | 按 Host 匹配: {slug}-claw.nodeskai.com
  v
实例 ClusterIP Service (:18789)
  |
  v
OpenClaw Pod (:18789)
```

每个 inst 集群需要独立安装本 deploy.yaml。infra 集群和 inst 集群各有一套 nginx-ingress-controller。

## 前置条件

| 条件 | 说明 |
|------|------|
| K8s 集群 | VKE 或其他 K8s 集群，版本 >= 1.25 |
| DNS 泛解析 | `*.nodeskai.com` 指向火山云 SLB 的公网 IP |
| 通配符证书 | `*.nodeskai.com` 的 TLS 证书（fullchain.pem + privkey.pem） |
| 火山云 SLB | 将 80 端口转发到 K8s 节点的 30080，443 转发到 30443 |

## 部署步骤

### 1. 部署 Ingress Controller

```bash
kubectl apply -f deploy.yaml
```

验证部署状态：

```bash
kubectl get pods -n nodeskclaw-system
# 确认 nodeskclaw-system-controller Pod 为 Running 状态
```

### 2. 创建 TLS Secret

方式一：直接用 kubectl 命令（推荐）

```bash
kubectl create secret tls wildcard-nodeskai-tls \
  --cert=fullchain.pem \
  --key=privkey.pem \
  -n nodeskclaw-system
```

方式二：编辑 `tls-secret.yaml` 填入 base64 编码后的证书

```bash
# base64 编码证书
cat fullchain.pem | base64 -w0
cat privkey.pem | base64 -w0

# 替换 tls-secret.yaml 中的占位符后
kubectl apply -f tls-secret.yaml
```

### 3. 配置火山云 SLB

在火山云控制台创建/配置 SLB：

- 前端监听端口 80（HTTP）→ 后端 K8s 节点的 30080 端口
- 前端监听端口 443（HTTPS）→ 后端 K8s 节点的 30443 端口
- 后端服务器组选择 K8s 集群的所有 Worker 节点

### 4. 配置 NoDeskClaw

在 NoDeskClaw 的 Settings 页面配置：

- **基础域名**: `nodeskai.com`
- **子域名后缀**: `nodeskclaw`
- **TLS Secret 名称**: `wildcard-nodeskai-tls`

配置完成后，每次部署 OpenClaw 实例时，NoDeskClaw 会自动创建 Ingress 规则，域名格式为 `{name}-nodeskclaw.nodeskai.com`。

## 文件说明

| 文件 | 说明 |
|------|------|
| `deploy.yaml` | Nginx Ingress Controller 完整部署清单（Namespace、RBAC、ConfigMap、Deployment、Service） |
| `tls-secret.yaml` | TLS Secret 模板，填入通配符证书后 apply |
| `README.md` | 本文件 |

## 验证

部署完成后，验证 Ingress Controller 是否正常工作：

```bash
# 检查 Controller Pod
kubectl get pods -n nodeskclaw-system

# 检查 Service NodePort
kubectl get svc -n nodeskclaw-system

# 检查 IngressClass
kubectl get ingressclass

# 测试连通性（替换为实际节点 IP）
curl -H "Host: test.nodeskai.com" http://<node-ip>:30080
```
