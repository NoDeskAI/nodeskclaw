[English](README.md)

# DeskClaw

**AI 劳动力，一站式编排。** 在 Kubernetes 上部署、管理和弹性伸缩 AI Agent -- 尽在一块屏幕。

DeskClaw 是 AI 员工的可视化编排平台。通过赛博办公室（Cyber Workspace）将多个 AI Agent 组织为协作团队，赋予基因（Gene）能力体系，在 K8s 集群上一键部署、实时监控、弹性伸缩。

## 亮点

- **赛博办公室** -- 六边形拓扑工作区，AI 员工自动协作、共享黑板、发布任务
- **基因系统** -- 模块化能力市场，为 Agent 热装载技能，支持企业私有化基因
- **一键部署** -- 从创建到上线，全流程可视化，SSE 实时推送部署进度
- **多集群管理** -- 跨集群实例编排，健康巡检，弹性扩缩
- **飞书 SSO** -- 企业级身份认证，组织架构自动同步

## 社区版 / 企业版

采用社区版（CE）/ 企业版（EE）双版本架构：

| | 社区版（CE） | 企业版（EE） |
|---|---|---|
| 协议 | Apache 2.0 | 商业许可 |
| 核心功能 | 实例部署、集群管理、日志监控、基因市场 | CE 全部 + 多组织、计费、高级审计 |
| 代码 | 本仓库 | 私有 `ee/` 目录 |

运行时通过 `FeatureGate` 自动检测 -- `ee/` 存在即 EE，否则 CE。功能清单定义在 `features.yaml`。

**技术实现**：后端 Factory 抽象层 + Hook 事件总线；前端 Stub + Vite Alias Override。

## 项目结构

```
DeskClaw/
├── nodeskclaw-portal/             # 用户门户 -- Vue 3 + Tailwind CSS（CE + EE）
├── nodeskclaw-backend/            # API 服务 -- Python 3.12 + FastAPI + SQLAlchemy
├── nodeskclaw-llm-proxy/          # LLM 代理 -- Python + FastAPI
├── nodeskclaw-artifacts/          # Docker 镜像与部署制品
├── openclaw-channel-nodeskclaw/   # 工作区 Agent 通道插件
├── features.yaml                  # CE/EE 功能注册表
├── ee/                            # 企业版（私有）
│   └── nodeskclaw-frontend/      # 管理后台 -- Vue 3 + shadcn-vue（EE-only）
├── openclaw/                      # DeskClaw 运行时源码（外部）
└── vibecraft/                     # VibeCraft 源码（外部）
```

## 国际化

全栈国际化，覆盖 Portal、Admin、Backend 三端。

- 语言检测：`zh*` -> `zh-CN`，`en*` -> `en-US`，回退 `en-US`
- 错误展示：优先 `message_key` 本地翻译，缺失时回退 `message`
- 后端契约：`code` + `error_code` + `message_key` + `message` + `data`

## 快速开始

### 前置条件

| 依赖 | 说明 |
|---|---|
| Python >= 3.12 + [uv](https://docs.astral.sh/uv/) | 后端运行时与包管理器 |
| Node.js >= 18 + npm | 前端运行时 |
| PostgreSQL | 数据库 |
| 飞书应用 | SSO 登录（App ID + App Secret） |

### 1. 配置

```bash
cd nodeskclaw-backend
cp .env.example .env
# 编辑 .env，填写以下必填项
```

| 变量 | 说明 |
|---|---|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/dbname` |
| `JWT_SECRET` | JWT 签名密钥 |
| `ENCRYPTION_KEY` | KubeConfig AES 密钥（32 字节 base64） |
| `FEISHU_APP_ID` | 飞书应用 App ID |
| `FEISHU_APP_SECRET` | 飞书应用 App Secret |
| `FEISHU_REDIRECT_URI` | `http://localhost:4518/api/v1/auth/feishu/callback` |

### 2. 一键启动

```bash
./dev.sh          # 自动检测：ee/ 目录存在则 EE 模式，否则 CE 模式
./dev.sh ce       # 强制 CE 模式（后端 + Portal）
./dev.sh ee       # 强制 EE 模式（后端 + Portal + Admin）
./dev.sh --fresh  # 强制重新安装所有依赖
```

脚本自动安装依赖、启动所有服务（带颜色日志前缀），Ctrl+C 统一退出。

| 模式 | 服务 | 端口 |
|------|------|------|
| CE | 后端 + Portal | 8000, 4517 |
| EE | 后端 + Portal + Admin | 8000, 4517, 4518 |

### 手动启动（替代方式）

<details>
<summary>逐个启动各服务</summary>

**后端：**

```bash
cd nodeskclaw-backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

API 地址 `http://localhost:8000` | Swagger 文档 `http://localhost:8000/docs` | 首次启动自动迁移数据库。

**Portal 前端：**

```bash
cd nodeskclaw-portal
npm install && npm run dev
```

Portal 地址 `http://localhost:4517` | `/api` 自动代理到后端。

**Admin 前端（EE-only）：**

```bash
cd ee/nodeskclaw-frontend
npm install && npm run dev
```

Admin 地址 `http://localhost:4518` | `/api` 和 `/stream` 自动代理到后端。

</details>

### 3. 开始使用

打开 `http://localhost:4517`（Portal）或 `http://localhost:4518`（Admin，EE）登录。

> 飞书回调地址：`http://localhost:4518/api/v1/auth/feishu/callback`

## 文档

| | |
|---|---|
| [后端](nodeskclaw-backend/README.md) | API 概览、目录结构、环境变量 |
| [构建制品](nodeskclaw-artifacts/README.md) | DeskClaw 镜像构建与 Dockerfile |
| [通道插件](openclaw-channel-nodeskclaw/README.md) | 工作区 Agent 协作插件 |

## 贡献

欢迎提交 PR。详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

[Apache License 2.0](LICENSE)
