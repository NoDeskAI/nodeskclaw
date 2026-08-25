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
├── k8s/               # K8s Deployment / Service / Ingress 清单，含可选 Hosted Registry
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
./deploy/deploy.sh deploy --tag v0.5.0 --prod --context <CTX>
./deploy/deploy.sh deploy backend --tag v0.5.0 --prod --context <CTX>
./deploy/deploy.sh deploy proxy --tag v0.5.0 --prod --context <CTX>
```

EE 模式：

```bash
./deploy/deploy.sh deploy --tag v0.5.0 --ee --prod --context <CTX>
./deploy/deploy.sh deploy admin --tag v0.5.0 --ee --prod --context <CTX>
./deploy/deploy.sh deploy --tag v0.5.0 --ee --skip-proxy --prod --context <CTX>
```

生产部署会先展示当前镜像和目标镜像，并要求交互确认。部署脚本不构建镜像、不推送镜像、不修改 GitHub Release。需要独立验证环境时，可以先显式初始化临时 staging namespace，再把上述命令的 `--prod` 替换为 `--staging`。

## 首次初始化

```bash
./deploy/init.sh --prod --context <CTX>
./deploy/init.sh --env-file path/to/.env --prod --context <CTX>
./deploy/init.sh --ee --prod --context <CTX>
# 可选临时验证 namespace：
./deploy/init.sh --staging --context <CTX>
```

初始化会创建 Namespace、写入后端 Secret，并应用基础 Deployment/Service 清单。Ingress 仍需配置域名后手动 apply：

```bash
kubectl --context <CTX> -n <NS> apply -f deploy/k8s/ingress.yaml
```

### 文件上传相关部署配置

文件上传策略由后端环境变量和 `system_configs`（系统配置表）共同决定。K8s 部署时，`deploy/init.sh` 会把 `nodeskclaw-backend/.env` 写入 `nodeskclaw-backend-env` Secret，因此上传配置必须先写进该 env 文件再初始化或覆盖 Secret。

需要同步的关键项：

| 配置 | 说明 |
|------|------|
| `UPLOAD_STORAGE_BACKEND` | 上传存储后端意图，`auto/local/s3`。目标为 S3 但必需配置缺失时不会回退 local |
| `S3_ENDPOINT`、`S3_BUCKET`、`S3_ACCESS_KEY_ID`、`S3_SECRET_ACCESS_KEY` | S3 兼容对象存储必需配置 |
| `AGENT_FILE_DOWNLOAD_BASE_URL` | 发给 Agent 的稳定下载 URL 基础地址，必须是 Agent Pod 可达的后端 `/api/v1` 地址 |
| `UPLOAD_GATEWAY_PROXY_BODY_SIZE_MB` | 记录部署网关请求体上限，需与 Ingress `nginx.ingress.kubernetes.io/proxy-body-size` 和 Portal Nginx `client_max_body_size` 保持一致 |
| `UPLOAD_PROXY_READ_TIMEOUT_SECONDS`、`UPLOAD_PROXY_SEND_TIMEOUT_SECONDS` | 需与 Ingress 读写超时和 Portal Nginx 反代超时保持一致 |

如果应用上限高于网关上限，Portal 的「组织设置 > 文件上传」会展示风险提示，但实际大文件仍会被 Nginx / Ingress 先拒绝。调整大文件能力时必须同时改 `.env`、`deploy/k8s/ingress.yaml` 和 `nodeskclaw-portal/nginx.conf`。

### Hosted Registry（托管仓库）

需要由 DeskClaw 托管工作引擎镜像时，在后端 env 文件中配置：

```bash
REGISTRY_MODE=hosted
HOSTED_REGISTRY_URL=registry.example.com/deskclaw
HOSTED_REGISTRY_USERNAME=registry-admin
HOSTED_REGISTRY_PASSWORD=<STRONG_PASSWORD>
HOSTED_REGISTRY_TLS_SECRET=registry-example-com-tls
HOSTED_REGISTRY_STORAGE_CLASS=<STORAGE_CLASS>
HOSTED_REGISTRY_STORAGE_SIZE=100Gi
HOSTED_REGISTRY_INGRESS_CLASS=nginx
```

然后显式初始化：

```bash
./deploy/init.sh --ee --with-hosted-registry --prod --context <CTX>
```

初始化会创建单副本 OCI Distribution、PVC（持久卷）、Basic Auth（基础认证）Secret、Service 和 TLS Ingress。仓库域名必须能被构建机和所有受管 K8s 节点访问并信任其证书。脚本不推送工作引擎镜像；推送方式见 `nodeskclaw-artifacts/README.md`。

对已有安装执行时，脚本会滚动重启后端，使新增的 Hosted Registry 环境配置写入尚未存在的系统配置键；已有 `registry_mode` 不会被覆盖。初始化完成后如仍显示 Custom Registry，请在 Admin 或 Portal 的镜像仓库设置中切换为团队托管仓库。

若省略 `HOSTED_REGISTRY_STORAGE_CLASS`，PVC 使用集群默认 StorageClass。Hosted Registry 首期只承载工作引擎镜像，主控组件初次启动仍需要外部仓库或离线预载镜像。

若构建集群无法直连 GitHub、Docker Hub、npm 或 PyPI，可在后端 env 文件中配置 `IMAGE_BUILD_PROXY_URL`（镜像构建代理地址）、`IMAGE_BUILD_NO_PROXY`（无需代理的地址）和 `IMAGE_BUILD_BASE_IMAGE_REGISTRY`（基础镜像 Registry，默认 `docker.io/library`）。当代理地址使用 `127.0.0.1` 时，镜像构建 Pod 会启用宿主机网络以访问节点上的代理；只应在所有可选构建节点均运行可信代理时使用。

需要单独加速构建依赖时，可配置 `IMAGE_BUILD_APT_MIRROR`（APT 镜像主机）、`IMAGE_BUILD_NPM_REGISTRY`（npm 镜像地址）、`IMAGE_BUILD_PIP_INDEX_URL`（PyPI 镜像地址）和 `IMAGE_BUILD_PIP_TRUSTED_HOST`（PyPI 信任主机），其含义与 `deploy/mirrors/*.env` 保持一致。

## 标准流程

本地验证：

```bash
./deploy/release.sh create v0.5.0
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
