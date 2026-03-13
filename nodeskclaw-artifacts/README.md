# nodeskclaw-artifacts

NoDeskClaw 部署到 K8s 的制品仓库 -- 存放 Docker 镜像构建文件和集群基础设施部署清单。

## 目录结构

```
nodeskclaw-artifacts/
├── common.sh                    # 公共构建函数（日志、Docker 操作、参数解析、--with-security 支持）
├── openclaw-image/              # OpenClaw 工作引擎镜像
│   ├── Dockerfile               # Base 镜像: node:22-bookworm-slim + npm 全局安装 openclaw
│   ├── Dockerfile.security      # 安全层镜像: FROM base + COPY TypeScript 插件到 extensions/
│   ├── docker-entrypoint.sh     # 容器启动脚本（配置生成 + 凭证注入 + 前台启动）
│   ├── init-container.sh        # Init Container 脚本（PVC 数据初始化 + 版本升级）
│   ├── openclaw.json.template   # 配置模板，启动时 envsubst 替换占位符
│   ├── build-and-push.sh        # 一键构建推送脚本（支持 --with-security）
│   └── check-update.sh          # 版本检测脚本（查询 npm 最新稳定版、自动更新 Dockerfile）
├── zeroclaw-image/              # ZeroClaw 高性能工作引擎镜像
│   ├── Dockerfile               # Base 镜像: debian:bookworm-slim + 预编译二进制下载
│   ├── Dockerfile.security      # 安全层镜像: 多阶段 Rust 源码构建（git clone + cargo build）
│   ├── docker-entrypoint.sh     # 容器入口脚本
│   ├── build-and-push.sh        # 构建推送脚本（支持 --with-security）
│   ├── check-update.sh          # 版本检测脚本（查询 GitHub Releases 最新版、自动更新 Dockerfile）
│   └── README.md                # 构建说明
├── nanobot-image/               # Nanobot 轻量工作引擎镜像
│   ├── Dockerfile               # Base 镜像: python:3.13-slim-bookworm + pip install nanobot-ai
│   ├── Dockerfile.security      # 安全层镜像: FROM base + pip install 安全层 + startup wrapper
│   ├── nanobot.yaml.template    # Nanobot 配置模板
│   ├── docker-entrypoint.sh     # 容器入口脚本
│   ├── build-and-push.sh        # 构建推送脚本（支持 --with-security）
│   ├── check-update.sh          # 版本检测脚本（查询 PyPI 最新稳定版、自动更新 Dockerfile）
│   └── README.md                # 构建说明
├── ingress-controller/          # Nginx Ingress Controller 部署清单
│   ├── deploy.yaml              # 完整 K8s 资源（Namespace、RBAC、Deployment、Service）
│   ├── tls-secret.yaml          # 通配符 TLS 证书 Secret 模板
│   └── README.md                # 部署说明
└── k8s/                         # 集群基础设施 YAML 模板
    └── nas-storageclass.yaml    # NAS 极速型 StorageClass（NFS subpath 动态供给）
```

## DeskClaw 镜像

### 这是什么

NoDeskClaw 管理的 DeskClaw 实例运行的 Docker 镜像。不从源码构建，而是通过 `npm install -g openclaw` 安装发布版本。

### 版本检查

```bash
cd nodeskclaw-artifacts/openclaw-image

# 检查是否有新版本
./check-update.sh

# 检查并自动更新 Dockerfile
./check-update.sh --update
```

### 构建推送

```bash
cd nodeskclaw-artifacts/openclaw-image

# 使用 Dockerfile 中的默认版本构建并推送
./build-and-push.sh

# 指定版本
./build-and-push.sh --version 2026.2.26

# 仅构建不推送
./build-and-push.sh --build-only
```

脚本自动完成：npm 版本校验 → `docker build --platform linux/amd64` → 打 `v{version}` + `latest` tag → 推送 → 验证。

### 安全层镜像构建

每个 Runtime 支持 `--with-security` 模式，在 base 镜像基础上追加安全层：

