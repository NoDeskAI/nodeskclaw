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
│   │   └── settings.py       # 系统配置
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
uv run uvicorn app.main:app --reload --port 8000
```

### Docker 构建

```bash
docker build -t clawbuddy-backend:latest .
docker run -d -p 8000:8000 --env-file .env clawbuddy-backend:latest
```

## 数据库

使用火山云 RDS PostgreSQL，首次启动时通过 `Base.metadata.create_all` 自动建表，无需手动迁移。
