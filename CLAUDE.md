# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

DeskClaw（曾用名 NoDeskClaw）— DeskClaw 实例可视化管理平台，通过 Web 界面管理 K8s 集群上的 DeskClaw 实例，支持一键部署、实时日志、集群健康巡检、飞书 SSO 登录。

采用 CE（社区版）/ EE（企业版）双版本架构：CE 为本仓库开源部分，EE 在私有 `ee/` 目录。运行时通过 `FeatureGate` 判断版本：优先读取 `NODESKCLAW_EDITION` 环境变量（`ce`/`ee`），未设置时检测 `ee/` 目录是否存在。`./dev.sh ce` 会自动设置此环境变量以确保后端以 CE 模式运行。

## 项目结构

```
NoDeskClaw/
├── nodeskclaw-portal/              # 用户门户前端（CE + EE，Vue 3 + Tailwind CSS）
├── nodeskclaw-backend/             # 后端 API 服务（Python 3.12 + FastAPI）
├── nodeskclaw-llm-proxy/          # LLM Proxy 服务（Python + FastAPI）
├── nodeskclaw-artifacts/          # 镜像构建 & 部署制品
├── openclaw-channel-nodeskclaw/   # DeskClaw channel plugin
├── openclaw-channel-dingtalk/     # DingTalk channel plugin (Stream protocol)
├── features.yaml                   # CE/EE Feature 定义
├── ee/                             # Enterprise Edition 模块（私有）
│   └── nodeskclaw-frontend/       # 管理后台前端（EE-only，Vue 3 + shadcn-vue + Tailwind CSS）
├── openclaw/                       # DeskClaw 源码（独立仓库）
└── vibecraft/                      # VibeCraft 源码（独立仓库）
```

## 常用命令

### 一键启动

```bash
./dev.sh         # 自动检测：ee/ 存在 -> EE，否则 -> CE
./dev.sh ce      # 强制 CE 模式（即使存在 ee/ 目录，后端也以 CE 运行）
./dev.sh ee      # 强制 EE 模式（backend + portal + admin）
```

### Docker Compose 部署

```bash
docker compose up -d                     # CE 模式（默认）
docker compose -f docker-compose.yml -f docker-compose.ee.yml up -d  # EE 模式

# 可选：需要自定义 JWT_SECRET / 飞书 SSO 等配置时
# cp .env.example nodeskclaw-backend/.env && vi nodeskclaw-backend/.env
```

Docker Compose 部署自动配置 Docker socket 挂载和数据目录映射，支持创建 Docker 类型集群。Mac/Linux 默认使用 `$HOME/.nodeskclaw/docker-instances`，Windows 必须显式设置 `NODESKCLAW_DATA_DIR`，后端容器内 `DOCKER_DATA_DIR` 固定为 `/nodeskclaw-data`，`NODESKCLAW_EDITION` 由 compose 文件自动设置。

### 后端（Python）

```bash
cd nodeskclaw-backend
uv sync                    # 安装依赖（首次）
uv run uvicorn app.main:app --reload --port 4510
uv run pytest              # 运行所有测试
uv run pytest app/services/test_xxx.py::test_foo  # 运行单个测试
uv run ruff check .        # 代码检查
uv run ruff check --fix . # 自动修复
```

### 前端

```bash
# 管理前端（EE-only）
cd ee/nodeskclaw-frontend
npm install
npm run dev               # 开发服务器 http://localhost:4518
npm run build             # 构建生产版本

# 用户门户
cd nodeskclaw-portal
npm install
npm run dev               # 开发服务器 http://localhost:4517
npm run build
npm run test              # 运行测试（vitest）
npm run test -- --run src/components/xxx.spec.ts  # 运行单个测试
npm run test:watch        # 监听模式
```

## i18n 国际化

- 覆盖范围：`nodeskclaw-portal`、`ee/nodeskclaw-frontend`、`nodeskclaw-backend`
- 前端错误展示：优先使用后端 `message_key` 本地翻译，词条缺失时回退 `message`
- 后端失败响应：`code` + `error_code` + `message_key` + `message` + `data`

