# Nginx Ingress Controller 部署清单

ClawBuddy 使用 Nginx Ingress Controller 实现 OpenClaw 实例的子域名自动路由。

## 架构

```
用户浏览器
  | *.nodesk.tech DNS 泛解析
  v
火山云 SLB (:80/:443)
  |
  v
K8s Nginx Ingress Controller (NodePort 30080/30443)
  | 按 Host 匹配: {instance-name}-clawbuddy.nodesk.tech
  v
实例 ClusterIP Service (:18789)
  |
  v
OpenClaw Pod (:18789)
```

## 前置条件

| 条件 | 说明 |
|------|------|
| K8s 集群 | VKE 或其他 K8s 集群，版本 >= 1.25 |
| DNS 泛解析 | `*.nodesk.tech` 指向火山云 SLB 的公网 IP |
| 通配符证书 | `*.nodesk.tech` 的 TLS 证书（fullchain.pem + privkey.pem） |
| 火山云 SLB | 将 80 端口转发到 K8s 节点的 30080，443 转发到 30443 |

## 部署步骤

### 1. 部署 Ingress Controller

```bash
kubectl apply -f deploy.yaml
```

验证部署状态：

```bash
kubectl get pods -n clawbuddy-system
# 确认 clawbuddy-system-controller Pod 为 Running 状态
```

### 2. 创建 TLS Secret

方式一：直接用 kubectl 命令（推荐）

```bash
kubectl create secret tls wildcard-nodesk-tls \
  --cert=fullchain.pem \
  --key=privkey.pem \
  -n clawbuddy-system
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

### 4. 配置 ClawBuddy

在 ClawBuddy 的 Settings 页面配置：

- **基础域名**: `nodesk.tech`
- **子域名后缀**: `clawbuddy`
- **TLS Secret 名称**: `wildcard-nodesk-tls`

配置完成后，每次部署 OpenClaw 实例时，ClawBuddy 会自动创建 Ingress 规则，域名格式为 `{name}-clawbuddy.nodesk.tech`。

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
kubectl get pods -n clawbuddy-system

# 检查 Service NodePort
kubectl get svc -n clawbuddy-system

# 检查 IngressClass
kubectl get ingressclass

# 测试连通性（替换为实际节点 IP）
curl -H "Host: test.nodesk.tech" http://<node-ip>:30080
```
