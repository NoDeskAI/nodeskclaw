# NoDeskClaw Backend

NoDeskClaw 管理平台后端服务，基于 FastAPI 构建，提供集群管理、实例部署、OAuth SSO 登录（飞书等可扩展）、镜像仓库管理等 API。

## 技术栈

- **语言 / 框架**: Python 3.12 + FastAPI
- **包管理**: uv
- **数据库**: 火山云 RDS PostgreSQL（SQLAlchemy asyncio + asyncpg）
- **K8s 交互**: kubernetes-asyncio
- **认证**: 飞书 OAuth 2.0 SSO + JWT
- **加密**: AES-256-GCM（KubeConfig 加密存储）

## 目录结构

```
nodeskclaw-backend/
├── app/
│   ├── main.py              # FastAPI 入口，lifespan 管理
│   ├── api/                  # 路由层
│   │   ├── router.py         # 路由聚合
│   │   ├── auth.py           # OAuth 登录、回调、token 刷新
│   │   ├── clusters.py       # 集群 CRUD
│   │   ├── deploy.py         # 部署操作
│   │   ├── events.py         # SSE 事件推送
│   │   ├── instances.py      # 实例管理
│   │   ├── channel_configs.py # Channel 配置 API
│   │   ├── registry.py       # 镜像仓库
│   │   ├── settings.py       # 系统配置
│   │   ├── workspaces.py     # 工作区 CRUD、群聊、SSE
│   │   └── templates.py      # 工作区模板 CRUD、应用
│   ├── core/                 # 核心模块
│   │   ├── config.py         # pydantic-settings 配置
│   │   ├── deps.py           # 依赖注入（DB session、当前用户等）
│   │   ├── exceptions.py     # 全局异常处理
│   │   ├── middleware.py      # 中间件
│   │   └── security.py       # JWT 签发 / 验证
│   ├── models/               # SQLAlchemy ORM 模型
│   │   ├── user.py           # 用户
│   │   ├── oauth_connection.py   # 用户 OAuth 关联（provider, provider_user_id, provider_tenant_id）
│   │   ├── org_oauth_binding.py  # 组织 OAuth 租户关联（provider, provider_tenant_id）
│   │   ├── cluster.py        # 集群
│   │   ├── instance.py       # 实例
│   │   ├── deploy_record.py  # 部署记录
│   │   ├── workspace.py      # 工作区
│   │   ├── workspace_message.py  # 工作区群聊消息
│   │   ├── workspace_member.py   # 工作区成员
│   │   ├── blackboard.py     # 工作区黑板
│   │   ├── workspace_template.py  # 工作区模板
│   │   └── system_config.py  # 系统配置（键值对）
│   ├── schemas/              # Pydantic 请求/响应 Schema
│   ├── services/             # 业务逻辑层
│   │   ├── auth_service.py       # OAuth 登录逻辑（provider 可扩展）
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
│   │   ├── llm_config_service.py # OpenClaw LLM 配置 + 系统 Channel plugin 分发
│   │   ├── channel_config_service.py # Channel 发现、配置读写、Schema 注册、自定义部署
│   │   ├── enterprise_file_service.py # 企业空间文件浏览（PodFS 只读）
│   │   ├── summary_job.py        # 自动摘要生成
│   │   └── k8s/                  # K8s 相关
│   │       ├── client_manager.py # K8s 连接池管理
│   │       ├── k8s_client.py     # K8s API 封装
│   │       ├── event_bus.py      # K8s 事件 → SSE
│   │       └── resource_builder.py # K8s YAML 资源构建
│   └── utils/
│       ├── feishu.py             # 飞书 API 工具函数（兼容旧逻辑）
│       └── oauth_providers/      # OAuth 提供方注册（可扩展）
│           ├── base.py           # OAuthProvider 基类
│           ├── registry.py       # 提供方注册与获取
│           └── feishu.py         # 飞书 OAuth 实现
├── pyproject.toml            # 项目依赖定义
├── uv.lock                   # 锁定依赖版本
├── Dockerfile                # 生产镜像构建
├── .env.example              # 环境变量模板
└── .env                      # 本地环境变量（不提交）
```

## API 概览

### 双前缀路由架构

API 路由同时挂载在两个前缀下：

- **`/api/v1/...`** — Portal（用户门户）使用，仅做登录/组织成员基础检查
- **`/api/v1/admin/...`** — 管理平台（nodeskclaw-frontend）使用，通过 `require_org_role(min_role)` 检查 `admin_memberships` 表