## 代码架构

- **前端**：双前端架构。`ee/nodeskclaw-frontend`（Admin 管理后台）仅 EE 版部署，CE 用户只有 `nodeskclaw-portal`（用户门户）。图标统一使用 `lucide-vue-next`
- **后端**：FastAPI + SQLAlchemy + asyncpg，采用 Service Layer 模式
- **K8s**：通过 kubectl 与 K8s 集群交互，目标节点架构 `linux/amd64`
- **DeskClaw 源码**：本地副本位于 `openclaw/src/`，用于调试和问题排查

## K8s 调试常用命令

```bash
# 查看 Pod 状态
kubectl get pods -n <namespace> --context <context-name>

# 查看 Pod 详情和 Events
kubectl describe pod <pod-name> -n <namespace> --context <context-name>

# 查看 Pod 日志
kubectl logs <pod-name> -n <namespace> --context <context-name> --tail=30

# 查看集群 Events
kubectl get events -n <namespace> --context <context-name> --sort-by='.lastTimestamp'

# 查看 Deployment 状态
kubectl get deploy -n <namespace> --context <context-name>
```

**重要**：所有 kubectl 命令必须显式指定 `--context <name>`，禁止依赖 current-context 默认值。

## 关键规则

### 必须遵守

- **禁止使用 emoji**，图标统一使用 `lucide-vue-next`
- **Docker 操作必须指定 `--platform linux/amd64`**（开发机 Apple Silicon arm64，目标集群 amd64）
- **涉及 K8s/DeskClaw 问题必须用 kubectl 实际查看集群状态**
- **所有数据删除必须软删除**（设置 `deleted_at`），唯一约束使用 Partial Unique Index
- **JSONC 配置文件解析前必须剥离行注释**
- **NFS 路径需正确转换**（容器路径 ↔ 本地挂载路径）
- **修改代码后必须搜索同源逻辑副本并同步修改**
- **部署脚本必须由用户手动执行**，禁止 AI 直接运行 `deploy/cli.sh`
- **变更涉及 ≥1 个独立功能点时必须提示用户进入 Plan 模式**
- **K8s 操作必须指定 `--context <name>`**，禁止依赖 current-context 默认值
- **破坏性操作（删除 namespace/资源、数据库 DELETE、git force push）必须逐项确认**
- **DeskClaw 行为判断必须有源码依据**，优先读取本地 `openclaw/src/` 副本
- **自动提交**：每完成一个单元性改动后必须主动提交 commit，不等用户提醒，也不允许攒多个独立改动最后一次性提交
- **禁止在代码中出现真人个人信息**，邮箱等占位统一使用 `@example.com`

### 问题排查原则

- **先查再答**：不确定的事情先查证，不凭记忆或猜测下结论
- **先读代码再写代码**：涉及第三方项目行为必须先读源码确认
- **端到端验证**：修完后必须验证问题是否真的消失
- **分层排查**：从最终现象反向逐层验证，每层都要有实际证据

### 敏感信息隔离

- 文档、设计资产默认放 `ee/` 私有仓库，CE 仅保留代码和最小必要公开文件
- `.cursor/rules/*.mdc` 禁止包含 IP、域名、Token、密钥等敏感信息
- 代码中发现真人信息必须立即替换并提交

### Git 规范

- **分支命名**：`<type>/<kebab-case-description>`（如 `feat/operation-audit`、`fix/deploy-env-serialize`），禁止无意义名称和纯日期名称
- **PR 标题**：与 commit message 格式一致 `<type>(<scope>): <中文描述>`，概括整个 PR 的变更目标

```
<type>(<scope>): <subject>
```

- type: feat / fix / docs / style / refactor / perf / test / chore
- subject 必须使用中文
- 禁止在 commit message 中出现 `Co-authored-by` 标签

详见 `.cursor/rules/` 下的规则文件。
