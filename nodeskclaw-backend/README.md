# NoDeskClaw Backend

NoDeskClaw 管理平台后端服务，基于 FastAPI 构建，提供集群管理、实例部署、OAuth SSO 登录（飞书等可扩展）、镜像仓库管理等 API。

## 技术栈

- **语言 / 框架**: Python 3.12 + FastAPI
- **包管理**: uv
- **数据库**: PostgreSQL（SQLAlchemy asyncio + asyncpg）
- **K8s 交互**: kubernetes-asyncio
- **认证**: 飞书 OAuth 2.0 SSO + JWT
- **加密**: AES-256-GCM（KubeConfig 加密存储）

## 目录结构

```
nodeskclaw-backend/
├── alembic/                 # Alembic 数据库迁移
│   ├── env.py               # 迁移环境配置
│   ├── versions/            # 迁移文件
│   └── script.py.mako       # 迁移文件模板
├── alembic.ini              # Alembic 配置
├── app/
│   ├── main.py              # FastAPI 入口，lifespan 管理
│   ├── startup/             # 启动时初始化
│   │   └── seed.py          # 幂等种子数据
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
│   │   ├── templates.py      # 工作区模板 CRUD、应用
│   │   ├── observability.py  # 可观测性 API（消息追踪/热力图/死信/熔断/事件溯源）
│   │   └── runtime_admin.py  # 运行时管理 API（节点类型/注册表/Pipeline 查询）
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
│   │   ├── instance.py       # 实例（含 compute_provider/runtime 字段）
│   │   ├── deploy_record.py  # 部署记录
│   │   ├── workspace.py      # 工作区
│   │   ├── workspace_message.py  # 工作区群聊消息
│   │   ├── workspace_member.py   # 工作区成员
│   │   ├── blackboard.py     # 工作区黑板
│   │   ├── workspace_template.py  # 工作区模板
│   │   ├── system_config.py  # 系统配置（键值对）
│   │   ├── org_smtp_config.py  # 组织 SMTP 邮件配置
│   │   ├── node_type.py      # 节点类型定义（运行时平台 v2）
│   │   ├── node_card.py      # 统一节点卡片（运行时平台 v2）
│   │   ├── message_queue.py  # 消息队列项
│   │   ├── event_log.py      # 事件溯源日志
│   │   ├── delivery_log.py   # 投递日志
│   │   ├── sse_connection.py # SSE 连接注册
│   │   ├── idempotency_cache.py  # 幂等缓存
│   │   ├── circuit_state.py  # 熔断器状态
│   │   ├── dead_letter.py    # 死信队列
│   │   └── message_schema.py # 消息 Schema 版本
│   ├── schemas/              # Pydantic 请求/响应 Schema
│   ├── services/             # 业务逻辑层
│   │   ├── auth_service.py       # OAuth 登录逻辑（provider 可扩展）、统一账号/验证码登录
│   │   ├── email_service.py     # 邮件发送服务（aiosmtplib，验证码邮件 + 测试邮件）
│   │   ├── cluster_service.py    # 集群管理
│   │   ├── deploy_service.py     # 部署编排
│   │   ├── instance_service.py   # 实例操作
│   │   ├── registry_service.py   # 镜像仓库查询
│   │   ├── config_service.py     # 系统配置读写
│   │   ├── health_checker.py     # 集群健康巡检
│   │   ├── workspace_service.py  # 工作区 CRUD + Agent 管理
│   │   ├── workspace_message_service.py  # 群聊消息记录 + 上下文构建
│   │   ├── collaboration_service.py      # 协作消息处理（由 SSE 监听器调用）
│   │   ├── sse_listener.py               # DeskClaw 实例 SSE 长连接（按 Ingress 域名）
│   │   ├── llm_config_service.py # DeskClaw LLM 配置 + 系统 Channel plugin 分发
│   │   ├── channel_config_service.py # Channel 发现、配置读写、Schema 注册、自定义部署
│   │   ├── enterprise_file_service.py # 企业空间文件浏览（PodFS 只读）
│   │   ├── summary_job.py        # 自动摘要生成
│   │   ├── runtime/              # 运行时平台 v2（五层架构）
│   │   │   ├── registries/       # 六大注册表（NodeType/Transport/Runtime/Compute/ContextBridge/Channel）
│   │   │   ├── adapters/         # Agent 运行时适配器（OpenClaw/ClaudeCode/GenericHTTP）
│   │   │   ├── context_bridges/  # 上下文注入桥接（ChannelPlugin/SystemPrompt/MCP）
│   │   │   ├── compute/          # 计算资源提供者（K8s/Docker/Process）
│   │   │   ├── transport/        # 消息投递适配器（Agent/Channel）
│   │   │   ├── messaging/        # 消息系统核心
│   │   │   │   ├── envelope.py   # CloudEvents 对齐的 MessageEnvelope
│   │   │   │   ├── bus.py        # MessageBus 单例 + Middleware Pipeline
│   │   │   │   ├── queue.py      # PGMQ 消息队列（WFQ + ACK/Retry + DLQ + NOTIFY）
│   │   │   │   ├── queue_consumer.py  # NOTIFY 驱动队列消费者 + 轮询兜底
│   │   │   │   ├── event_log.py  # 事件溯源日志
│   │   │   │   ├── middlewares/  # 中间件（Validation/Semantic/Routing/Transport/CircuitBreaker/RateLimit/Audit/Metrics）
│   │   │   │   └── ingestion/    # 接入层适配器（Portal/Agent/Feishu/Cron）
│   │   │   ├── hooks/            # NodeHookManager 生命周期钩子
│   │   │   ├── node_card.py      # NodeCard 统一节点业务逻辑
│   │   │   ├── sse_registry.py   # SSE 连接注册表（跨实例）
│   │   │   ├── pg_notify.py      # PG LISTEN/NOTIFY 集成
│   │   │   ├── telemetry.py      # OpenTelemetry 集成
│   │   │   ├── security.py       # 安全模型（RBAC/隔离/沙箱）
│   │   │   ├── companion.py      # Companion Process 客户端（CLI Agent HTTP 包装）
│   │   │   ├── route_cache.py    # RouteTable 拓扑缓存 + PG NOTIFY 失效
│   │   │   ├── retention.py      # 数据保留策略（EventLog/Queue 清理）
│   │   │   ├── failure_recovery.py # 实例故障恢复
│   │   │   └── migration.py      # 数据迁移脚本（旧表 → node_cards）
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
- **`/api/v1/admin/...`** — 管理平台（ee/nodeskclaw-frontend）使用，通过 `require_org_role(min_role)` 检查 `admin_memberships` 表

两个前缀使用同一套路由处理函数，不重复业务逻辑。管理前端 axios 的 baseURL 为 `/api/v1/admin`。

### 路由列表（/api/v1 公共前缀）

| 前缀 | 模块 | 说明 |
|------|------|------|
| `/api/v1/health` | 系统 | 健康检查 |
| `/api/v1/auth` | 认证 | OAuth 登录、统一账号/验证码登录、token 刷新、密码管理 |
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

Admin 后台权限**严格依赖 `AdminMembership`**，`is_super_admin` 不再自动放行。CE Portal 超管和 EE Admin 平台管理员是**独立的账号体系**，由不同的种子函数分别初始化。

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

## 运行时平台 v2 架构

### 消息流转

所有工作区消息（用户聊天、Agent 协作、系统通知）统一通过 MessageBus 管道处理：

```
入口（Portal/Agent SSE/Feishu/System）
  → Ingestion Adapter（构建 MessageEnvelope）
  → MessageBus.publish()
  → Middleware Pipeline:
      Metrics → Validation → ContentFilter → RateLimit → Semantic → Routing → CircuitBreaker → Transport → Audit
  → TransportAdapter（Agent/Channel）投递到目标节点
