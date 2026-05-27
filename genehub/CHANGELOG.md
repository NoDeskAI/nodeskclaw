# Changelog

All notable changes to this project will be documented in this file.

## v2026-03-05

### Fixed
- **OpenClaw triggerLearning**：修复 `openclaw agent` 命令缺少 `--agent main` 参数，且被 5s timeout 提前 kill 的问题
- **OpenClaw 学习触发流程**：triggerLearning 先执行 `openclaw gateway restart` 等待 gateway 重载 skills，再 spawn agent 发消息（detached 后台运行，不阻塞 CLI）

---

## v2026-03-04-6

### Fixed
- **CLI 全局安装后无法使用**：`npm install -g` 创建的 symlink 路径和 `import.meta.url` 不匹配，导致 `program.parse()` 永远不执行，CLI 静默退出无任何输出
- `--version` 从 package.json 动态读取，不再硬编码为 `0.1.0`

---

## v2026-03-04-5

### Added
- PR #2 合入: LearningEngine 优先从 Registry 拉取最新 genehub-learner manifest

### Fixed
- CLI `publish` 支持直接传入 gene.yaml 文件路径（之前只接受目录，传文件路径导致拼接错误）
- CLI `publish` 在 gene.yaml 无 `skill.file` 时自动读取同目录 SKILL.md / CLAUDE.md / AGENTS.md
- `install --learn` / `learn` 对 OpenClaw 无效：AGENTS.md 不存在时创建而非静默跳过
- `learn` 命令补充 `triggerLearning` 调用，与 `install --learn` 行为一致
- boot 指令注入不再依赖 genehub-learner 首次安装，已安装用户也能补上

---

## v2026-03-04-4

### Added
- 基因组：渊博、威严、灵敏、远见四大基因组及 10 个基因
- 管理员可在 web 页面直接提交评审（Gene / Genome / Template）
- SDK / CLI / federated-search / reviews API 单元测试覆盖

### Fixed
- CLI `publish` 支持直接传入 gene.yaml 文件路径（之前只接受目录路径，传文件路径会导致路径拼接错误）
- CLI `publish` 在 gene.yaml 无 `skill.file` 时自动读取同目录 SKILL.md / CLAUDE.md / AGENTS.md
- Curator 审核逻辑修复：`postReview` 统一处理所有 verdict（approved / rejected / needs_improvement / flagged），不再产生重复 review 记录
- Curator 提示词优化：引导 AI 写详细评语并给出明确评级，不再一律通过
- web 评审状态显示修复：新增 `needs_improvement`、`approve` 兼容映射

---

## v2026-03-04-3

### Added
- CLI `publish` 支持自动检测 skill 文件（CLAUDE.md / SKILL.md / AGENTS.md / .cursorrules / .clinerules 等），无需预建 gene.yaml
- 交互式 manifest 构建：自动推断 slug / name / description，交互选择 category / tags
- `-y` 非交互模式，CI/CD 场景可直接使用默认值发布
- 首次发布后自动生成 gene.yaml 保存到目录，后续发布无缝衔接
- 联邦搜索测试覆盖新增 Gitea 集成场景（下载+上传、Gitea 不可用、下载失败降级）

### Fixed
- 联邦搜索入库适配 Gitea 存储架构：外部基因（ClawHub）入库时自动下载 SKILL.md、创建 Gitea 仓库、上传文件并打 tag，确保版本历史和 CLI 安装可用
- ClawHub 下载失败或 Gitea 不可用时优雅降级，仍完成 DB 入库

---

## v2026-03-04-2

### Added
- 版本历史支持点击展开：查看安装命令、git tag、文件内容（Gene / Genome / Template 通用）
- 基因组 / 模板详情页补全版本历史、文件浏览、评审记录 Tab
- MCP 新增 `review_genome` / `review_template` 工具
- 基因组 / 模板发布自动触发 Curator 审核
- Curator 提示词更新，支持基因组和模板审核