两个前缀使用同一套路由处理函数，不重复业务逻辑。管理前端 axios 的 baseURL 为 `/api/v1/admin`。

### 路由列表（/api/v1 公共前缀）

| 前缀 | 模块 | 说明 |
|------|------|------|
| `/api/v1/health` | 系统 | 健康检查 |
| `/api/v1/auth` | 认证 | OAuth 登录、token 刷新、密码管理 |
| `/api/v1/auth/oauth/callback` | 认证 | OAuth 登录回调（通用，支持 provider 参数） |
| `PUT /api/v1/auth/me/password` | 认证 | 修改/设置密码 |
| `/api/v1/orgs` | 组织 | 组织 CRUD、成员管理、管理员重置成员密码 |
| `/api/v1/orgs/oauth-setup` | 组织 | 组织 OAuth 设置（通用，通过 OAuth 租户绑定组织） |
| `/api/v1/clusters` | 集群 | 集群 CRUD、KubeConfig 管理 |
| `/api/v1/deploy` | 部署 | 创建部署、YAML 预览 |
| `/api/v1/instances` | 实例 | 实例列表、详情、日志、删除 |
| `/api/v1/instances/{id}/available-channels` | Channel 配置 | 扫描 Pod 返回可用 Channel |
| `/api/v1/instances/{id}/channel-configs` | Channel 配置 | 读写 Channel 配置 + 重启 |
| `/api/v1/instances/{id}/channels/install` | Channel 配置 | 安装 npm 第三方 Channel |
| `/api/v1/instances/{id}/channels/upload` | Channel 配置 | 上传 Channel 插件 |
| `/api/v1/instances/{id}/channels/deploy-repo` | Channel 配置 | 部署项目仓库 Channel |
| `/api/v1/events` | 事件 | SSE 实时推送 |
| `/api/v1/registry` | 镜像仓库 | 仓库配置、Tag 查询 |
| `/api/v1/settings` | 系统配置 | 配置读写 |
| `/api/v1/workspaces` | 工作区 | CRUD、Agent 管理、群聊、SSE |
| `/api/v1/workspaces/{ws}/chat` | 群聊 | 广播消息给所有 Agent |
| `/api/v1/workspaces/{ws}/messages` | 消息 | 工作区消息历史 |
| `/api/v1/workspaces/{ws}/events?token=` | SSE | 实时事件流（query param JWT 认证） |
| `/api/v1/workspaces/sse-token` | SSE | 签发 5 分钟短时效 SSE token |
| `/api/v1/workspaces/templates` | 工作区模板 | 列表、创建、详情、删除、应用到工作区 |
| `/api/v1/enterprise-files/agents` | 企业空间 | 列出可浏览的 Agent 实例 |
| `/api/v1/enterprise-files/agents/{id}/files` | 企业空间 | 列出 Agent 目录文件（query: path） |
| `/api/v1/enterprise-files/agents/{id}/files/content` | 企业空间 | 读取文件内容（仅文本） |
| `/api/v1/enterprise-files/agents/{id}/files/download` | 企业空间 | 下载文件 |
| `/api/v1/instances/{id}/files` | 实例文件 | 列出实例目录文件（instance admin） |
| `/api/v1/instances/{id}/files/content` | 实例文件 | 读取/写入文件内容（GET 读、PUT 写） |
| `/api/v1/instances/{id}/files/download` | 实例文件 | 下载文件 |

### RBAC 双表职责分离

管理平台和 Portal 的角色完全独立，由两张表管理：

| 表 | 用途 | 谁写 | 谁读 |
|----|------|------|------|
| `org_memberships` | Portal 组织角色（admin/member） | OAuth 登录自动创建 | Portal |
| `admin_memberships` | 管理平台角色（member/operator/admin） | 管理员手动添加 | Admin |

管理平台角色层级（`admin_memberships.role`）：

| 角色 | 层级值 | 含义 |
|------|--------|------|
| member | 10 | 只读：Dashboard、实例详情/日志/监控/事件 |
| operator | 20 | 运维操作：部署、重启、扩缩容、配置变更 |
| admin | 30 | 完全权限：集群管理、系统设置、基因运营、成员管理 |

`is_super_admin` 绕过所有管理平台权限检查。无 `AdminMembership` 记录的用户无法访问管理平台。