```

### Envelope 协议

MessageEnvelope 遵循 CloudEvents 1.0 规范，扩展字段：

- **SenderType**: user / agent / system / cron / external
- **IntentType**: chat / collaborate / notify / command / ack
- **Priority**: critical / normal / background（WFQ 权重 8:4:1）
- **Urgency**: immediate / normal / deferred / scheduled
- **MessageRouting**: mode / target / targets / exclude / max_hops / ttl / visited / priority
- **MessageScheduling**: delivery_mode / urgency / delay_seconds / deadline
- **ResponseChunk**: type / content / is_done / is_error / timestamp

### 中间件管道

| 中间件 | 职责 |
|--------|------|
| MetricsMiddleware | OpenTelemetry 埋点（PRODUCER span + 计数器） |
| ValidationMiddleware | Schema 校验 + 幂等性（INSERT ON CONFLICT）+ 工作区隔离 |
| ContentFilterMiddleware | 内容合规过滤（CE no-op，EE 通过 FeatureGate 注入策略） |
| RateLimitMiddleware | 发送方令牌桶限流 |
| SemanticMiddleware | 8 条规则链：mention→CRITICAL, NOTIFY/CRON→BACKGROUND, ACK→DEFERRED, delay→SCHEDULED, EXTERNAL→升级, collaborate→NORMAL, routing.priority 覆盖 |
| RoutingMiddleware | 发送方 BFS + anycast 最少队列选择 + 语义评分 + 背压过滤 + TTL/visited 限制 + 拓扑版本追踪 |
| CircuitBreakerMiddleware | 熔断保护（OPEN 跳过，HALF_OPEN 探测），恢复时自动重投 recoverable 死信 |
| TransportMiddleware | 投递 + 优先级分级接收方速率限制 + 熔断状态更新 + 拓扑版本检测 + Edge 指标 + 失败重试/DLQ |
| AuditMiddleware | 8 种事件全生命周期记录 + backend_instance_id 追踪 |

### 可靠性

- **PGMQ**: PostgreSQL 消息队列 + WFQ 虚拟时间调度防饥饿 + PG NOTIFY 驱动即时消费 + 5s 轮询兜底
- **ACK/Retry/DLQ**: 指数退避 + jitter 抖动重试（max 3 次），不可恢复错误（node_card_not_found 等）直接进 DLQ
- **熔断器**: 三态（CLOSED/OPEN/HALF_OPEN），恢复时自动重投 recoverable 死信
- **背压**: 按队列深度分级（FULL/NORMAL_ONLY/CRITICAL_ONLY/NONE）
- **幂等**: INSERT ON CONFLICT DO NOTHING 原子去重
- **拓扑版本**: 路由缓存带版本号，投递失败时检测版本变更
- **离线消息**: Agent 重连时自动重放积压消息（on_agent_joined → _replay_pending_messages）

### SSE 跨实例推送

- 每个后端实例启动时生成 `BACKEND_INSTANCE_ID`
- SSE 连接注册到 `sse_connections` 表
- `broadcast_event` 本地直推 + PG NOTIFY `sse_push:{instance_id}` 跨实例转发
- 远端订阅者收到通知后推入本地 `_workspace_queues`

### delegate/escalate 协议

Agent 响应以 `delegate:<target>` 或 `escalate:<target>` 开头时，自动构建新 envelope 转发给目标 Agent 或 Human。协作深度限制 `MAX_COLLABORATION_DEPTH=5`，超限拒绝。delegation 链通过 `routing.visited` 追踪已访问节点，`causationid`/`correlationid` 追踪因果链。

### Channel 降级链

Feishu 私聊 → Feishu 群聊 → SSE → 离线队列（enqueue）。每级失败自动尝试下一级。

### 计算环境

deploy_service 根据 Instance.compute_provider 字段分发部署：

| compute_provider | 实现 | 场景 |
|------------------|------|------|
| k8s（默认） | 内置 K8s 部署管道 + rolling update | 生产环境 |
| docker | DockerComputeProvider | 本地开发/测试（端口 13000 起，数据在 ~/.nodeskclaw/docker-instances/） |
| process | ProcessComputeProvider | 单机调试 |

Docker 部署常量定义在 `app/services/docker_constants.py`。远程文件操作通过 `DockerFS`（主机直接读写）或 `PodFS`（kubectl exec）完成，由 `remote_fs()` 按 `compute_provider` 自动分发。

### Agent 生命周期

- 双层健检：心跳扫描 + RuntimeAdapter.health_check → 更新 NodeCard.status
- 热切换：K8sComputeProvider.update_instance 触发 rolling update
- 状态重建：`/messages/{id}/reconstruct` 从 EventLog 重建消息生命周期

### 启动时初始化

lifespan 中依次初始化：OpenTelemetry → NodeType 同步到 DB → NodeHook 注册 → PG LISTEN/NOTIFY 订阅（topology_changed + sse_push + message_enqueued）→ 心跳扫描（含 Agent 健康检查）→ 队列消费者（NOTIFY 驱动 + 轮询兜底）→ 数据迁移。

### 数据保留策略

| 层级 | 时间范围 | 处理 |
|------|---------|------|
| Hot | 0–30 天 | 保留完整 JSONB data |
| Warm | 30–90 天 | 清除 data 列，只保留 event_type/message_id/trace_id |
| Cold | >90 天 | 软删除 |

## 本地开发

### 前置条件

- Python >= 3.12
- [uv](https://docs.astral.sh/uv/) 已安装
- PostgreSQL 可访问
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

CE 超管配置（可选）：

| 变量 | 说明 |
|------|------|
| `INIT_ADMIN_ACCOUNT` | 超管的 username，默认 `admin`。留空则跳过自动创建 |
| `RESET_ADMIN_PASSWORD` | 设为 `true` 后重启可强制重置超管密码。默认 `false` |

EE 平台管理员配置（仅 EE 模式生效）：

| 变量 | 说明 |
|------|------|
| `INIT_EE_ADMIN_ACCOUNT` | EE Admin 后台管理员 username，默认 `deskclaw-admin`。留空跳过，不能与 `INIT_ADMIN_ACCOUNT` 相同 |
| `RESET_EE_ADMIN_PASSWORD` | 设为 `true` 后重启可强制重置 EE 管理员密码。默认 `false` |

可选项：

| 变量 | 说明 |
|------|------|
| `LOGIN_EMAIL_WHITELIST` | 允许登录/注册的邮箱域名白名单（逗号分隔，如 `nodeskai.com`），为空则不限制 |
| `GATEWAY_KUBECONFIG` | 本地开发时网关集群（infra）的 kubeconfig 文件路径。生产环境使用 in-cluster config，无需配置 |
| `EGRESS_DENY_CIDRS` | AI 员工 Pod Egress NetworkPolicy 中拒绝访问的 CIDR 列表（逗号分隔），默认 `10.0.0.0/8,172.16.0.0/12,192.168.0.0/16` |
| `EGRESS_ALLOW_PORTS` | AI 员工 Pod 公网出站允许的 TCP 端口（逗号分隔），默认 `80,443` |

### 启动

推荐使用项目根目录的一键启动脚本（同时启动后端和前端）：

```bash
./dev.sh      # 自动检测 CE/EE
./dev.sh ce   # 强制 CE 模式
./dev.sh ee   # 强制 EE 模式
```

单独启动后端：

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

使用 PostgreSQL，Schema 变更由 [Alembic](https://alembic.sqlalchemy.org/) 管理。

### 数据库迁移（Alembic）

项目使用 Alembic（SQLAlchemy 官方迁移工具）管理所有 Schema 变更。迁移文件位于 `alembic/versions/`。

#### 日常开发流程

```
修改 Model → 自动生成迁移 → Review → Commit → 启动时自动应用
```

1. **修改 Model**：编辑 `app/models/` 下的 SQLAlchemy 模型

2. **生成迁移文件**：
   ```bash
   uv run alembic revision --autogenerate -m "描述（如：instances 新增 gpu_type 列）"
   ```
   Alembic 会对比当前 Model 和数据库 Schema，自动生成 `alembic/versions/xxx_描述.py`

3. **Review 生成的迁移文件**：
   - 检查 `upgrade()` 和 `downgrade()` 是否正确
   - autogenerate 无法检测**列重命名**（会生成 DROP + ADD），需手动改为 `op.alter_column(..., new_column_name=...)`
   - Partial Unique Index（`postgresql_where`）需确认是否被正确识别

4. **Commit 迁移文件**：迁移文件是代码的一部分，必须提交到 Git

5. **应用迁移**（自动）：
   - `./dev.sh` 启动时自动执行 `alembic upgrade head`
   - Docker 容器启动时同样自动执行
   - 也可以手动执行：`uv run alembic upgrade head`

#### 常用命令

| 场景 | 命令 |
|------|------|
| 改了 Model，生成迁移 | `uv run alembic revision --autogenerate -m "描述"` |
| 手动应用迁移 | `uv run alembic upgrade head` |
| 查看当前版本 | `uv run alembic current` |
| 查看迁移历史 | `uv run alembic history --verbose` |
| 回滚上一个迁移 | `uv run alembic downgrade -1` |
| 生成空迁移（手写数据迁移用） | `uv run alembic revision -m "描述"` |

#### 多人协作

两人同时生成迁移会产生分叉（两个迁移文件的 `down_revision` 指向同一个版本），合并分支后需要：

```bash
uv run alembic merge -m "merge branches" <rev1> <rev2>
```

#### 版本发布 / 开源用户升级

- 每次 release 镜像中包含最新的迁移文件
- 容器启动时 `alembic upgrade head` 自动将数据库从任意版本升级到最新
- 开源用户拉取新版镜像后重启即可，无需手动执行 SQL
- **生产库首次接入 Alembic**：需手动执行一次 `alembic stamp head` 标记当前版本

#### 注意事项

- **autogenerate 盲区**：列重命名、列类型精细变更、数据迁移需手动编辑生成的迁移文件
- **Partial Unique Index**：项目大量使用 `Index(..., postgresql_where=text("deleted_at IS NULL"))`，review 时需留意
- **迁移文件必须 commit**：`alembic/versions/` 下的文件是代码的一部分
- **EE Model**：`alembic/env.py` 条件导入 `ee.backend.models`，EE 表的迁移也能被 autogenerate 检测

### 种子数据

首次启动时自动创建（幂等，每次启动检查）：

- 默认组织（Default Organization）
- **CE 超管用户**（见下方"CE 超管初始化"）
- **EE 平台管理员**（仅 EE 模式，见下方"EE 平台管理员初始化"）
- 预设工作区模板（软件研发团队、内容工作室、研究实验室）
- 工作区定时器（任务巡检）

种子数据逻辑位于 `app/startup/seed.py`。

### CE 超管初始化

CE 版本通过 `INIT_ADMIN_ACCOUNT` 配置项自动创建超管账号。

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `INIT_ADMIN_ACCOUNT` | `admin` | 超管的 username，留空则跳过自动创建 |
| `RESET_ADMIN_PASSWORD` | `false` | 设为 `true` 后重启会强制重置超管密码 |

#### 首次启动

1. 自动创建 `admin` 用户（`is_super_admin=True`）
2. 生成随机密码并在 Console 醒目输出
3. 用户使用 `admin` + 随机密码登录后，系统强制跳转到改密页面
4. 设置新密码后即可正常使用

#### 重置密码

如果超管忘记密码，在 `.env` 中设置 `RESET_ADMIN_PASSWORD=true` 后重启服务，Console 会输出新的随机密码。重置完成后记得将配置改回 `false`。

#### 每次重启的行为

| 超管状态 | 行为 |
|----------|------|
| 不存在 | 创建用户 + 生成随机密码 |
| 存在 + `RESET_ADMIN_PASSWORD=true` | 强制重置密码 |
| 存在 + 尚未改密（`must_change_password=true`） | 重新生成随机密码（确保 Console 输出最新可用密码） |
| 存在 + 已改密 | 不做任何操作 |

### EE 平台管理员初始化

EE 版本通过 `INIT_EE_ADMIN_ACCOUNT` 配置项创建独立的 Admin 后台管理员。该账号与 CE 超管是**不同的 User 记录**，拥有独立密码。

| 配置项 | 默认值 | 说明 |
|--------|--------|------|
| `INIT_EE_ADMIN_ACCOUNT` | `deskclaw-admin` | Admin 后台管理员 username，留空则跳过 |
| `RESET_EE_ADMIN_PASSWORD` | `false` | 设为 `true` 后重启会强制重置管理员密码 |

#### 权限体系

- **CE Portal 超管**（`is_super_admin=True`，无 AdminMembership）：只能访问 Portal
- **EE 平台管理员**（`is_super_admin=True` + `AdminMembership`）：可访问 Admin 后台 + 组织管理

Admin 后台权限**仅依赖 AdminMembership**，`is_super_admin` 不作为 Admin 访问旁路。

#### 升级/降级

| 场景 | 行为 |
|------|------|
| CE -> EE | 自动创建 EE 管理员，CE 超管无法访问 Admin 后台 |
| EE -> CE | Admin 前端不部署，EE 管理员记录留存无害 |
| EE -> CE -> EE | 识别已有 EE 管理员，跳过重复创建 |

### 软删除

所有数据模型均采用逻辑删除，通过 `deleted_at` 字段标记：

- `deleted_at = NULL`：正常记录
- `deleted_at = 时间戳`：已删除记录

唯一约束使用 Partial Unique Index：`Index(..., unique=True, postgresql_where=text("deleted_at IS NULL"))`。
