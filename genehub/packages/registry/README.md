# @nodeskai/genehub-registry

GeneHub Registry Service -- AI 员工基因注册中心的后端服务。

## 技术栈

- **框架**：Hono (Node.js)
- **数据库**：PostgreSQL + Drizzle ORM
- **认证**：GitHub OAuth + JWT + API Key
- **MCP**：Streamable HTTP 端点，供 Curator 审核

## 目录结构

```
packages/registry/
├── src/
│   ├── index.ts              # 服务入口
│   ├── app.ts                # Hono 应用配置、路由挂载、静态文件
│   ├── api/                  # REST API 路由
│   │   ├── auth.ts           # GitHub OAuth + JWT
│   │   ├── genes.ts          # 基因 CRUD + 联邦搜索
│   │   ├── genomes.ts        # 基因组 CRUD
│   │   ├── keys.ts           # API Key 管理
│   │   ├── resolve.ts        # 依赖解析
│   │   ├── reviews.ts        # 审核列表与反馈
│   │   ├── sync.ts           # NoDeskClaw 同步
│   │   └── webhooks.ts       # NoDeskClaw Webhook
│   ├── services/             # 业务逻辑
│   │   ├── gene-service.ts
│   │   ├── genome-service.ts
│   │   ├── dependency-resolver.ts
│   │   ├── federated-search.ts
│   │   └── gene-events.ts
│   ├── adapters/             # 外部数据源适配器
│   │   ├── clawhub/
│   │   ├── evomap/
│   │   └── nodeskclaw/
│   ├── db/                   # 数据库 schema + 迁移 + seed
│   ├── mcp/                  # MCP Streamable HTTP
│   ├── middleware/            # 认证、错误处理、响应格式化
│   └── curator/              # AI Curator 配置
├── drizzle/                  # 生成的迁移文件
├── dist/                     # 构建产物
└── package.json
```

## 开发

### 前置条件

- Node.js >= 20
- PostgreSQL（可通过 Docker Compose 启动）

### 环境变量

在 `packages/registry/.env` 中配置：

```
DATABASE_URL=postgres://genehub:genehub@localhost:5432/genehub
GITHUB_CLIENT_ID=...
GITHUB_CLIENT_SECRET=...
GENEHUB_JWT_SECRET=...
GENEHUB_ADMIN_TOKEN=your-admin-token
```

### 命令

```bash
pnpm dev            # 开发模式（自动加载 .env）
pnpm build          # 构建
pnpm start          # 生产模式启动
pnpm test           # 运行测试
pnpm db:generate    # 生成数据库迁移
pnpm db:migrate     # 执行迁移
pnpm db:seed        # 填充示例数据
pnpm db:studio      # 打开 Drizzle Studio
```

## API 概览

| 路径前缀 | 说明 |
|---|---|
| `GET /api/health` | 健康检查 |
| `/auth/*` | GitHub OAuth、登出、当前用户 |
| `/api/v1/genes/*` | 基因 CRUD、版本管理、联邦搜索 |
| `/api/v1/genomes/*` | 基因组 CRUD、版本管理、依赖解析 |
| `/api/v1/keys/*` | API Key 创建、列表、撤销 |
| `/api/v1/resolve` | 批量依赖解析 |
| `/api/v1/sync/*` | NoDeskClaw 数据同步 |
| `/api/v1/webhooks/*` | NoDeskClaw Webhook 接收 |
| `/mcp` | MCP Streamable HTTP（需 admin token） |

## 部署

生产环境通过 Docker 镜像部署到 K8s，配置见 `deploy/k8s/genehub.yaml`。
