# ClawBuddy Backend

ClawBuddy 管理平台后端服务，基于 FastAPI 构建，提供集群管理、实例部署、飞书 SSO 登录、镜像仓库管理等 API。

## 技术栈

- **语言 / 框架**: Python 3.12 + FastAPI
- **包管理**: uv
- **数据库**: 火山云 RDS PostgreSQL（SQLAlchemy asyncio + asyncpg）
- **K8s 交互**: kubernetes-asyncio
- **认证**: 飞书 OAuth 2.0 SSO + JWT
- **加密**: AES-256-GCM（KubeConfig 加密存储）

## 目录结构

```
claw-buddy-backend/
├── app/
│   ├── main.py              # FastAPI 入口，lifespan 管理
│   ├── api/                  # 路由层
│   │   ├── router.py         # 路由聚合
│   │   ├── auth.py           # 飞书 SSO 登录
│   │   ├── clusters.py       # 集群 CRUD
│   │   ├── deploy.py         # 部署操作
│   │   ├── events.py         # SSE 事件推送
│   │   ├── instances.py      # 实例管理
│   │   ├── registry.py       # 镜像仓库
│   │   ├── settings.py       # 系统配置
│   │   └── workspaces.py     # 工作区 CRUD、群聊、SSE
│   ├── core/                 # 核心模块
│   │   ├── config.py         # pydantic-settings 配置
│   │   ├── deps.py           # 依赖注入（DB session、当前用户等）
│   │   ├── exceptions.py     # 全局异常处理
│   │   ├── middleware.py      # 中间件
│   │   └── security.py       # JWT 签发 / 验证
│   ├── models/               # SQLAlchemy ORM 模型
│   │   ├── user.py           # 用户
│   │   ├── cluster.py        # 集群
│   │   ├── instance.py       # 实例
│   │   ├── deploy_record.py  # 部署记录
│   │   ├── workspace.py      # 工作区
│   │   ├── workspace_message.py  # 工作区群聊消息
│   │   ├── workspace_member.py   # 工作区成员
│   │   ├── blackboard.py     # 工作区黑板
│   │   └── system_config.py  # 系统配置（键值对）
│   ├── schemas/              # Pydantic 请求/响应 Schema
│   ├── services/             # 业务逻辑层
│   │   ├── auth_service.py       # 飞书 SSO 逻辑
│   │   ├── cluster_service.py    # 集群管理
│   │   ├── deploy_service.py     # 部署编排
│   │   ├── instance_service.py   # 实例操作
│   │   ├── registry_service.py   # 镜像仓库查询
│   │   ├── config_service.py     # 系统配置读写
│   │   ├── health_checker.py     # 集群健康巡检
│   │   ├── workspace_service.py  # 工作区 CRUD + Agent 管理
│   │   ├── workspace_message_service.py  # 群聊消息记录 + 上下文构建
│   │   ├── collaboration_service.py      # 协作消息处理（由 SSE 监听器调用）
│   │   ├── sse_listener.py               # OpenClaw 实例 SSE 长连接（按 Ingress 域名）
│   │   ├── llm_config_service.py # OpenClaw 配置 + Channel plugin 分发
│   │   ├── summary_job.py        # 自动摘要生成
│   │   └── k8s/                  # K8s 相关
│   │       ├── client_manager.py # K8s 连接池管理
│   │       ├── k8s_client.py     # K8s API 封装
│   │       ├── event_bus.py      # K8s 事件 → SSE
│   │       └── resource_builder.py # K8s YAML 资源构建
│   └── utils/
│       └── feishu.py         # 飞书 API 工具函数
├── pyproject.toml            # 项目依赖定义
├── uv.lock                   # 锁定依赖版本
├── Dockerfile                # 生产镜像构建
├── .env.example              # 环境变量模板
└── .env                      # 本地环境变量（不提交）
```

## API 概览

