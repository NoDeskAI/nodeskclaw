# GeneHub

NoDeskClaw AI 员工基因库 —— 统一管理、分发和演化 Agent 能力基因。

## 什么是 GeneHub

GeneHub 是 NoDeskClaw 生态的核心基因注册中心（Gene Registry），为全体 AI 员工提供可复用、可组合、可演化的能力基因。

它同时承担三个角色：
- **基因注册中心**（Registry）：统一存储、版本管理、搜索发现
- **标准学习协议**（Protocol）：定义基因从发现到安装到学习的全生命周期规范
- **多产品适配层**（Adapters）：已对接 openClaw、nanobot，后续扩展 DeskClaw 等产品

## 核心能力

### 基因库管理

- 为 NoDeskClaw 全体 AI 员工提供统一的基因存储与检索
- 语义化版本管理（SemVer）、依赖解析与冲突检测
- 基因标签体系：能力（ability）、性格（personality）、知识（knowledge）、工具（tool）

### 联邦搜索与外部基因获取

- **联邦搜索**：搜索时同时查询本地 DB + ClawHub + Evomap，结果合并并按来源标记
- 从 **ClawHub** 拉取社区共享基因（已集成）
- 从 **Evomap** 获取演化路径推荐的基因组合（已集成）
- 外部基因入库后自动触发 AI Curator 审核

### 标准学习协议（Gene Learning Protocol）

- 定义基因的标准描述格式 **Gene Manifest**（`gene.yaml`）
- 标准化的安装 / 学习 / 遗忘 / 创造协议
- 渐进式学习能力等级：L0 直接安装 → L1 浅层学习 → L2 深度学习 → L3 自主进化
- 已为 **openClaw** 和 **nanobot** 提供 Adapter 接口，后续扩展 DeskClaw 等产品

### AI 基因库管理（OpenCode + MCP）

GeneHub 内置了基于 **MCP（Model Context Protocol）** 的 AI 能力体系：

- **MCP Server**：将基因库操作暴露为 22 个标准工具（Query 6 + Genome 4 + Template 3 + Manage 4 + Review 5），任何支持 MCP 的 AI 框架均可接入
- **Gene Curator**：基于 **OpenCode** 驱动的自主 AI Agent，自动审核基因、基因组和 AI 员工模板
- **事件驱动**：基因/基因组/模板入库时通过 PostgreSQL `LISTEN/NOTIFY` 自动触发 Curator 审核
- **Gitea 集成**：基因文件通过自托管 Gitea 进行 Git 版本管理，支持历史版本文件浏览和 archive 下载

```bash
# 启动 MCP Server（用于 AI 框架对接）
pnpm --filter @nodeskai/genehub-registry mcp:dev

# 使用 OpenCode 运行 Curator（需要 opencode CLI + MiniMax API Key）
cd packages/registry/curator
export MINIMAX_API_KEY="你的 MiniMax API Key"
export DATABASE_URL="postgres://genehub:genehub@localhost:5432/genehub"

# 交互模式
opencode --config opencode.json

# 单次任务
opencode run --config opencode.json "审核最近新入库的基因"
```