```bash
# 1. 先构建 base 镜像
cd openclaw-image && ./build-and-push.sh --version 2026.2.26 --build-only
# 2. 再构建安全层镜像（FROM base）
./build-and-push.sh --with-security --base-tag v2026.2.26 --build-only

# Nanobot
cd ../nanobot-image && ./build-and-push.sh --version 0.1.0 --build-only
./build-and-push.sh --with-security --base-tag v0.1.0 --build-only

# ZeroClaw（安全层模式为 Rust 源码构建，耗时较长）
cd ../zeroclaw-image && ./build-and-push.sh --version v0.1.0 --build-only
ZEROCLAW_REPO=https://github.com/nicholasgasior/zeroclaw.git ZEROCLAW_REF=main \
  ./build-and-push.sh --with-security --base-tag v0.1.0 --build-only
```

安全层镜像 Tag 格式: `v{VERSION}-sec`（如 `v2026.2.26-sec`）。

| 模式 | Dockerfile | 构建上下文 | 说明 |
|------|-----------|-----------|------|
| Base | `Dockerfile` | 当前目录 | 现有逻辑不变 |
| Security | `Dockerfile.security` | 项目根目录 | FROM base + 安全层 |

也可以通过 GitHub Actions 手动触发构建工作流（见 `.github/workflows/build-openclaw-image.yml`）。

| 构建参数 | 说明 | 默认值 |
|----------|------|--------|
| `NODE_VERSION` | Node.js 大版本 | `22` |
| `OPENCLAW_VERSION` | openclaw npm 包版本 | `2026.2.26` |
| `IMAGE_VERSION` | 镜像 Tag 版本标记 | `v2026.2.26` |

### 版本自动检测

项目配置了 GitHub Actions 定时工作流（`.github/workflows/check-runtime-updates.yml`），每天自动检查三个工作引擎的最新版本：

| Runtime | 包来源 | 版本检查方式 |
|---------|--------|-------------|
| OpenClaw | npm `openclaw` | `npm view` 过滤 `YYYY.M.DD` 格式稳定版 |
| Nanobot | PyPI `nanobot-ai` | PyPI JSON API 过滤 `X.Y.Z` 格式稳定版 |
| ZeroClaw | GitHub `nicholasgasior/zeroclaw` | GitHub Releases API 获取最新 release tag |

发现新版本时自动创建对应 PR，人工审核后合并。三个 runtime 的检测作为独立 Job 并行运行，互不影响。

### 镜像内文件说明

| 文件 | 作用 |
|------|------|
| `docker-entrypoint.sh` | 容器启动入口。检查 `OPENCLAW_FORCE_RECONFIG` 决定是否从模板重建配置，补全旧配置缺失的 `controlUi` 字段（版本兼容），注入凭证，然后 `exec openclaw gateway` 前台运行 |
| `init-container.sh` | K8s Init Container 执行。首次部署时将 `/root/.openclaw` 模板拷贝到 PVC；版本升级时合并内置插件、更新版本标记 |
| `openclaw.json.template` | 配置模板，包含 `${OPENCLAW_GATEWAY_PORT}` 等占位符，由 entrypoint 用 `envsubst` 替换生成 `openclaw.json`。`controlUi` 包含 `allowInsecureAuth`（绕过设备配对）和 `dangerouslyAllowHostHeaderOriginFallback`（非 loopback 绑定时的 Origin 校验回退） |
| `build-and-push.sh` | 一键构建推送脚本。支持 `--version` 指定版本、`--build-only` 仅构建、npm 版本校验、自动打 tag |
| `check-update.sh` | 版本检测脚本。查询 npm 最新稳定版（过滤 beta/rc），支持 `--update` 自动更新 Dockerfile |

