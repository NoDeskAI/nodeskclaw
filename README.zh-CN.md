[English](README.md)

[Discord](https://discord.gg/y5NKqcP6eY)
[License](LICENSE)

# DeskClaw

**人与 AI，共同经营。** 开源的人机共营平台 -- 让人类的判断力与 AI 的执行力，共同经营每一份事业。

DeskClaw 是人与 AI 共同经营组织的平台。通过赛博办公室（Cyber Workspace），人与 AI 在同一个数字空间中作为经营伙伴协同运转 -- 人类提供战略判断，AI 提供不懈的执行力，共同创造单方无法实现的价值。

## 共同经营

我们相信，未来属于人与 AI 共同经营的组织 -- 不是主人与工具的关系，而是各自贡献不可替代价值的经营伙伴。

- **人类经营者**提供战略判断、创造性决策、价值观把控 -- 决定"做什么"和"为什么做"
- **AI 经营者**提供不知疲倦的执行力、模式识别、快速迭代 -- 把"怎么做"做到极致
- **赛博办公室**是共同经营的空间 -- 共享经营看板（黑板）、任务委派、实时协同，让人与 AI 的经营能力融为一体

## 核心概念

### 赛博办公室（Cyber Workspace）

人与 AI 共同经营的数字空间。六边形拓扑让经营团队的协作关系可视化；共享黑板是团队的经营看板；任务发布让人或 AI 都能将业务委派给最合适的经营伙伴。不是监控面板，而是经营发生的地方。

### 基因系统（Gene System）

对 AI 经营能力的投资。为 AI 装载新基因，就是为你的事业打开新的经营维度 -- 模块化能力包来自公共市场或企业私有库，按需组合，持续进化。经营什么样的事业，就装载什么样的基因。

### 弹性扩展（Elastic Scale）

经营规模的即时扩张。一键在 K8s 集群上部署 AI 经营伙伴。本地开发通过 `dev.sh` 快速启动。

## 亮点

- **赛博办公室** -- 六边形拓扑经营空间，人与 AI 共同经营、共享经营看板、委派业务
- **基因系统** -- 模块化能力投资：从公共或私有市场为 AI 装载新的经营维度
- **一键扩容** -- 端到端扩展经营规模，SSE 实时推送进度
- **多集群经营** -- 跨集群编排、健康巡检、弹性伸缩，覆盖整个经营版图

## 架构

```mermaid
flowchart LR
    subgraph ops [" 经营者 "]
        direction TB
        Human["人类经营者<br>战略 · 判断"]
        AI["AI 经营伙伴<br>执行 · 迭代"]
        Human <-.->|共同经营| AI
    end

    ops --> channels

    subgraph channels [" 经营入口 "]
        direction TB
        Portal["Web 门户"]
        DingTalk["钉钉"]
        OpenAPI["Open API"]
    end

    channels --> coopCore

    subgraph coopCore [" 共营核心 "]
        direction TB
        subgraph cyberWS [" 赛博办公室 "]
            direction LR
            Topo["六边形拓扑"]
            Board["共享黑板"]
            Tasks["任务委派"]
        end
        subgraph geneSys [" 基因系统 "]
            direction LR
            Market["公共市场"]
            EntLib["企业基因库"]
        end
    end

    coopCore --> platform

    subgraph platform [" 平台服务 "]
        direction TB
        Instance["实例生命周期"]
        Cluster["多集群编排"]
        Scale["弹性伸缩"]
        LLMProxy["LLM 路由"]
        ChPlugin["通道插件"]
    end

    platform --> infra

    subgraph infra [" 基础设施 "]
        direction TB
        K8s["Kubernetes"]
        Runtime["OpenClaw / Nanobot"]
        DB["PostgreSQL"]
        LLMs["OpenAI · Anthropic · Gemini · ..."]
    end
```



### 项目结构

```
DeskClaw/
├── nodeskclaw-portal/             # 用户门户 -- Vue 3 + Tailwind CSS
├── nodeskclaw-backend/            # API 服务 -- Python 3.12 + FastAPI + SQLAlchemy
├── nodeskclaw-llm-proxy/          # LLM 代理 -- Python + FastAPI
├── nodeskclaw-artifacts/          # Docker 镜像与部署制品
├── openclaw-channel-nodeskclaw/   # 赛博办公室经营通道插件
├── openclaw/                      # DeskClaw 运行时源码（外部）
└── vibecraft/                     # VibeCraft 源码（外部）
```

## 国际化

全栈国际化，覆盖 Portal 和 Backend 两端。

- 语言检测：`zh*` -> `zh-CN`，`en*` -> `en-US`，回退 `en-US`
- 错误展示：优先 `message_key` 本地翻译，缺失时回退 `message`
- 后端契约：`code` + `error_code` + `message_key` + `message` + `data`

## 快速开始

### Kubernetes 部署（推荐）

DeskClaw 以 Kubernetes 为主要部署方式，适用于 Staging 和 Production 环境。本地开发请使用 `dev.sh`（见下方）。

需要 K8s 集群、容器镜像仓库和外部 PostgreSQL 数据库。

#### 前置条件


| 依赖            | 说明                                            |
| ------------- | --------------------------------------------- |
| Kubernetes 集群 | 1.24+，需安装 Ingress Controller（如 ingress-nginx） |
| 容器镜像仓库        | 任意 Docker V2 仓库（Docker Hub、AWS ECR、GCR 等）     |
| PostgreSQL    | 外部数据库（如 AWS RDS、GCP Cloud SQL）                |
| kubectl       | 已配置集群访问权限                                     |
| Docker        | 用于本地构建镜像                                      |


#### 1. 配置镜像仓库和集群上下文

```bash
# 创建 deploy/.env.local（已被 .gitignore 忽略）
cat > deploy/.env.local <<'EOF'
REGISTRY="your-registry.example.com/deskclaw"
KUBE_CONTEXT="your-kubectl-context"
EOF

# 登录容器镜像仓库
docker login your-registry.example.com
```

#### 2. 准备后端环境变量

```bash
cp nodeskclaw-backend/.env.example nodeskclaw-backend/.env
# 编辑 .env，填写 DATABASE_URL、JWT_SECRET、ENCRYPTION_KEY 等
# 最少需要配置：
#   DATABASE_URL=postgresql+asyncpg://user:pass@your-rds:5432/nodeskclaw
#   JWT_SECRET=<随机密钥>
#   ENCRYPTION_KEY=<32字节base64密钥>
```

#### 3. 初始化集群

创建 Namespace、将 `.env` 上传为 K8s Secret、应用基础 Deployment + Service 清单：

```bash
./deploy/cli.sh init                    # 默认 staging namespace
./deploy/cli.sh init --prod             # 生产 namespace
```

#### 4. 构建并部署

```bash
./deploy/cli.sh deploy                  # 构建全部镜像 + 滚动更新（staging）
./deploy/cli.sh deploy --prod           # 部署到生产环境（需交互确认）
./deploy/cli.sh deploy backend          # 只部署单个组件
```

#### 5. 配置 Ingress

编辑 `deploy/k8s/ingress.yaml`，将 `example.com` 替换为实际域名，然后 apply：

```bash
kubectl --context <CTX> -n <NS> apply -f deploy/k8s/ingress.yaml
```

Ingress 定义了两个域名入口（按需配置）：


| Ingress      | 默认域名                    | 后端服务                             |
| ------------ | ----------------------- | -------------------------------- |
| Portal（用户门户） | `console.example.com`   | portal (80) + backend API (8000) |
| LLM Proxy    | `llm-proxy.example.com` | llm-proxy (80)                   |


完整 CLI 用法、镜像标签规则和 release/promote 工作流见 [deploy/README.md](deploy/README.md)。

### 本地开发

#### 前置条件


| 依赖                                                | 说明                          |
| ------------------------------------------------- | --------------------------- |
| Python >= 3.12 + [uv](https://docs.astral.sh/uv/) | 后端运行时与包管理器                  |
| Node.js >= 18 + npm                               | 前端运行时                       |
| PostgreSQL                                        | 数据库（或使用下方 `--docker-pg` 选项） |


#### 1. 配置

```bash
cd nodeskclaw-backend
cp .env.example .env
# 编辑 .env，填写 DATABASE_URL、JWT_SECRET 等
```

#### 2. 一键启动

```bash
./dev.sh              # 启动所有服务（后端 + Portal）
./dev.sh --docker-pg  # 用 Docker 启动 PostgreSQL（无需本地安装 PG）
./dev.sh --fresh      # 强制重新安装所有依赖
```

脚本自动处理依赖安装，以带颜色的日志前缀启动所有服务，Ctrl+C 统一清理。`--docker-pg` 会自动启动一个本地 PostgreSQL 容器。

服务：backend (4510) + llm-proxy (4511) + portal (4517)

手动启动（备选）

**后端：**

```bash
cd nodeskclaw-backend
uv sync
uv run uvicorn app.main:app --reload --port 4510
```

API 地址 `http://localhost:4510` | Swagger 文档 `http://localhost:4510/docs` | 首次启动自动迁移数据库。

**前端（Portal）：**

```bash
cd nodeskclaw-portal
npm install && npm run dev
```

Portal 地址 `http://localhost:4517` | `/api` 自动代理到后端。



#### 3. 登录

首次启动时，后端会在终端输出中直接打印初始管理员凭据：

```
========================================
  超管初始账号
  账号: admin
  密码: <随机生成>
  请登录后立即修改密码
========================================
```

打开 `http://localhost:4517`，使用打印的凭据登录。首次登录后会要求修改密码。

## 升级

### Kubernetes

K8s 部署由 `deploy/cli.sh` 管理，标准流程为**先部署到 Staging，再推广到 Production**。

**Staging** -- 构建镜像、推送到 registry、滚动更新 Staging namespace：

```bash
./deploy/cli.sh deploy --tag v0.9.0
```

**Production** -- 复用已推送的镜像，更新 Production namespace（不重新构建）：

```bash
./deploy/cli.sh promote v0.9.0
```

数据库迁移在新的后端 Pod 启动时自动执行。完整 CLI 用法见 [deploy/README.md](deploy/README.md)。

### Docker Compose 部署

无需 Kubernetes 的快速自部署方式：

```bash
docker compose up -d                   # CE 模式（默认）
docker compose up -d --build           # 重新构建镜像
```

### 构建镜像源加速

如果拉取依赖（PyPI、npm、Debian/Alpine 软件包）较慢，可使用镜像源预设加速构建：

```bash
# deploy/cli.sh 部署
./deploy/cli.sh deploy --mirrors cn

# docker compose 构建
docker compose --env-file deploy/mirrors/cn.env up -d --build

# DeskClaw 引擎镜像构建
./nodeskclaw-artifacts/build.sh openclaw --mirrors cn
```

可用预设在 `deploy/mirrors/` 目录下，详见 [deploy/mirrors/README.md](deploy/mirrors/README.md)。

> **注意：** Docker Hub 基础镜像拉取（`FROM python:3.12-slim` 等）无法通过构建参数加速。请在 Docker daemon 中配置 [registry mirror](https://docs.docker.com/docker-hub/mirror/)。

### 升级注意事项

- **重大版本升级前请先备份数据库。**
- 查看 [GitHub Releases](https://github.com/NoDeskAI/nodeskclaw/releases) 了解版本变更和不兼容改动。
- 如果数据库此前未由 Alembic 管理，首次升级前可能需要执行一次 `alembic stamp head`，详见[后端 README](nodeskclaw-backend/README.md)。

## 文档


|                                               |                    |
| --------------------------------------------- | ------------------ |
| [后端](nodeskclaw-backend/README.md)            | API 中枢、目录结构、环境变量   |
| [用户门户](nodeskclaw-portal/README.md)           | 经营者入口前端            |
| [构建制品](nodeskclaw-artifacts/README.md)        | DeskClaw 镜像构建与部署清单 |
| [经营通道](openclaw-channel-nodeskclaw/README.md) | 赛博办公室通信基础设施        |
| [LLM 代理](nodeskclaw-llm-proxy/README.md)      | AI 智力供给中枢          |


## 社区

- [Discord](https://discord.gg/y5NKqcP6eY) -- 加入讨论、提问、分享反馈
- [GitHub Issues](https://github.com/NoDeskAI/nodeskclaw/issues) -- Bug 报告与功能建议
- 微信 -- 扫描下方二维码加入开发者交流群；若微信群已满，请优先使用上方 Discord

<img src="docs/assets/wechat-group-qr.png" alt="微信开发者群二维码" width="200" />

## 贡献

欢迎提交 PR。详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

[Apache License 2.0](LICENSE)