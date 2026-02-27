# deploy/ — CI/CD 构建部署脚本

NoDeskClaw 前后端的镜像构建、推送和 K8s 部署更新工具集。

## 目录结构

```
deploy/
├── deploy.sh         # 统一构建推送部署脚本
├── init-secrets.sh   # 首次部署初始化（创建 K8s Secret + 应用清单）
├── k8s/
│   ├── backend.yaml  # 后端 Deployment + Service
│   ├── admin.yaml    # Admin 前端 Deployment + Service
│   └── portal.yaml   # Portal 前端 Deployment + Service
└── README.md
```

## 部署架构

三个独立镜像，各自有 Deployment + ClusterIP Service，部署在 `nodeskclaw-system` Namespace：

| 组件 | 镜像名 | 端口 | 说明 |
|------|--------|------|------|
| backend | `nodeskclaw-backend` | 8000 | FastAPI，处理 API + SSE |
| admin | `nodeskclaw-admin` | 80 | Nginx，Admin 前端，反代 `/api` `/stream` 到 backend |
| portal | `nodeskclaw-portal` | 80 | Nginx，Portal 前端，反代 `/api` 到 backend |

镜像仓库：`nodesk-center-cn-beijing.cr.volces.com/base-image/`

## 用法

### 首次部署

```bash
# 1. 确保 kubectl 指向正确的 VKE 集群
# 2. 确保 cr-pull-secret 已在 nodeskclaw-system 中创建
# 3. 初始化（从 .env 创建 Secret + 应用 K8s 清单）
./deploy/init-secrets.sh

# 4. 构建、推送、部署全部组件
./deploy/deploy.sh all
```

### 日常更新

```bash
# 更新后端
./deploy/deploy.sh backend

# 更新 Admin 前端
./deploy/deploy.sh admin

# 更新 Portal 前端
./deploy/deploy.sh portal

# 全量更新
./deploy/deploy.sh all
```

### 高级用法

```bash
# 仅构建和推送镜像，不更新 K8s
./deploy/deploy.sh backend --build-only

# 仅更新 K8s 到指定标签（不重新构建）
./deploy/deploy.sh admin --deploy-only --tag 20260218-b0f6ad1

# 构建时不使用 Docker 缓存
./deploy/deploy.sh portal --no-cache
```

### 镜像标签格式

`YYYYMMDD-<git-short-hash>`，例如 `20260218-b0f6ad1`

## 前提条件

- Docker Desktop 运行中，且能访问 Docker Hub（拉取基础镜像）
- 已登录火山云 CR：`docker login nodesk-center-cn-beijing.cr.volces.com`
- `kubectl` 已配置正确的 VKE 集群上下文
- `nodeskclaw-system` Namespace 和 `cr-pull-secret` 已存在

## Dockerfile 位置

| 组件 | Dockerfile | Nginx 配置 |
|------|-----------|------------|
| backend | `nodeskclaw-backend/Dockerfile` | — |
| admin | `nodeskclaw-frontend/Dockerfile` | `nodeskclaw-frontend/nginx.conf` |
| portal | `nodeskclaw-portal/Dockerfile` | `nodeskclaw-portal/nginx.conf` |
