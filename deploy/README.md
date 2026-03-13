# deploy/ — CI/CD 构建部署脚本

DeskClaw 前后端的镜像构建、推送和 K8s 部署更新工具集。

## 目录结构

```
deploy/
├── deploy.sh         # 统一构建推送部署脚本
├── release.sh        # 发布工作流（staging -> release -> promote）
├── init-secrets.sh   # 首次部署初始化（创建 K8s Secret + 应用清单）
├── k8s/
│   ├── backend.yaml  # 后端 Deployment + Service
│   ├── admin.yaml    # Admin 前端 Deployment + Service
│   ├── portal.yaml   # Portal 前端 Deployment + Service
│   └── ingress.yaml  # Ingress（需手动配置域名后 apply）
└── README.md
```

## 部署架构

三个独立镜像，各自有 Deployment + ClusterIP Service：

| 组件 | 镜像名 | 端口 | 说明 |
|------|--------|------|------|
| backend | `nodeskclaw-backend` | 8000 | FastAPI，处理 API + SSE |
| admin | `nodeskclaw-admin` | 80 | Nginx，Admin 前端，反代 `/api` `/stream` 到 backend |
| portal | `nodeskclaw-portal` | 80 | Nginx，Portal 前端，反代 `/api` 到 backend |

镜像仓库：`<YOUR_REGISTRY>/<YOUR_NAMESPACE>/`

K8s YAML 清单不包含 `namespace` 字段，由 `kubectl -n <NS>` 在运行时指定目标 Namespace。

## 用法

### 首次部署

```bash
# 1. 初始化（从 .env 创建 Secret + 应用 Deployment/Service 清单）
./deploy/init-secrets.sh --context <CTX>

# 2. 手动配置 Ingress 域名后 apply
kubectl --context <CTX> -n <NS> apply -f deploy/k8s/ingress.yaml

# 3. 构建、推送、部署全部组件
./deploy/deploy.sh all --context <CTX>
```

### 日常更新

```bash
./deploy/deploy.sh backend --context <CTX>
./deploy/deploy.sh admin --context <CTX>
./deploy/deploy.sh portal --context <CTX>
./deploy/deploy.sh all --context <CTX>
```

### 多 Namespace 部署

```bash
# 部署到 staging 环境
./deploy/deploy.sh all --context <CTX> --namespace nodeskclaw-staging

# 部署到 production 环境（默认）
./deploy/deploy.sh all --context <CTX> --namespace nodeskclaw-system
```

### 高级用法

```bash
# 仅构建和推送镜像，不更新 K8s
./deploy/deploy.sh backend --build-only

# 仅更新 K8s 到指定标签（不重新构建）
./deploy/deploy.sh admin --deploy-only --tag v0.1.0-beta.1 --context <CTX>

# 构建时不使用 Docker 缓存
./deploy/deploy.sh portal --no-cache --context <CTX>
```

### 版本发布工作流

使用 `release.sh` 管理完整的 staging -> release -> promote 流程：

```bash
# 1. 构建并部署到 staging
./deploy/release.sh staging v0.1.0-beta.1 --context <CTX>

# 2. 测试通过后，创建 GitHub Pre-release
./deploy/release.sh release v0.1.0-beta.1

# 3. 升级生产环境
./deploy/release.sh promote v0.1.0-beta.1 --context <CTX>

# 完整流程（每步需确认）
./deploy/release.sh full v0.1.0-beta.1 --context <CTX>
```

### 镜像标签格式

- 日常更新：`YYYYMMDD-<git-short-hash>`（如 `20260218-b0f6ad1`）
- 版本发布：语义化版本（如 `v0.1.0-beta.1`、`v0.1.0`）

## 前提条件

- Docker Desktop 运行中，且能访问 Docker Hub（拉取基础镜像）
- 已登录容器镜像仓库：`docker login <YOUR_REGISTRY>`
- `kubectl` 已配置正确的集群上下文
- 目标 Namespace 和 `cr-pull-secret` 已存在
- `gh` CLI 已安装并认证（`release.sh` 需要）
- 创建本地部署配置 `deploy/.env.local`（已被 `.gitignore` 忽略），填写真实镜像仓库地址：
  ```bash
  # deploy/.env.local
  REGISTRY="<YOUR_REGISTRY>/<YOUR_NAMESPACE>"
  ```

## Dockerfile 位置

| 组件 | Dockerfile | Nginx 配置 |
|------|-----------|------------|
| backend | `nodeskclaw-backend/Dockerfile` | — |
| admin | `ee/nodeskclaw-frontend/Dockerfile` | `ee/nodeskclaw-frontend/nginx.conf` |
| portal | `nodeskclaw-portal/Dockerfile` | `nodeskclaw-portal/nginx.conf` |

## CE/EE 构建差异

`deploy.sh` 自动检测项目根目录下是否存在 `ee/` 目录：

- **CE 模式**（无 `ee/`）：使用各组件自身的 Dockerfile 和 build context，构建纯 CE 镜像。admin 组件跳过构建（CE 不含管理后台）。
- **EE 模式**（有 `ee/`）：
  - backend：追加 `COPY ee/ ./ee/` 将 EE 后端模块打入镜像
  - admin：直接使用 `ee/nodeskclaw-frontend/Dockerfile` 构建（该目录本身就是完整的 EE 前端项目）
  - portal：生成临时 Dockerfile，`COPY ee/frontend/portal/ /ee/frontend/portal/` 使 Vite alias 覆盖生效

K8s 清单（`k8s/*.yaml`）CE/EE 通用，差异仅在镜像内容。