详见 [AI 能力使用指南](CONTRIBUTING.md#gene-curator) 和 [架构文档](docs/architecture.md#十一ai-能力opencode--mcp)。

### 三层能力体系

- **Gene（基因）**：最小能力单元，如 code-review、system-design
- **Genome（基因组）**：一组基因的组合套件，如"后端开发基因组"
- **Agent Template（AI 员工模板）**：完整的 AI 员工配置，包含基因组 + 角色定义 + 个性配置

### 安装方式

- 原生 CLI：`genehub install <slug>` / `genehub install <slug>@<version>`
- 支持指定版本安装历史版本
- HTTP API：程序化调用（NoDeskClaw 等平台对接）

## 官方基因仓库

**[genehub.nodeskai.com](https://genehub.nodeskai.com)**

官方基因仓库是 GeneHub 的中心化基因市场，你可以在上面：

- 浏览和搜索所有已发布的基因、基因组、AI 员工模板
- 查看详情、版本历史（支持展开查看文件内容）、AI 评审记录
- 获取一键安装命令
- 管理员可筛选未发布内容和按审核状态过滤

所有 CLI 命令默认连接官方仓库，无需额外配置。

## 安装

```bash
npm install -g @nodeskai/genehub
```

安装后即可使用 `genehub` 命令。相关 npm 包：

| 包名 | 说明 |
|---|---|
| [`@nodeskai/genehub`](https://www.npmjs.com/package/@nodeskai/genehub) | CLI 命令行工具 |
| [`@nodeskai/genehub-sdk`](https://www.npmjs.com/package/@nodeskai/genehub-sdk) | TypeScript SDK（Adapters + Learning Engine） |
| `genehub-sdk` (PyPI / `packages/sdk/python`) | Python SDK（最小可用：Client + Adapter + GenericAdapter + LearningEngine） |
| [`@nodeskai/genehub-types`](https://www.npmjs.com/package/@nodeskai/genehub-types) | 共享类型定义与 Zod Schemas |

## 快速开始

### 开发环境搭建

```bash
# 克隆仓库
git clone git@github.com:NoDeskAI/genehub.git
cd genehub

# 安装依赖（需要 pnpm >= 9 和 Node.js >= 20）
pnpm install

# 构建所有包
pnpm build

# 启动 PostgreSQL（需要 Docker）
docker compose up -d

# 运行数据库迁移
pnpm db:generate
pnpm db:migrate

# 导入种子数据
pnpm db:seed

# 启动 Registry 服务
pnpm dev:registry
```

### 使用 CLI

如果通过 npm 全局安装：

```bash
npm install -g @nodeskai/genehub
genehub search code-review
```

如果在本地开发环境中使用：

```bash
# 方式一：通过 pnpm 调用（推荐）
pnpm genehub search code-review

# 方式二：直接运行源码（无需构建）
pnpm --filter @nodeskai/genehub dev -- search code-review
```

CLI 常用命令：

```bash
# 搜索基因
genehub search code-review

# 安装基因（自动检测当前 Agent 产品：openClaw / nanobot）
genehub install code-review

# 安装指定版本
genehub install code-review@1.2.0

# 安装并触发深度学习
genehub install code-review --learn

# 触发深度学习（L2）
genehub learn code-review

# 检查学习结果
genehub learn --check code-review

# 查看已安装基因
genehub list

# 卸载基因
genehub uninstall code-review

# 管理配置
genehub config set registry https://genehub.nodeskai.com
genehub config set token ghb_your_token

# 初始化新基因模板
genehub init ./my-gene

# 发布基因
genehub publish ./my-gene/
```

### 运行测试

```bash
pnpm test
```

## 项目结构

```
genehub/
├── packages/
│   ├── types/                      # @nodeskai/genehub-types - 共享类型与 Zod schemas
│   ├── registry/                   # @nodeskai/genehub-registry - Gene Registry Service (Hono + Drizzle)
│   │   ├── src/
│   │   │   ├── api/                # REST API 路由（genes / genomes / templates / auth）
│   │   │   ├── services/           # 业务逻辑（含联邦搜索、Gitea 集成）
│   │   │   ├── mcp/               # MCP Server（22 个 AI 工具）
│   │   │   │   ├── server.ts      # 工具注册
│   │   │   │   └── tools/         # query / genome / template / manage / review
│   │   │   └── adapters/          # ClawHub / Evomap / NoDeskClaw 适配器
│   │   └── curator/               # Gene Curator AI Agent
│   │       ├── opencode.json      # OpenCode 配置
│   │       ├── AGENTS.md          # Curator 系统提示词
│   │       └── listener.ts        # 事件监听器（LISTEN/NOTIFY）
│   ├── sdk/typescript/             # @nodeskai/genehub-sdk - TypeScript SDK + Adapters
│   ├── sdk/python/                 # genehub-sdk - Python SDK（Client + Adapter + GenericAdapter + LearningEngine）
│   ├── cli/                        # @nodeskai/genehub - 命令行工具 (Commander.js)
│   └── web/                        # 基因仓库 Web UI (React + Vite + Tailwind)
├── genes/                          # 官方基因库
│   └── skills/<gene-slug>/
│       ├── gene.yaml               # Gene Manifest
│       └── SKILL.md                # 技能内容
├── deploy/k8s/                     # Kubernetes 部署清单（Registry + Gitea + Curator）
├── docs/                           # 设计文档
├── Dockerfile                      # 多阶段构建 (Registry + Web)
├── docker-compose.yml              # PostgreSQL + Gitea 本地开发
└── biome.json                      # Lint / Format 配置
```

## 协议兼容矩阵

| 产品 | 安装 | 学习(L0) | 深度学习(L2) | 自主进化(L3) | 状态 |
|------|------|----------|-------------|-------------|------|
| openClaw / NoDeskClaw | ✅ | ✅ | ✅ | ✅ | 已支持 |
| nanobot | ✅ | ✅ | 试验性 | 试验性 | 已支持 |
| ClawHub | 联邦搜索 | — | — | — | 已集成搜索 |
| Evomap | 联邦搜索 | — | — | — | 已集成搜索 |
| DeskClaw | — | — | — | — | 后续扩展 |

## 文档

- [架构设计](docs/architecture.md)（含 AI 能力、MCP Server、联邦搜索）
- [标准学习协议规范](docs/gene-learning-protocol.md)

## License

MIT