### Changed
- 基因文件存储架构重构，集成 Gitea 自托管 Git 管理
- 基因组 / 模板集成 Gitea Git 管理（版本文件、archive 下载）
- delete API 改为硬删除，同步清理 Gitea 仓库
- MCP 端点改为 session-based 模式，仅接受 POST
- pre-commit hook 自动同步 VERSION 到所有 package.json

### Fixed
- JWT 登录用户的管理员角色识别（`optionalAuth` 中间件未检查 `ADMIN_LOGINS`）
- 管理员审核状态筛选：前端 "待审核" 映射值从 `draft` 改为 `pending`
- OpenClaw / Nanobot adapter 多文件基因安装只复制 SKILL.md
- `create` 时 slug 唯一检查过滤已删除记录
- Gitea 仓库创建前检查是否已存在
- Gitea K8s 部署配置修复

---

## v2026-03-03-1

### Added
- AI 员工模板（Agent Template）完整实体：数据库表、CRUD API（11 个端点）、版本管理
- AI 员工模板前端页面：TemplateBrowse 浏览 + TemplateDetail 详情 + TemplateCard 组件
- 3 个 MCP 工具：`list_templates`、`get_template`、`suggest_template`
- GeneAdapter 接口新增 `triggerLearning` 方法，OpenClaw / Nanobot Adapter 实现
- CLI `install --learn` 支持自动触发 bot 对话学习
- 9 个 Agent Template API 端到端测试

### Changed
- 架构文档新增三层能力体系（Gene -> Genome -> Agent Template）、企业私有基因库、学习通道设计
- 学习协议文档补充对话触发学习与串行学习章节

### Fixed
- SDK / types 的 `package.json` exports 改用 `publishConfig` 方案，开发时直接引用源码，避免 stale dist 导致新方法不可用

---

## v2026-03-03

### Added
- Registry 新增 4 个 API 端点：`/genes/tags`、`/genes/featured`、`/genes/:slug/synergies`、`/genomes/featured`
- NoDeskClaw 后端接入 GeneHub Registry（PR #2 已合并）：
  - Phase 2: 基因市场 API 代理（GeneHub 优先 + 本地 fallback）
  - Phase 3: 学习引擎从 GeneHub 拉取 manifest，安装上报 + 创造推送 + 效能同步
  - Phase 4: genes 表降级为缓存（synced_at + upsert 策略）

### Changed
- 确认 6 个架构开放问题：独立部署、混合存储、初期内网、AI Curator 自主过滤恶意基因

---

## v2026-03-02-14

### Added
- GitHub OAuth + API Key 认证体系（`/auth/github`、API Key CRUD）
- 联邦搜索（`GET /api/v1/genes/search`）合并本地 + ClawHub 结果，外部基因后台入库 + AI 审核
- MCP Streamable HTTP 端点（`/mcp`），供 AI Curator 审核基因
- AI Curator 完整部署（CronJob + Listener + MCP tools）
- 前端 UI 组件库（card、badge、tabs、tooltip、skeleton 等）
- 前端页面：基因组浏览/详情、设置（API Key 管理）、联邦搜索卡片
- CLI `auth login` 命令（GitHub OAuth 浏览器流程）
- CLI `publish` 支持自动发版（slug 已存在时调用 publishVersion）
- CLI 支持环境变量配置（`GENEHUB_REGISTRY_URL` / `GENEHUB_TOKEN`）
- lefthook pre-commit hook 强制提交前 lint
- `code-review` 基因补充完整

### Changed
- 新基因默认 `pending` 状态，需 AI Curator 审核后发布
- 审核通过后自动设置 `is_published = true`
- npm 发布改用 `pnpm publish`，正确解析 `workspace:*` 依赖
- OAuth callback 失败时重定向到前端（带 `auth_error` 参数），不再返回 JSON 错误

