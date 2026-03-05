# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## 项目概述

DeskClaw（曾用名 NoDeskClaw）— OpenClaw 实例可视化管理平台，通过 Web 界面管理 K8s 集群上的 OpenClaw 实例，支持一键部署、实时日志、集群健康巡检、飞书 SSO 登录。

采用 CE（社区版）/ EE（企业版）双版本架构：CE 为本仓库开源部分，EE 在私有 `ee/` 目录，运行时通过 `FeatureGate` 自动检测。

## 项目结构

```
NoDeskClaw/
├── nodeskclaw-frontend/           # 管理后台前端（Vue 3 + shadcn-vue + Tailwind CSS）
├── nodeskclaw-portal/              # 用户门户前端（Vue 3 + Tailwind CSS）
├── nodeskclaw-backend/             # 后端 API 服务（Python 3.12 + FastAPI）
├── nodeskclaw-llm-proxy/          # LLM Proxy 服务（Go）
├── nodeskclaw-artifacts/          # 镜像构建 & 部署制品
├── openclaw-channel-nodeskclaw/   # OpenClaw channel plugin
├── features.yaml                   # CE/EE Feature 定义
├── ee/                             # Enterprise Edition 模块（私有）
├── openclaw/                       # OpenClaw 源码（独立仓库）
└── vibecraft/                      # VibeCraft 源码（独立仓库）
```

## 常用命令

### 后端（Python）

```bash
cd nodeskclaw-backend
uv sync                    # 安装依赖（首次）
uv run uvicorn app.main:app --reload --port 8000
uv run pytest              # 运行所有测试
uv run pytest app/services/test_xxx.py::test_foo  # 运行单个测试
uv run ruff check .        # 代码检查
```

### 前端

```bash
# 管理前端
cd nodeskclaw-frontend
npm install
npm run dev               # 开发服务器 http://localhost:5173
npm run build             # 构建生产版本

# 用户门户
cd nodeskclaw-portal
npm install
npm run dev               # 开发服务器 http://localhost:5174
npm run build
npm run test              # 运行测试（vitest）
npm run test -- --run src/components/xxx.spec.ts  # 运行单个测试
npm run test:watch        # 监听模式
```

## i18n 国际化

- 覆盖范围：`nodeskclaw-portal`、`nodeskclaw-frontend`、`nodeskclaw-backend`
- 前端错误展示：优先使用后端 `message_key` 本地翻译，词条缺失时回退 `message`
- 后端失败响应：`code` + `error_code` + `message_key` + `message` + `data`

## 代码架构

- **前端**：双前端架构（管理后台 + 用户门户），共享部分类型定义，采用 `lucide-vue-next` 图标库
- **后端**：FastAPI + SQLAlchemy + asyncpg，采用 Service Layer 模式
- **K8s**：通过 kubectl 与火山云 VKE 集群交互，目标节点架构 `linux/amd64`

## 关键规则

### 必须遵守

- **禁止使用 emoji**，图标统一使用 `lucide-vue-next`
- **Docker 操作必须指定 `--platform linux/amd64`**（开发机 Apple Silicon arm64，目标集群 amd64）
- **涉及 K8s/OpenClaw 问题必须用 kubectl 实际查看集群状态**
- **所有数据删除必须软删除**（设置 `deleted_at`），唯一约束使用 Partial Unique Index
- **JSONC 配置文件解析前必须剥离行注释**
- **NFS 路径需正确转换**（容器路径 ↔ 本地挂载路径）
- **修改代码后必须搜索同源逻辑副本并同步修改**
- **部署脚本必须由用户手动执行**，禁止 AI 直接运行 `deploy/deploy.sh`
- **变更涉及 ≥1 个独立功能点时必须提示用户进入 Plan 模式**
- **K8s 操作必须指定 `--context <name>`**，禁止依赖 current-context 默认值
- **破坏性操作（删除 namespace/资源、数据库 DELETE、git force push）必须逐项确认**
- **OpenClaw 行为判断必须有源码依据**，优先读取本地 `openclaw/src/` 副本

### Git 提交规范

```
<type>(<scope>): <subject>
```

- type: feat / fix / docs / style / refactor / perf / test / chore
- subject 必须使用中文
- 禁止在 commit message 中出现 `Co-authored-by` 标签

详见 `.cursor/rules/` 下的规则文件。