### 关键环境变量

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `OPENCLAW_GATEWAY_PORT` | 监听端口 | `18789` |
| `OPENCLAW_GATEWAY_BIND` | 绑定策略（lan = 0.0.0.0） | `lan` |
| `OPENCLAW_GATEWAY_TOKEN` | Gateway 认证 Token | 必填 |
| `OPENCLAW_LOG_LEVEL` | 日志级别 | `info` |
| `OPENCLAW_FORCE_RECONFIG` | 设为 `true` 时强制从模板重建配置 | `false` |
| `OPENCLAW_CREDENTIALS_JSON` | JSON 格式凭证，写入 credentials/default.json | 可选 |
| `OPENAI_API_KEY` | OpenAI 模型 Key，DeskClaw 原生读取 | 可选 |
| `ANTHROPIC_API_KEY` | Anthropic 模型 Key | 可选 |

### 构建产物检查清单

构建完成后验证：

```bash
docker run --rm <image> node --version          # 输出 Node.js 版本
docker run --rm <image> openclaw --version       # 输出 DeskClaw 版本
docker run --rm <image> which openclaw           # /usr/local/bin/openclaw
docker run --rm <image> ls /root/.openclaw/      # 目录结构完整
docker run --rm <image> cat /root/.openclaw-version  # 版本标记正确
```

## Nginx Ingress Controller

### 这是什么

NoDeskClaw 使用 Nginx Ingress Controller 实现 DeskClaw 实例的子域名自动路由。每个实例部署时自动创建 Ingress 规则，用户通过 `{instance-name}.{base-domain}` 访问对应实例。

### 架构

```
用户浏览器 → *.example.com DNS → 负载均衡器 → K8s Ingress Controller (NodePort 30080/30443) → ClusterIP Service (:18789) → DeskClaw Pod
```

### 部署

```bash
cd nodeskclaw-artifacts/ingress-controller

# 1. 部署 Ingress Controller
kubectl apply -f deploy.yaml

# 2. 创建 TLS Secret（通配符证书）
kubectl create secret tls wildcard-nodeskai-tls \
  --cert=fullchain.pem --key=privkey.pem -n nodeskclaw-system

# 3. 配置负载均衡器 转发 80→30080, 443→30443
```

详细说明见 `ingress-controller/README.md`。

## NAS StorageClass

### 这是什么

DeskClaw 实例需要持久化存储（PVC）来保存运行数据。使用NFS 存储 + NFS CSI 动态供给（subpath 模式），每个 PVC 自动创建独立子目录。

### 前提

- VKE 集群已安装 `csi-nas` 组件（集群 -> 组件管理 -> 存储）
- 已购买NFS 存储并创建挂载点

### 部署

```bash
# 一次性操作：创建 StorageClass
kubectl apply -f k8s/nas-storageclass.yaml

# 验证
kubectl get sc nas-subpath
```

### 参数说明

| 参数 | 说明 |
|------|------|
| `volumeAs: subpath` | subpath 模式：共享同一 NAS，每个 PVC 自动创建子目录 |
| `server` | NAS 挂载地址（IP:路径），按实际 NAS 实例替换 |
| `archiveOnDelete: "true"` | 删除 PVC 时将子目录归档（重命名），不物理删除 |
| `reclaimPolicy: Retain` | 即使 PVC 被删除，NAS 上的数据也保留 |
| `allowVolumeExpansion: true` | 允许后续扩容 PVC |

### 添加新存储类型

未来购买新 NAS（如容量型），创建新的 StorageClass YAML 并 `kubectl apply` 即可。NoDeskClaw 前端部署页会自动从集群读取可用的 StorageClass 列表供用户选择。

---

## 与其他项目的关系

- **nodeskclaw-backend** -- NoDeskClaw 管理平台后端，有自己的 Dockerfile
- **ee/nodeskclaw-frontend** -- NoDeskClaw 管理平台前端（EE-only），开发阶段无需独立镜像
- **本目录** -- 被 NoDeskClaw 部署到 K8s 的 DeskClaw 实例镜像

详细的镜像设计文档见 EE 私有仓库 `ee/docs/DeskClaw镜像构建规范.md`。