### Fixed
- 图标名字符串未映射为 Lucide 组件导致页面异常
- 含 `rules` 数组的基因详情页白屏（类型断言错误）
- NOTIFY 事件发射失败导致服务异常
- `Dockerfile.curator` 引用已删除的 `system-prompt.md`
- CI lint 失败（Biome 格式化 + organizeImports）
- CI 测试失败（认证中间件 + 联邦搜索逻辑变更后断言不匹配）
- Docker 构建因 `prepare` 脚本找不到 git 而失败

---

## v2026-02-27-m1

### M1 - 核心功能

#### Registry 完整 API
- 版本管理：`POST /:slug/versions` 发布新版本、`GET /:slug/versions/:version` 获取指定版本
- 依赖解析：`POST /resolve` 支持 semver 范围匹配、循环依赖检测、拓扑排序
- 认证中间件：Bearer Token、角色分级（public / publisher / admin）
- 效能数据上报：`POST /:slug/effectiveness` + `POST /:slug/installed` 安装统计
- Gene CRUD 增强：`PUT /:slug` 更新、`DELETE /:slug` 软删除、版本指定 manifest 获取

#### Learning Engine（L1 + L2）
- L1 浅层学习：安装基因时自动更新 AGENTS.md 能力声明、写入 memory 记录、合并 MCP Servers
- L2 深度学习引擎：LearningEngine 类、学习任务生成、练习场景、结果解析与 variant 应用
- genehub-learner 元学习基因：always-on skill，教 Agent 处理学习任务

#### 适配器增强
- BaseAdapter 重构：`doInstall/doUninstall` + `onPostInstall/onPostUninstall` hook 模式
- OpenClaw Adapter L1：自动更新 AGENTS.md、memory、MCP 配置
- nanobot Adapter L1：memory 记录、版本解析
- getInstalledVersion()：从 SKILL.md front matter 解析版本号
- uninstall()：清理 AGENTS.md 中的能力声明

#### CLI 完整命令集
- 新增：`config set/get`、`uninstall`、`learn`（L2 深度学习触发/检查）
- 增强：`install` 支持 `slug@version` + `--learn` 自动触发学习
- 增强：`search --json`、`list --json` JSON 格式输出
- 增强：`list` 显示版本号

#### 官方基因库
- 新增 7 个高质量基因：genehub-learner、analytical-thinking、clean-code、test-driven-development、data-analysis、communication-style、prompt-engineering
- 每个基因包含完整的 learning objectives 和 scenarios

#### 测试
- Learning Engine 单元测试（6 项）
- OpenClaw Adapter L1 集成测试（6 项）
- 全部 30 项测试通过

---

## v2026-02-27-alpha

### Added

- 项目初始化
- 架构设计文档（`docs/architecture.md`）
- 标准学习协议规范（`docs/gene-learning-protocol.md`）
- 项目基础规则（AGENTS.md、Cursor Rules、开源项目规范）
- MIT License、CONTRIBUTING.md

### M0 - 基础设施

- pnpm monorepo 搭建（`@nodeskai/genehub-types` + `@nodeskai/genehub-registry` + `@nodeskai/genehub-sdk` + `genehub` CLI）
- `@nodeskai/genehub-types`：Gene Manifest Zod schema、实体类型、API 类型、Adapter 接口
- `@nodeskai/genehub-registry`：Hono + Drizzle ORM + PostgreSQL，Gene CRUD API（搜索/详情/manifest/版本/发布）
- `@nodeskai/genehub-sdk`：GeneHub API 客户端 + OpenClaw Adapter + nanobot Adapter + Generic Adapter
- `genehub` CLI：install / search / list / publish / init 五个子命令
- 官方基因示例：`genes/skills/code-review/`
- Docker Compose 本地 PostgreSQL 环境
- Vitest 测试：Manifest schema 校验 + Registry API + Adapter 单元测试