启动后访问 `http://localhost:8000/docs` 查看完整 API 文档（Swagger UI）。

## 错误响应契约（i18n 对齐）

失败响应统一结构：

```json
{
  "code": 40101,
  "error_code": 40101,
  "message_key": "errors.auth.token_invalid",
  "message": "Token 无效或已过期",
  "data": null
}
```

- `error_code`（错误码）出现即表示失败
- `message_key`（文案键）供前端 i18n（国际化）翻译
- `message`（文案）为后端可读提示（当前语言）
- 不再返回 `detail`（错误详情字段）
- HTTP `status_code`（状态码）保持语义化，不统一改为 200

## 本地开发

### 前置条件

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/) 已安装
- 火山云 RDS PostgreSQL 可访问
- 飞书开放平台应用已创建（需要 App ID 和 App Secret）

### 安装依赖

```bash
cd nodeskclaw-backend
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
| `FEISHU_APP_ID` | 飞书 OAuth 提供方 App ID |
| `FEISHU_APP_SECRET` | 飞书 OAuth 提供方 App Secret |
| `FEISHU_REDIRECT_URI` | 飞书 OAuth 回调地址 |

未来接入其他 OAuth 提供方（如钉钉、企业微信等）时，需在配置中新增对应 `*_APP_ID`、`*_APP_SECRET` 等变量。

可选项：

| 变量 | 说明 |
|------|------|
| `GATEWAY_KUBECONFIG` | 本地开发时网关集群（infra）的 kubeconfig 文件路径。生产环境使用 in-cluster config，无需配置 |

### 启动

```bash
uv run uvicorn app.main:app --reload --port 8000 --timeout-graceful-shutdown 3
```

### Docker 构建

后端镜像的 build context 是**项目根目录**（非 `nodeskclaw-backend/`），因为镜像需要包含 `openclaw-channel-nodeskclaw/` 插件源码（工作区 Agent 通信用）。

```bash
cd /path/to/NoDeskClaw
docker build --platform linux/amd64 -f nodeskclaw-backend/Dockerfile -t nodeskclaw-backend:latest .
docker run -d -p 8000:8000 --env-file nodeskclaw-backend/.env nodeskclaw-backend:latest
```

生产环境通过统一部署脚本构建：`./deploy/deploy.sh backend`

## 日志

后端启用了本地滚动日志，日志文件位于 `logs/` 目录：

```
logs/
├── nodeskclaw.log       # 当前日志文件
├── nodeskclaw.log.1     # 上一个滚动文件
├── nodeskclaw.log.2     # ...
└── ...                 # 最多保留 5 个历史文件
```

- **单文件大小**：10MB，超出后自动滚动
- **保留数量**：5 个历史文件（加当前文件共约 60MB）
- **日志格式**：`时间 级别 [模块名] 消息`
- **输出目标**：同时输出到文件和控制台

`logs/` 目录已在 `.gitignore` 中排除，不会提交到仓库。

## 数据库

使用火山云 RDS PostgreSQL，首次启动时通过 `Base.metadata.create_all` 自动建表，无需手动迁移。

### OAuth 相关表（重构后）

| 表名 | 说明 |
|------|------|
| `user_oauth_connections` | 用户与 OAuth 提供方的关联（provider、provider_user_id、provider_tenant_id） |
| `org_oauth_bindings` | 组织与 OAuth 租户的关联（provider、provider_tenant_id） |

原先的 `users.feishu_uid`、`organizations.feishu_tenant_key` 等字段已移除，统一迁移至上述表。

### 默认基因/基因组初始化

- 启动流程不再自动 seed（初始化写入）默认 `Gene`（基因）/`Genome`（基因组）数据。
- 默认数据需通过一次性 SQL（结构化查询语言）显式回填到数据库。
- 回填建议使用 `ON CONFLICT ... DO NOTHING`（冲突跳过）策略，按 `slug`（唯一标识）去重，避免覆盖现有记录。

### 软删除

所有数据模型（User、Cluster、Instance、DeployRecord、SystemConfig）均采用逻辑删除，通过 `deleted_at` 字段标记：

- `deleted_at = NULL`：正常记录
- `deleted_at = 时间戳`：已删除记录

**数据库迁移**：升级到软删除版本后，首次启动时后端会自动检测并为已有表添加 `deleted_at` 列和索引，无需手动执行 SQL。
