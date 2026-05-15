# deploy/ — 发版与部署工具

DeskClaw 的发版和部署使用独立入口管理：`release.sh` 只负责版本制品和 GitHub Release，`deploy.sh` 只负责把已存在镜像 tag 更新到 K8s，`init.sh` 只负责首次初始化环境。

## 目录结构

```
deploy/
├── release.sh         # 发版：构建镜像、推送、git tag、GitHub Release
├── deploy.sh          # 部署：更新 K8s Deployment 到指定 tag
├── init.sh            # 初始化：Namespace、Secret、基础 Deployment/Service
├── lib/               # 共享函数
├── .env.local         # 本地部署配置（不进 git）
├── k8s/               # K8s Deployment / Service / Ingress 清单
└── mirrors/           # 构建镜像源预设
```

## 前置配置

创建 `deploy/.env.local`（已被 `.gitignore` 忽略）：

```bash
REGISTRY="<YOUR_REGISTRY>/<YOUR_NAMESPACE>"
PUBLIC_REGISTRY="<PUBLIC_REGISTRY>/<PUBLIC_NAMESPACE>"  # 可选
KUBE_CONTEXT="<YOUR_KUBECTL_CONTEXT>"
```

`PUBLIC_REGISTRY` 可选。配置后，backend/portal/proxy 使用 `PUBLIC_REGISTRY`，admin 始终使用 `REGISTRY`；未配置时所有组件使用 `REGISTRY`。

其他前提：

- Docker Desktop 运行中，且已登录容器镜像仓库
- `kubectl` 已配置目标集群上下文
- 目标 Namespace 和 `cr-pull-secret` 已存在，或先运行 `init.sh`
- `gh` CLI 已安装并认证（仅 `release.sh` 需要）

## 发版

创建版本制品：

```bash
./deploy/release.sh create v0.5.0
./deploy/release.sh create v0.5.0 --ee
./deploy/release.sh create v0.5.0 --skip-proxy
./deploy/release.sh create v0.5.0 --mirrors cn
```

`create` 会构建并推送版本镜像、生成 changelog、创建/更新 git tag，并创建 GitHub Pre-release。它不会执行 K8s 部署。

将 GitHub Release 标记为正式版：

```bash
./deploy/release.sh finalize v0.5.0
```

`finalize` 只更新 GitHub Release 状态，不触碰 K8s。

## 部署

部署只使用已存在镜像 tag，`--tag` 必填：

```bash
./deploy/deploy.sh deploy --tag v0.5.0 --staging --context <CTX>
./deploy/deploy.sh deploy backend --tag v0.5.0 --staging --context <CTX>
./deploy/deploy.sh deploy proxy --tag v0.5.0 --staging --context <CTX>
./deploy/deploy.sh deploy --tag v0.5.0 --prod --context <CTX>
```

EE 模式：

```bash
./deploy/deploy.sh deploy --tag v0.5.0 --ee --staging --context <CTX>
./deploy/deploy.sh deploy admin --tag v0.5.0 --ee --staging --context <CTX>
./deploy/deploy.sh deploy --tag v0.5.0 --ee --skip-proxy --staging --context <CTX>
```

生产部署会先展示当前镜像和目标镜像，并要求交互确认。部署脚本不构建镜像、不推送镜像、不修改 GitHub Release。

## 首次初始化

```bash
./deploy/init.sh --staging --context <CTX>
./deploy/init.sh --prod --context <CTX>
./deploy/init.sh --env-file path/to/.env --staging --context <CTX>
./deploy/init.sh --ee --staging --context <CTX>
```

初始化会创建 Namespace、写入后端 Secret，并应用基础 Deployment/Service 清单。Ingress 仍需配置域名后手动 apply：

```bash
kubectl --context <CTX> -n <NS> apply -f deploy/k8s/ingress.yaml
```

### GeneHub 配置

GeneHub 已合并到主仓库，但在 K8s 中仍作为独立服务部署：

- `genehub`（GeneHub Registry，基因库 API）读取 `GENEHUB_DATABASE_URL`（GeneHub 数据库连接）连接 PostgreSQL。
- `genehub-gitea`（基因文件 Git 存储）使用 `genehub-gitea-data` PVC（持久化卷声明）保存仓库数据，避免 Pod 重建后丢失 gene 文件。
- Backend（后端 API）通过 `GENEHUB_REGISTRY_URL`（GeneHub Registry 地址）把 GeneHub 数据聚合到 Portal（用户门户）的 Gene Market（基因市场）。

首次运行 `deploy/init.sh` 前，需要在 `nodeskclaw-backend/.env` 或 `--env-file` 指定的文件中配置：

```bash
GENEHUB_DATABASE_URL=postgres://<user>:<password>@<host>:5432/genehub
GENEHUB_REGISTRY_URL=http://genehub
GENEHUB_WEB_URL=<your-genehub-web-url>
GENEHUB_ADMIN_TOKEN=<optional-admin-token>
GENEHUB_JWT_SECRET=<optional-jwt-secret>
GENEHUB_ADMIN_LOGINS=<optional-admin-login-list>
GENEHUB_WEBHOOK_SECRET=<optional-webhook-secret>
```

`GENEHUB_DATABASE_URL`（GeneHub 数据库连接）是必填项。`deploy/init.sh` 会在创建 `nodeskclaw-backend-env` Secret（后端环境变量 Secret）前校验它，未配置或仍是占位符时会直接失败，避免 GeneHub Registry 在集群内回落到 localhost 默认数据库。

## 标准流程

Staging 验证：

```bash
./deploy/release.sh create v0.5.0
./deploy/deploy.sh deploy --tag v0.5.0 --staging --context <CTX>
```

生产发布：

```bash
./deploy/deploy.sh deploy --tag v0.5.0 --prod --context <CTX>
./deploy/release.sh finalize v0.5.0
```

## 镜像标签格式

- 日常测试版本：`YYYYMMDD-<git-short-hash>` 或显式版本号
- 正式版本：语义化版本，例如 `v0.1.0-beta.1`、`v0.1.0`

## CE/EE 差异

通过 `--ee` 参数控制构建或部署目标：

- CE 模式默认包含 backend、portal、proxy，不包含 admin。
- EE 模式包含 backend、admin、portal、proxy，并要求本地存在 `ee/` 目录。
- admin 镜像始终使用 `REGISTRY`，其他组件使用 `PUBLIC_REGISTRY`，未配置时回退 `REGISTRY`。