| 前缀 | 模块 | 说明 |
|------|------|------|
| `/api/v1/health` | 系统 | 健康检查 |
| `/api/v1/auth` | 认证 | 飞书 SSO 登录、token 刷新 |
| `/api/v1/clusters` | 集群 | 集群 CRUD、KubeConfig 管理 |
| `/api/v1/deploy` | 部署 | 创建部署、YAML 预览 |
| `/api/v1/instances` | 实例 | 实例列表、详情、日志、删除 |
| `/api/v1/events` | 事件 | SSE 实时推送 |
| `/api/v1/registry` | 镜像仓库 | 仓库配置、Tag 查询 |
| `/api/v1/settings` | 系统配置 | 配置读写 |
| `/api/v1/workspaces` | 工作区 | CRUD、Agent 管理、群聊、SSE |
| `/api/v1/workspaces/{ws}/chat` | 群聊 | 广播消息给所有 Agent |
| `/api/v1/workspaces/{ws}/messages` | 消息 | 工作区消息历史 |
| `/api/v1/workspaces/{ws}/events?token=` | SSE | 实时事件流（query param JWT 认证） |
| `/api/v1/workspaces/sse-token` | SSE | 签发 5 分钟短时效 SSE token |

启动后访问 `http://localhost:8000/docs` 查看完整 API 文档（Swagger UI）。

## 本地开发

### 前置条件

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/) 已安装
- 火山云 RDS PostgreSQL 可访问
- 飞书开放平台应用已创建（需要 App ID 和 App Secret）

### 安装依赖

```bash
cd claw-buddy-backend
uv sync
```

### 配置环境变量

复制 `.env.example` 为 `.env`，填入实际值：

```bash
cp .env.example .env
```

必填项：

| 变量 | 说明 |
|------|------|
| `DATABASE_URL` | PostgreSQL 连接串，格式 `postgresql+asyncpg://user:pass@host:5432/dbname` |
| `JWT_SECRET` | JWT 签名密钥，生产环境务必替换 |
| `ENCRYPTION_KEY` | KubeConfig AES 加密密钥（32 字节 base64） |
| `FEISHU_APP_ID` | 飞书应用 App ID |
| `FEISHU_APP_SECRET` | 飞书应用 App Secret |
| `FEISHU_REDIRECT_URI` | 飞书 OAuth 回调地址 |

### 启动

```bash
uv run uvicorn app.main:app --reload --port 8000 --timeout-graceful-shutdown 3
```

### Docker 构建

```bash
docker build -t clawbuddy-backend:latest .
docker run -d -p 8000:8000 --env-file .env clawbuddy-backend:latest
```

## 日志

后端启用了本地滚动日志，日志文件位于 `logs/` 目录：

```
logs/
├── clawbuddy.log       # 当前日志文件
├── clawbuddy.log.1     # 上一个滚动文件
├── clawbuddy.log.2     # ...
└── ...                 # 最多保留 5 个历史文件
```

- **单文件大小**：10MB，超出后自动滚动
- **保留数量**：5 个历史文件（加当前文件共约 60MB）
- **日志格式**：`时间 级别 [模块名] 消息`
- **输出目标**：同时输出到文件和控制台

`logs/` 目录已在 `.gitignore` 中排除，不会提交到仓库。

## 数据库

使用火山云 RDS PostgreSQL，首次启动时通过 `Base.metadata.create_all` 自动建表，无需手动迁移。

### 默认基因/基因组初始化

- 启动流程不再自动 seed（初始化写入）默认 `Gene`（基因）/`Genome`（基因组）数据。
- 默认数据需通过一次性 SQL（结构化查询语言）显式回填到数据库。
- 回填建议使用 `ON CONFLICT ... DO NOTHING`（冲突跳过）策略，按 `slug`（唯一标识）去重，避免覆盖现有记录。

### 软删除

所有数据模型（User、Cluster、Instance、DeployRecord、SystemConfig）均采用逻辑删除，通过 `deleted_at` 字段标记：

- `deleted_at = NULL`：正常记录
- `deleted_at = 时间戳`：已删除记录

**数据库迁移**：升级到软删除版本后，首次启动时后端会自动检测并为已有表添加 `deleted_at` 列和索引，无需手动执行 SQL。
