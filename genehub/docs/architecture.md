# GeneHub 架构设计

> 版本：v0.1
> 日期：2026-02-27
> 状态：草稿

---

## 一、定位与背景

### 1.1 为什么需要 GeneHub

NoDeskClaw 已经实现了一套完整的基因进化生态（Gene Evolution Ecosystem），包括基因市场、学习引擎、遗忘机制、Agent 创造等能力。但这套系统存在以下问题：

| 问题 | 影响 |
|------|------|
| 基因存储与管理耦合在 NoDeskClaw 后端 | 其他 Agent 产品无法复用 |
| 基因格式绑定 OpenClaw（SKILL.md + openclaw.json） | nanobot 等产品需要各自适配 |
| 无外部基因引入通道 | 无法从 ClawHub、Evomap 等外部生态获取基因 |
| 安装方式单一（API 调用） | 无法兼容 `claw install`、`npm`、`pip` 等主流分发方式 |

**GeneHub 的目标**：将基因能力从 NoDeskClaw 中抽离为独立的中心化基因服务，成为 NoDeskClaw 全生态的基因基础设施。

### 1.2 核心定位

```
GeneHub = 基因注册中心（Registry）+ 标准学习协议（Protocol）+ 多产品适配层（Adapters）
```

类比：

| 角色 | 软件世界类比 |
|------|-------------|
| GeneHub Registry | npm registry / PyPI |
| Gene Manifest | package.json / setup.py |
| GeneHub CLI | npm / pip |
| 标准学习协议 | Language Server Protocol（LSP） |
| 产品适配器 | LSP 客户端实现 |

---

## 一(bis)、三层能力体系

GeneHub 管理三层能力实体，从原子到组合：

| 层级 | 实体 | 说明 |
|------|------|------|
| L1 | Gene（基因） | 原子能力单元，一个 SKILL.md + manifest |
| L2 | Genome（基因组） | 基因的精选合集，一键安装一套能力 |
| L3 | Agent Template（AI 员工模板） | 基因组 + 额外基因 + 角色设定，一个可复制的 AI 员工身份 |

```
Gene（基因）
  └── 原子能力单元

Genome（基因组）
  └── 引用多个基因，一键安装

Agent Template（AI 员工模板）
  └── 引用基因组 + 额外基因 + 角色定位 + 头像
  └── 一个可以被克隆的 AI 员工身份
```

AI 员工模板是最高层抽象，GeneHub 存储公共模板（面向社区），NoDeskClaw 存储企业私有模板（安全隔离）。

---

## 二、系统架构

### 2.1 全局架构

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                            外部基因生态                                        │
│                                                                              │
│   ┌──────────────┐       ┌──────────────┐       ┌──────────────┐            │
│   │   ClawHub     │       │   Evomap     │       │  社区贡献     │            │
│   │  (基因市场)    │       │ (进化推荐)   │       │ (PR / Upload) │            │
│   └──────┬───────┘       └──────┬───────┘       └──────┬───────┘            │
│          │                      │                      │                     │
└──────────┼──────────────────────┼──────────────────────┼─────────────────────┘
           │                      │                      │
           ▼                      ▼                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                          GeneHub Core                                         │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    Gene Registry Service                             │   │
│   │                                                                     │   │
│   │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │   │
│   │  │ 基因存储      │  │ 版本管理      │  │ 搜索与发现               │  │   │
│   │  │ Gene Store   │  │ Versioning   │  │ Search & Discovery      │  │   │
│   │  └──────────────┘  └──────────────┘  └──────────────────────────┘  │   │
│   │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │   │
│   │  │ 依赖解析      │  │ 兼容校验      │  │ 审核与发布               │  │   │
│   │  │ Dependency   │  │ Compat Check │  │ Review & Publish        │  │   │
│   │  └──────────────┘  └──────────────┘  └──────────────────────────┘  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    外部基因适配层 (Inbound Adapters)                   │   │
│   │                                                                     │   │
│   │  ┌──────────────┐  ┌──────────────┐  ┌──────────────────────────┐  │   │
│   │  │ ClawHub      │  │ Evomap       │  │ Git Repo Importer       │  │   │
│   │  │ Adapter      │  │ Adapter      │  │ (GitHub / GitLab)       │  │   │
│   │  └──────────────┘  └──────────────┘  └──────────────────────────┘  │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    标准学习协议 SDK                                    │   │
│   │                    (Gene Learning Protocol)                          │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    产品适配层 (Outbound Adapters)                      │   │
│   │                                                                     │   │
│   │  ┌──────────────┐  ┌──────────────┐                               │   │
│   │  │ OpenClaw     │  │ nanobot      │    (DeskClaw 等后续扩展)       │   │
│   │  │ Adapter      │  │ Adapter      │                               │   │
│   │  └──────────────┘  └──────────────┘                               │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
│   ┌─────────────────────────────────────────────────────────────────────┐   │
│   │                    CLI / 分发层                                       │   │
│   │  genehub install | claw install | npx | pip                         │   │
│   └─────────────────────────────────────────────────────────────────────┘   │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
           │                      │                      │
           ▼                      ▼                      ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                          Agent 产品                                           │
│                                                                              │
│   ┌──────────────┐  ┌──────────────┐  ┌──────────────┐                    │
│   │  NoDeskClaw   │  │  openClaw    │  │  nanobot     │  (更多产品后续)    │
│   │  (K8s 管理)  │  │  (开源框架)   │  │ (轻量 Agent) │                    │
│   └──────────────┘  └──────────────┘  └──────────────┘                    │
│                                                                              │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 2.2 核心模块

#### Gene Registry Service（基因注册中心）

中心化的基因存储与管理服务，职责：

| 模块 | 职责 |
|------|------|
| Gene Store | 基因 / 基因组的存储、CRUD、元数据管理 |
| Versioning | 语义化版本（SemVer）管理、变体（Variant）追溯 |
| Search & Discovery | 全文搜索、标签过滤、推荐算法、热度排行 |
| Dependency Resolver | 基因间依赖解析、冲突检测、安装计划生成 |
| Compatibility Checker | 目标产品兼容性校验（某基因是否支持 nanobot） |
| Review & Publish | 基因审核流程（人类审核 / Agent 审核 / 自动验证） |

#### Inbound Adapters（外部基因适配层）

外部基因生态对接。**ClawHub / EvoMap 已从定期同步改为联邦搜索（实时查询 + 后台入库待审核）**。

| 适配器 | 数据源 | 协议 | 当前模式 |
|--------|--------|------|---------|
| ClawHub Adapter | ClawHub 基因市场 | REST API | **联邦搜索**（实时展示 + 后台入库为 pending，等待 AI 审核） |
| Evomap Adapter | Evomap 进化推荐引擎 | REST API | **联邦搜索**（同上） |
| NoDeskClaw Adapter | NoDeskClaw 内部数据 | 直连 DB | 批量导入（白名单，直接 approved） |
| Git Repo Importer | GitHub / GitLab 仓库 | Git Clone + gene.yaml 解析 | 导入 |

#### Outbound Adapters（产品适配层）

将 GeneHub 的基因注入到不同 Agent 产品（初期聚焦 openClaw + nanobot，其他产品后续扩展）：

| 适配器 | 目标产品 | 注入方式 |
|--------|---------|---------|
| OpenClaw Adapter | openClaw / NoDeskClaw | SKILL.md + openclaw.json（NFS / API） | 初期 |
| nanobot Adapter | nanobot | 配置注入（Future：capabilities/requires 校验与注入） | 初期 |
| Generic Adapter | 通用 Agent | 标准学习协议 HTTP 回调 | 初期 |
| DeskClaw Adapter | DeskClaw | .cursor/rules/ + SKILL.md | 后续扩展 |

#### GeneHub CLI（命令行工具）

统一的基因管理命令行，兼容多种安装方式：

```bash
# 已实现命令
genehub install <gene-slug>       # 安装基因（支持 @version、--force、--learn、--target）
genehub uninstall <gene-slug>     # 卸载基因
genehub search <keyword>          # 搜索基因（默认联邦搜索；--local 仅本地 DB）
genehub list                      # 列出已安装基因
genehub publish <path>            # 发布基因（自动检测 CLAUDE.md/SKILL.md/AGENTS.md，无需预建 gene.yaml）
genehub publish <path> -y         # 非交互模式发布（使用默认值）
genehub init [path]               # 初始化 gene.yaml + SKILL.md 模板
genehub config set/get            # 管理配置（registry / token）
genehub auth login/status/logout  # GitHub OAuth 认证
genehub learn <slug>              # 触发深度学习（--check 检查结果）
genehub genome publish <path>     # 发布基因组（包含 genome.yaml）
genehub genome install <slug>     # 安装基因组（递归安装所有基因）
genehub genome list               # 搜索基因组
genehub genome info <slug>        # 基因组详情
genehub template publish <path>   # 发布 AI 员工模板（包含 template.yaml）
genehub template install <slug>   # 安装模板（递归安装基因组 + 基因）
genehub template list             # 搜索模板
genehub template info <slug>      # 模板详情

# Future
genehub info <gene-slug>          # 基因详情（未实现）

# 兼容已有生态（Future）
claw install <gene-slug>          # ClawHub 兼容
npx genehub install <gene-slug>   # npm 生态兼容
pip install genehub-<gene-slug>   # Python 生态兼容
```

#### 多 Agent 办公室单元（Office Unit）

GeneHub 基因与基因组可被用于塑造多 Agent 协作中的角色人格与行为底色。一种典型设计是「办公室单元」：四类角色（执行 Act、规划 Plan、知识/检索 Knowledge、审核/权限 Judge）分别对应基因组 agile-executor（灵敏）、visionary-planner（远见）、erudite-scholar（渊博）、steadfast-guardian（威严）。下图描述四角色与信息流关系；详细基因清单与关联见 [.cursor/plans/多agent基因组设计_2260e583.plan.md](.cursor/plans/多agent基因组设计_2260e583.plan.md)。

```mermaid
graph TD
    subgraph implemented [本次实现]
        Agile["灵敏 Agile / Act"]
        Foresight["远见 Foresight / Plan"]
        Erudite["渊博 Erudite / Knowledge"]
        Authority["威严 Authority / Judge"]
    end

    Foresight -->|"委派任务/指令"| Agile
    Agile -->|"汇报进展/状态"| Foresight
    Foresight -->|"请求知识/参考"| Erudite
    Erudite -->|"提供参考/资源"| Foresight
    Agile -->|"按需请求知识"| Erudite
    Agile -->|"请求权限/提交结果"| Authority
    Authority -->|"发放或回收权限、验收"| Agile
    Foresight -->|"计划与约束对齐"| Authority
```

四基因组（灵敏、远见、渊博、威严）的基因按 Identity / Behavioral / Method 分层，并通过协作接口（委派与接收、状态与监控、知识请求与蒸馏、验收与权限治理等）对接；与已有基因（如 analytical-thinking、communication-style）为 synergy 推荐关系。详见计划文档「六、基因之间的关联」。

---

## 三、数据模型

### 3.1 核心实体

#### Gene（基因）

从 NoDeskClaw 的 Gene 模型演化而来，增加多产品兼容字段：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| name | string(128) | 显示名称 |
| slug | string(128) | 唯一标识符，全局唯一 |
| version | string(16) | 语义化版本号（SemVer） |
| description | text | 详细描述（Markdown） |
| short_description | string(256) | 摘要 |
| category | string(32) | 领域分类 |
| tags | JSON | 标签数组（能力 / 性格 / 知识 / 工具） |
| icon | string(64) | 图标名（lucide 图标标识） |
| source | enum | `official` / `clawhub` / `evomap` / `community` / `agent` / `github` |
| source_ref | string | 外部来源引用（ClawHub URL / Evomap ID / GitHub login） |
| repository_url | text nullable | Gitea 仓库路径（如 `genes/clean-code`） |
| file_count | int | 基因文件数量 |
| publisher_id | FK nullable | 发布者（见 3.3 节） |
| manifest | JSON | **标准基因清单**（见第四章），仅存 gene.yaml 解析结果 |
| compatibility | JSON | 兼容产品列表 `["openclaw", "nanobot"]`（初期仅支持这两个产品） |
| dependencies | JSON | 依赖基因 `[{"slug": "xxx", "version": ">=1.0"}]` |
| synergies | JSON | 协同推荐基因 |
| parent_gene_id | FK nullable | 变体溯源 |
| author | JSON | 作者信息 `{"type": "human/agent", "id": "...", "name": "..."}` |
| install_count | int | 总安装数 |
| avg_rating | float | 平均评分 |
| effectiveness_score | float | 综合效能分 |
| ai_score | float nullable | AI Curator 评分（0-10） |
| ai_verdict | string(24) nullable | AI 审核结论（如 `approve`、`needs_improvement`、`flagged`） |
| ai_enriched | bool | 是否已被 AI Curator 处理过 |
| review_status | enum | `draft` / `pending` / `approved` / `rejected` / `flagged` / `needs_improvement` |
| is_published | bool | 是否上架 |
| created_at | datetime | |
| updated_at | datetime | |
| deleted_at | datetime | 软删除 |

#### Genome（基因组）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| name | string(128) | 显示名称 |
| slug | string(128) | 唯一标识符 |
| version | string(16) | 版本号 |
| description | text | 描述 |
| short_description | string(256) | 摘要 |
| category | string(32) | 分类（默认 `general`） |
| tags | JSON | 标签数组 |
| icon | string(64) | 图标 |
| genes | JSON | 包含的基因 `[{"slug": "xxx", "version": ">=1.0", "config_override": {}}]` |
| compatibility | JSON | 兼容产品列表 |
| repository_url | text nullable | Gitea 仓库路径（如 `genomes/fullstack-dev`） |
| file_count | int | 文件数量 |
| install_count | int | 应用次数 |
| avg_rating | float | 评分 |
| author | JSON | 作者信息 |
| is_published | bool | 上架 |
| created_at | datetime | |
| updated_at | datetime | |
| deleted_at | datetime | 软删除 |

#### Agent Template（AI 员工模板）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| name | string(128) | 模板名称 |
| slug | string(128) | 唯一标识符 |
| version | string(16) | 版本号 |
| description | text | 描述 |
| short_description | string(256) | 摘要 |
| role | string(64) nullable | 角色定位（如「营销专员」「代码审查员」） |
| category | string(32) | 分类 |
| tags | JSON | 标签数组 |
| icon | string(64) | 图标 |
| avatar_url | text nullable | 员工头像 |
| genomes | JSON | 引用的基因组 `[{slug, version}]` |
| genes | JSON | 额外独立基因 `[{slug, version}]` |
| compatibility | JSON | 兼容产品列表 |
| repository_url | text nullable | Gitea 仓库路径（如 `templates/senior-backend`） |
| file_count | int | 文件数量 |
| install_count | int | 安装次数 |
| avg_rating | float | 平均评分 |
| author | JSON | 作者信息 |
| publisher_id | FK nullable | 发布者 |
| is_published | bool | 是否上架 |
| created_at | datetime | |
| updated_at | datetime | |
| deleted_at | datetime | 软删除 |

#### Agent Template Version（模板版本历史）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| template_id | FK | 所属模板 |
| version | string(16) | 版本号 |
| genomes | JSON | 该版本的基因组列表 |
| genes | JSON | 该版本的额外基因列表 |
| commit_sha | varchar(40) nullable | Gitea commit SHA |
| git_tag | varchar(64) nullable | Gitea git tag |
| files | JSON nullable | 文件列表 `[{path, size, sha}]` |
| changelog | text | 变更日志 |
| is_latest | bool | 是否最新 |
| published_at | datetime | 发布时间 |

#### GeneVersion（基因版本历史）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| gene_id | FK | 所属基因 |
| version | string(16) | 版本号 |
| manifest | JSON | 该版本的完整 manifest |
| commit_sha | varchar(40) nullable | Gitea commit SHA |
| git_tag | varchar(64) nullable | Gitea git tag（如 `v1.0.0`） |
| files | JSON nullable | 文件列表 `[{path, size, sha}]` |
| changelog | text | 变更日志 |
| is_latest | bool | 是否最新 |
| published_at | datetime | 发布时间 |

#### GenomeVersion（基因组版本历史）

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| genome_id | FK | 所属基因组 |
| version | string(16) | 版本号 |
| genes | JSON | 该版本的基因组合 |
| commit_sha | varchar(40) nullable | Gitea commit SHA |
| git_tag | varchar(64) nullable | Gitea git tag（如 `v1.0.0`） |
| files | JSON nullable | 文件列表 `[{path, size, sha}]` |
| changelog | text | 变更日志 |
| is_latest | bool | 是否最新 |
| published_at | datetime | 发布时间 |

#### GeneReview（审核记录，统一表）

统一存储基因、基因组、AI 员工模板的审核记录。通过 `entity_type` + `entity_slug` 区分实体类型：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| gene_id | FK nullable | 所属基因（向后兼容旧数据，新增记录可为空） |
| entity_type | string(16) | 实体类型：`gene` / `genome` / `template`，默认 `gene` |
| entity_slug | string(128) nullable | 实体 slug（方便查询，不依赖外键） |
| reviewer | string(64) | 审核者标识（默认 `curator-agent`） |
| score | float nullable | 评分（0-10） |
| verdict | string(24) nullable | 结论（`approve` / `reject` / `needs_improvement` / `flagged`） |
| comments | JSON | 审核意见数组 |
| changes_made | JSON nullable | AI 自动修改的字段记录 |
| feedback | string(32) nullable | 人工反馈覆盖（admin 操作） |
| model | string(64) nullable | 使用的 LLM 模型标识 |
| created_at | datetime | |

索引：`(entity_type, entity_slug)` 联合索引，`(gene_id)` 保持向后兼容。

#### GeneRelation（基因关系）

基因间的关联关系，由 AI Curator 自动发现或人工设置：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| source_gene_id | FK | 源基因 |
| target_gene_id | FK | 目标基因 |
| relation_type | string(24) | 关系类型：`synergy` / `conflict` / `extends` / `replaces` |
| strength | float | 关系强度（0-1，默认 0.5） |
| reason | text nullable | 关联理由 |
| created_by | string(64) | 创建者（默认 `curator-agent`） |
| created_at | datetime | |

唯一约束：`(source_gene_id, target_gene_id, relation_type)`

### 3.2 与 NoDeskClaw 的数据关系

```
NoDeskClaw                              GeneHub
┌─────────────────────┐         ┌─────────────────────┐
│ Instance             │         │ Gene (Registry)      │
│ InstanceGene         │◄───────►│ Genome (Registry)    │
│ EvolutionEvent       │         │ GeneVersion          │
│ GeneEffectLog        │         │                      │
│ GeneRating           │   sync  │                      │
└─────────────────────┘  ◄────► └─────────────────────┘

NoDeskClaw 保留：实例级基因状态（InstanceGene）、进化日志、效能数据
GeneHub 统管：基因元数据、版本、manifest、搜索、兼容性
```

NoDeskClaw 的 `genes` 表将作为 GeneHub 的客户端缓存，定期与 GeneHub Registry 同步。新基因由 GeneHub 统一管理，NoDeskClaw 通过 API 拉取。

### 3.3 认证与发布者

#### Publisher（发布者）

通过 GitHub OAuth 登录后自动创建，不维护用户资料，仅缓存 GitHub 身份：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| github_id | integer | GitHub user ID，唯一 |
| github_login | string(64) | GitHub 用户名 |
| github_name | string(128) | 显示名 |
| github_avatar_url | text | 头像 URL |
| github_profile_url | text | Profile 链接（来源跳转用） |
| created_at | datetime | |
| last_login_at | datetime | |

#### ApiKey（API 密钥）

一个 Publisher 可创建多个 Key，用于 CLI/SDK 认证：

| 字段 | 类型 | 说明 |
|------|------|------|
| id | UUID | 主键 |
| publisher_id | FK | 所属发布者 |
| token_prefix | string(16) | 前缀用于展示（如 `ghb_abc1****`） |
| token_hash | string(64) | SHA-256 hash，不存明文 |
| name | string(128) | 用户命名（如 "My Laptop"） |
| last_used_at | datetime | |
| created_at | datetime | |
| revoked_at | datetime | 非空表示已撤销 |

#### Gene 表变更

| 字段 | 类型 | 说明 |
|------|------|------|
| publisher_id | FK nullable | 发布者（nullable 兼容历史数据） |
| source | enum | 新增 `github` 值，用户发布时设为 `github` |
| source_ref | string | 用户发布时设为 GitHub login |

#### 认证流程

```
GitHub OAuth                   API Key
┌──────────────────────┐       ┌─────────────────────────┐
│ Web: Login with GitHub │       │ CLI/SDK: Bearer ghb_xxx  │
│ -> /auth/github        │       │ -> 查 api_keys 表         │
│ -> GitHub OAuth flow   │       │ -> hash 比对              │
│ -> upsert publisher    │       │ -> 关联 publisher         │
│ -> JWT httpOnly cookie │       │ -> 设置 authRole          │
└──────────────────────┘       └─────────────────────────┘
```

认证优先级：
1. Bearer Token -> 查 `api_keys` 表，角色 `publisher`
2. Session Cookie -> 解析 JWT，角色 `publisher`
3. `GENEHUB_ADMIN_TOKEN` 环境变量 -> 角色 `admin`
4. 无认证 -> 角色 `public`

所需环境变量：`GITHUB_CLIENT_ID`、`GITHUB_CLIENT_SECRET`、`GENEHUB_JWT_SECRET`

---

## 四、标准基因清单（Gene Manifest）

见 `docs/gene-learning-protocol.md` 第二章。

---

## 五、技术选型

| 层级 | 选型 | 说明 |
|------|------|------|
| Registry API | TypeScript + Hono | 轻量高性能，运行在 Node.js / Bun / Edge |
| 数据库 | PostgreSQL | 与 NoDeskClaw 同生态，支持 JSONB 全文搜索 |
| 基因文件存储 | Gitea（自托管 Git） | 每个基因/基因组/模板各一个 Git 仓库（三个 org：genes/genomes/templates），git tag 管理版本，DB 仅存索引 |
| 搜索引擎 | PostgreSQL ILIKE（当前）/ Meilisearch（Future） | 先简后繁 |
| CLI | TypeScript (tsx) | 跨平台，npm 全局安装 |
| Web 前端 | React 19 + Vite 7 + Tailwind CSS 4 + Radix UI | 基因浏览、搜索、API Key 管理（6 个页面） |
| SDK | TypeScript（已实现）+ Python（已实现最小可用） | 覆盖主流 Agent 开发语言 |
| 分发 | npm + pip + GitHub Releases | 兼容主流包管理器 |
| Git Hooks | lefthook | pre-commit 执行 Biome lint |

---

## 六、API 设计

### 6.1 Registry API

**Base URL**: `https://registry.genehub.dev/api/v1`（初期可本地部署）

#### 基因查询

| 方法 | 路径 | 说明 | 状态 |
|------|------|------|------|
| GET | `/genes` | 搜索基因列表（支持 q / category / tags / compatibility / sort） | 已实现 |
| GET | `/genes/tags` | 标签统计（tag + count） | 已实现 |
| GET | `/genes/featured` | 推荐基因列表（按安装量/评分排序） | 已实现 |
| GET | `/genes/:slug` | 基因详情（最新版本） | 已实现 |
| GET | `/genes/:slug/versions` | 版本列表 | 已实现 |
| GET | `/genes/:slug/versions/:version` | 指定版本详情 | 已实现 |
| GET | `/genes/:slug/manifest` | 获取 manifest（支持 `?version=x.y.z`） | 已实现 |
| GET | `/genes/:slug/files` | 文件列表（支持 `?version=x.y.z`） | 已实现 |
| GET | `/genes/:slug/files/*` | 获取文件内容（支持 `?version=x.y.z`） | 已实现 |
| GET | `/genes/:slug/archive` | 下载 tarball（支持 `?version=x.y.z`） | 已实现 |
| GET | `/genes/:slug/variants` | 变体列表（基于 `parent_gene_id`） | Future |
| GET | `/genes/:slug/synergies` | 协同推荐 | 已实现 |
| GET | `/genes/:slug/reviews` | 审核记录列表（分页） | 已实现 |

#### 基因组查询

| 方法 | 路径 | 说明 | 状态 |
|------|------|------|------|
| GET | `/genomes` | 搜索基因组 | 已实现 |
| GET | `/genomes/featured` | 推荐基因组列表 | 已实现 |
| GET | `/genomes/:slug` | 基因组详情 | 已实现 |
| GET | `/genomes/:slug/resolve` | 解析并返回所有基因的 manifest（含依赖） | 已实现 |
| GET | `/genomes/:slug/versions` | 基因组版本列表 | 已实现 |
| GET | `/genomes/:slug/versions/:version` | 指定基因组版本详情 | 已实现 |
| GET | `/genomes/:slug/files` | 文件列表（支持 `?version=x.y.z`） | 已实现 |
| GET | `/genomes/:slug/files/*` | 获取文件内容（支持 `?version=x.y.z`） | 已实现 |
| GET | `/genomes/:slug/archive` | 下载 tarball（支持 `?version=x.y.z`） | 已实现 |

#### 基因管理

| 方法 | 路径 | 说明 | 状态 |
|------|------|------|------|
| POST | `/genes` | 发布新基因（需 publisher） | 已实现 |
| POST | `/genes/:slug/versions` | 发布新版本（需 publisher） | 已实现 |
| PUT | `/genes/:slug` | 更新基因元数据（需 publisher） | 已实现 |
| DELETE | `/genes/:slug` | 删除基因（需 admin，软删除） | 已实现 |
| POST | `/genes/:slug/deprecate` | 废弃基因 | Future |

#### 基因组管理

| 方法 | 路径 | 说明 | 状态 |
|------|------|------|------|
| POST | `/genomes` | 创建基因组（需 publisher） | 已实现 |
| POST | `/genomes/:slug/versions` | 发布基因组新版本（需 publisher） | 已实现 |
| PUT | `/genomes/:slug` | 更新基因组（需 publisher） | 已实现 |
| DELETE | `/genomes/:slug` | 删除基因组（需 admin） | 已实现 |

#### AI 员工模板

| 方法 | 路径 | 说明 | 状态 |
|------|------|------|------|
| GET | `/templates` | 搜索模板列表（支持 q / category / role / sort） | 已实现 |
| GET | `/templates/featured` | 推荐模板列表 | 已实现 |
| GET | `/templates/:slug` | 模板详情 | 已实现 |
| GET | `/templates/:slug/versions` | 版本列表 | 已实现 |
| GET | `/templates/:slug/versions/:version` | 指定版本 | 已实现 |
| GET | `/templates/:slug/files` | 文件列表（支持 `?version=x.y.z`） | 已实现 |
| GET | `/templates/:slug/files/*` | 获取文件内容 | 已实现 |
| GET | `/templates/:slug/archive` | 下载 tarball | 已实现 |
| POST | `/templates` | 创建模板（需 publisher） | 已实现 |
| POST | `/templates/:slug/versions` | 发布新版本（需 publisher） | 已实现 |
| PUT | `/templates/:slug` | 更新（需 publisher） | 已实现 |
| DELETE | `/templates/:slug` | 删除（需 admin） | 已实现 |
| POST | `/templates/:slug/installed` | 安装计数上报 | 已实现 |

#### 效能与统计

| 方法 | 路径 | 说明 | 状态 |
|------|------|------|------|
| POST | `/genes/:slug/installed` | 安装计数上报 | 已实现 |
| POST | `/genes/:slug/effectiveness` | 效能数据上报（EMA 算法） | 已实现 |
| POST | `/genomes/:slug/installed` | 基因组安装计数上报 | 已实现 |
| POST | `/effectiveness/batch` | 批量效能上报 | Future |

删除基因/基因组/模板时，先删除 Gitea 对应仓库再删除 DB 记录；Gitea 删除失败时请求返回 5xx，避免 DB 已删但 Gitea 残留导致同 slug 无法再创建。

#### 审核

| 方法 | 路径 | 说明 | 状态 |
|------|------|------|------|
| POST | `/genes/:slug/reviews/:reviewId/feedback` | 人工反馈覆盖 AI 审核结论（需 admin） | 已实现 |

#### 依赖解析

| 方法 | 路径 | 说明 | 状态 |
|------|------|------|------|
| POST | `/resolve` | 解析依赖，返回安装计划（当前单基因，Future: 批量） | 已实现 |

#### 联邦搜索

| 方法 | 路径 | 说明 | 状态 |
|------|------|------|------|
| GET | `/genes/search?q=xxx` | 联邦搜索（本地 + ClawHub 实时查询，外部结果后台入库为 pending 待 AI 审核） | 已实现 |
| POST | `/import/git` | 从 Git 仓库导入基因 | Future |

#### 认证

| 方法 | 路径 | 说明 | 状态 |
|------|------|------|------|
| GET | `/auth/github` | GitHub OAuth 登录 | 已实现 |
| GET | `/auth/github/callback` | OAuth 回调 | 已实现 |
| POST | `/auth/logout` | 登出 | 已实现 |
| GET | `/auth/me` | 当前用户信息 | 已实现 |

#### API Key 管理

| 方法 | 路径 | 说明 | 状态 |
|------|------|------|------|
| POST | `/keys` | 创建 API Key（需 publisher） | 已实现 |
| GET | `/keys` | 列出 API Key（需 publisher） | 已实现 |
| DELETE | `/keys/:id` | 撤销 API Key（需 publisher） | 已实现 |

#### NoDeskClaw 同步与 Webhook

| 方法 | 路径 | 说明 | 状态 |
|------|------|------|------|
| POST | `/sync/nodeskclaw` | NoDeskClaw 批量同步（需 admin 白名单） | 已实现 |
| GET | `/sync/status` | 同步状态查询 | 已实现 |
| POST | `/webhooks/nodeskclaw/gene-created` | NoDeskClaw 基因创造回调 | 已实现 |
| POST | `/webhooks/nodeskclaw/gene-learned` | NoDeskClaw 基因学习回调 | 已实现 |
| POST | `/webhooks/nodeskclaw/effectiveness` | NoDeskClaw 效能数据回调 | 已实现 |

#### ~~外部基因同步~~（已弃用）

> **弃用说明**：定期同步接口已弃用，改用联邦搜索。外部基因源通过联邦搜索实时查询并后台
> 入库为 `pending` 状态，由 AI Curator 审核通过后发布。
> 仅保留 NoDeskClaw 同步用于历史数据批量导入（白名单，直接 approved）。
> 接口将于 2026-06-01 下线。

| 方法 | 路径 | 说明 |
|------|------|------|
| ~~POST~~ | ~~`/sync/clawhub`~~ | ~~触发 ClawHub 同步~~ → 改用联邦搜索 |
| ~~POST~~ | ~~`/sync/evomap`~~ | ~~请求 Evomap 推荐~~ → 改用联邦搜索 |

### 6.2 统一响应格式

```json
{
  "code": 0,
  "message": "success",
  "data": {}
}
```

错误响应：

```json
{
  "code": 40001,
  "error_code": "gene_not_found",
  "message": "基因不存在",
  "data": null
}
```

---

## 七、项目结构

```
genehub/
├── docs/                           # 设计文档
│   ├── architecture.md             # 架构设计（本文档）
│   └── gene-learning-protocol.md   # 标准学习协议规范
│
├── packages/
│   ├── types/                      # 共享类型定义（@nodeskai/genehub-types）
│   │   └── src/
│   │       ├── manifest.ts         # Gene Manifest Zod Schema
│   │       ├── api.ts              # API 类型 + 错误码
│   │       └── index.ts
│   │
│   ├── registry/                   # Gene Registry Service（@nodeskai/genehub-registry）
│   │   ├── src/
│   │   │   ├── api/                # API 路由（genes / genomes / auth / keys / reviews / resolve / sync / webhooks）
│   │   │   ├── services/           # 业务逻辑（gene-service / genome-service / gitea-service / federated-search / dependency-resolver / gene-events）
│   │   │   ├── db/                 # 数据库（Drizzle schema + migrations + seed）
│   │   │   ├── middleware/         # 中间件（auth / error-handler / response）
│   │   │   ├── mcp/               # MCP Server（22 个工具）
│   │   │   │   ├── tools/         # query / genome / template / manage / review
│   │   │   │   ├── server.ts      # MCP Server 定义
│   │   │   │   └── http.ts        # Streamable HTTP 传输
│   │   │   ├── adapters/          # 外部基因适配器
│   │   │   │   ├── clawhub/       # ClawHub 适配（client + converter + sync）
│   │   │   │   ├── evomap/        # Evomap 适配（client + converter + sync）
│   │   │   │   └── nodeskclaw/    # NoDeskClaw 适配（converter + sync）
│   │   │   └── index.ts
│   │   ├── curator/               # Gene Curator Agent 配置
│   │   │   ├── opencode.json      # 本地开发配置
│   │   │   ├── opencode-k8s.json  # K8s 生产配置
│   │   │   ├── AGENTS.md          # Curator 角色定义（系统提示词）
│   │   │   └── listener.ts        # 事件监听器（LISTEN/NOTIFY）
│   │   └── package.json
│   │
│   ├── sdk/
│   │   ├── typescript/             # TypeScript SDK（@nodeskai/genehub-sdk）
│   │   │   └── src/
│   │   │       ├── client.ts       # GeneHub API 客户端
│   │   │       ├── learning/       # 标准学习协议引擎（L1/L2）
│   │   │       └── adapters/       # 产品适配器（openclaw / nanobot / generic）
│   │   └── python/                 # Python SDK（genehub-sdk，最小可用）
│   │       ├── pyproject.toml
│   │       ├── src/genehub_sdk/
│   │       │   ├── client.py       # GeneHubClient
│   │       │   ├── types.py        # Gene / GeneManifest / 适配器类型
│   │       │   ├── adapters/       # GeneAdapter 基类 + GenericAdapter
│   │       │   └── learning/       # LearningEngine
│   │       └── tests/
│   │
│   ├── cli/                        # 命令行工具（@nodeskai/genehub）
│   │   └── src/
│   │       └── commands/           # install / uninstall / search / list / publish / init / config / auth / learn / genome / template
│   │
│   └── web/                        # Web 前端（React 19 + Vite + Tailwind CSS 4）
│       └── src/
│           ├── pages/              # Home / Browse / GeneDetail / GenomeBrowse / GenomeDetail / TemplateBrowse / TemplateDetail / Settings
│           ├── components/         # Layout / GeneCard / GenomeCard / TemplateCard / FederatedSearchCard / ReviewList / VersionHistory
│           ├── components/ui/      # button / badge / card / input / skeleton / separator / tabs / tooltip
│           └── api/                # API 请求封装
│
├── genes/                          # 官方基因库（Git 管理，8 个基因）
│   └── skills/
│       └── <gene-slug>/
│           ├── gene.yaml           # 基因元数据
│           └── SKILL.md            # 技能内容
│
├── deploy/                         # 部署配置
│   └── k8s/
│       ├── genehub.yaml            # Registry + Web 部署
│       ├── gitea.yaml              # Gitea 基因文件存储
│       ├── curator.yaml            # Curator CronJob + Listener
│       └── postgres.yaml           # PostgreSQL StatefulSet
│
├── scripts/                        # 工具脚本
│   ├── init-gitea.sh              # Gitea 初始化（创建 admin + genes/genomes/templates 三个 org）
│   └── sync-version.mjs           # 版本号同步
│
├── .github/workflows/              # CI/CD
│   ├── ci.yml                      # lint + build + test
│   └── release.yml                 # npm publish + Docker build + K8s deploy
│
├── VERSION                         # 项目版本号
├── CHANGELOG.md
├── lefthook.yml                    # pre-commit lint hook
├── biome.json                      # Biome 配置
├── README.md
├── AGENTS.md                       # 开发指南
├── package.json                    # monorepo 根配置
└── pnpm-workspace.yaml
```

> **未实现的目录**（计划中）：
> - ~~`packages/sdk/python/`~~ — Python SDK 已实现最小可用（Client + Adapter + GenericAdapter + LearningEngine）
> - `adapters/` — 安装方式兼容层（clawhub / npm / pip，后续扩展）
> - `genes/rules/`、`genes/protocols/` — 规则类、协议类基因（当前仅有 skills 分类）

---

## 八、与 NoDeskClaw 集成方案

### 8.1 迁移路径

| 阶段 | 动作 | NoDeskClaw 影响 |
|------|------|----------------|
| Phase 1 | GeneHub Registry 独立部署，导入 NoDeskClaw 现有基因数据 | NoDeskClaw 保持现有功能不变 |
| Phase 2 | NoDeskClaw 基因市场 API 改为代理转发到 GeneHub | 前端无感知，后端 gene_service 添加 GeneHub 客户端 |
| Phase 3 | NoDeskClaw 学习引擎接入标准学习协议 | Learning Channel Plugin 无需改动，gene_service 适配 |
| Phase 4 | NoDeskClaw genes 表降级为本地缓存 | 基因元数据以 GeneHub 为主，本地缓存加速 |

### 8.2 API 映射

| NoDeskClaw 现有 API | GeneHub 替代 |
|---------------------|-------------|
| `GET /genes` | `GET /api/v1/genes` (Registry) |
| `GET /genes/:id` | `GET /api/v1/genes/:slug` (Registry) |
| `POST /genes/:id/rate` | `POST /api/v1/genes/:slug/rate` (Registry) |
| `POST /instances/:id/genes/install` | 保留（实例级操作留在 NoDeskClaw，拉取 manifest 从 GeneHub） |
| `POST /genes/learning-callback` | 保留（学习回调留在 NoDeskClaw） |

### 8.3 数据同步

```
GeneHub Registry                     NoDeskClaw
     │                                    │
     │  GET /genes/:slug/manifest         │
     │ ◄──────────────────────────────────│ (install_gene 时拉取)
     │                                    │
     │  POST /genes (Agent 创造)           │
     │ ◄──────────────────────────────────│ (creation_callback 后推送)
     │                                    │
     │  POST /genes/:slug/effectiveness   │
     │ ◄──────────────────────────────────│ (效能数据回传)
     │                                    │
     │  Webhook: 新基因/版本通知           │
     │ ──────────────────────────────────►│ (主动推送)
     │                                    │
```

---

## 九、外部基因获取

### 9.1 ClawHub 适配

> ClawHub（clawhub.ai）是 OpenClaw 官方的公共技能注册中心，拥有 3,286 个技能、1.5M+ 下载量。
> 技术栈：TanStack Start + Convex + OpenAI embeddings 向量搜索。
> GitHub：openclaw/clawhub（3,131 stars）

#### 交互流程（联邦搜索，当前方案）

```
用户搜索 q="memory"
        │
        ▼
   GeneHub API (GET /genes/search)
        │
        ├─── 本地 DB (ILIKE)         → 本地结果 (source: local)
        │
        └─── ClawHub API (实时搜索)   → 远程结果 (source: clawhub)
                                       ↓
                             去重（本地优先）→ 分数归一化 → 合并排序 → 返回
```

ClawHub 结果**不入库**，仅作为外部知识源实时查询。ClawHub 超时或失败时优雅降级，只返回本地结果。

#### ~~交互流程（定期同步，已弃用）~~

> 以下为旧的定期同步方案，已弃用。保留文档供参考。

```
ClawHub (clawhub.ai)            GeneHub
     │  1. 搜索 → 2. 详情 → 3. 下载 → 4. 转换 → 5. 存入（已弃用）
```

#### ClawHub 技能格式

```yaml
# SKILL.md frontmatter
---
name: my-skill
description: Does a thing with an API.
metadata:
  openclaw:
    requires:
      env:
        - MY_API_KEY
      bins:
        - curl
    primaryEnv: MY_API_KEY
---
# 技能内容（Markdown）
```

#### 转换规则

| ClawHub 字段 | GeneHub gene.yaml 字段 |
|-------------|----------------------|
| `name` | `name` + `slug`（kebab-case） |
| `description` | `description` / `short_description` |
| `metadata.openclaw.requires` | `config.openclaw` |
| `tags` | `tags` |
| 技能正文 | `skill.content`（SKILL.md） |
| 下载量 / 星标数 | `install_count` / `avg_rating` |
| — | `source: clawhub` |
| 技能 URL | `source_ref` |

#### ClawHub CLI 协议参考

```bash
clawhub search "query"            # 语义搜索
clawhub install <slug>            # 安装（下载 zip → 解压到 ./skills/）
clawhub publish <path>            # 发布
clawhub sync                      # 批量同步
```

#### 安全注意事项

2026-02 ClawHavoc 事件：341 个恶意技能被发现，ClawHub 已接入 VirusTotal 扫描。
GeneHub 同步时应：跳过被标记/隐藏的技能、校验技能包完整性、记录审计日志。

### 9.2 Evomap 适配

> EvoMap（evomap.ai）是 AI 自进化基础设施平台，基于 Genome Evolution Protocol（GEP）。
> 核心引擎：Capability Evolver，实时分析日志 → 提取信号 → 生成/验证策略 → 固化能力。
> GitHub：EvoMap/evolver（872 stars）

#### GEP 协议核心概念

| GEP 概念 | 说明 | GeneHub 映射 |
|----------|------|-------------|
| Gene | 原子能力单元（如 "read file"、"execute SQL"） | Gene Manifest |
| Capsule | 成功执行路径的封装，复合问题解决方案 | Genome（基因组） |
| Event | 不可变的突变/修复日志，完整上下文记录 | GeneVersion changelog |

#### 交互流程

```
EvoMap (evomap.ai)              GeneHub
  │                                │
  │  1. 提交 Agent 能力画像         │
  │ ◄──────────────────────────────│ (当前已安装基因 + 效能数据)
  │                                │
  │  2. Evolver 分析 + 推荐        │
  │ ──────────────────────────────►│ (推荐基因/Capsule 组合)
  │                                │
  │  3. GeneHub 解析推荐            │
  │     GEP Gene → gene.yaml      │
  │     GEP Capsule → genome      │
  │                                │
  │  4. 效能数据回传                │
  │ ◄──────────────────────────────│ (用于进化信号分析)
  │                                │
```

#### Evolver 策略模式

```bash
EVOLVE_STRATEGY=balanced      # 平衡模式（默认）
EVOLVE_STRATEGY=innovate      # 最大化新能力
EVOLVE_STRATEGY=harden        # 聚焦稳定性
EVOLVE_STRATEGY=repair-only   # 紧急修复模式
```

---

## 十、安装兼容性

### 10.1 安装方式矩阵

| 安装方式 | 命令 | 适用场景 |
|---------|------|---------|
| GeneHub CLI | `genehub install <slug>` | 标准方式，全功能 |
| claw install | `claw install @genehub/<slug>` | ClawHub 生态兼容 |
| npx | `npx genehub install <slug>` | 前端 / Node.js 项目 |
| pip | `pip install genehub-<slug>` | Python Agent 项目 |
| Git Clone | `git clone .../<slug>.git` | 开发者直接引用 |
| HTTP API | `POST /install` | 程序化调用（NoDeskClaw 等） |

### 10.2 CLI 安装流程

```
genehub install code-review

  1. 查询 Registry: GET /genes/code-review/manifest
  2. 解析依赖: POST /resolve { genes: ["code-review"] }
  3. 检测目标产品: 自动识别当前环境（openclaw / nanobot / 通用）
  4. 下载基因文件:
     ├── 优先: GET /genes/code-review/archive -> tar.gz 下载 + 解压到临时目录
     └── 降级: 使用 manifest 中的 skill.content（旧基因兼容）
  5. 调用对应 Adapter 注入基因
     ├── 多文件基因: adapter.installFromDirectory(tempDir, manifest)
     ├── OpenClaw: 写入 SKILL.md + 合并 openclaw.json
     ├── nanobot: 配置注入
     └── Generic: 复制整个基因目录到 .genehub/genes/
  6. 验证安装结果
  7. 输出安装报告
```

### 10.3 后续扩展（DeskClaw 等）

> DeskClaw Adapter 属于后续扩展计划，初期不实现。以下为预留设计参考。

DeskClaw 使用 Cursor Rules（`.cursor/rules/*.mdc`）和 Skills（SKILL.md）管理能力。GeneHub 的 DeskClaw Adapter 负责：

| Gene Manifest 字段 | DeskClaw 映射 |
|-------------------|-------------|
| `skill.content` | `.cursor/skills/<slug>/SKILL.md` |
| `rules` | `.cursor/rules/<slug>.mdc` |
| `config` | 合并到项目配置 |

---

## 十一、AI 能力（OpenCode + MCP）

GeneHub 内置了一套基于 **OpenCode**（开源终端 AI 框架）和 **MCP**（Model Context Protocol）的 AI 能力体系，用于自动化基因库管理。

### 11.1 架构总览

```
                    ┌──────────────────────────────────────┐
                    │     Gene Curator (K8s Pod)            │
                    │     OpenCode + MiniMax LLM            │
                    │                                      │
                    │  ┌────────────────────────────────┐  │
                    │  │ system-prompt.md               │  │
                    │  │ 角色定义 + 巡检流程 + 权限边界   │  │
                    │  └────────────────────────────────┘  │
                    └──────────────┬───────────────────────┘
                                   │ MCP (Streamable HTTP)
                                   │ POST http://genehub/mcp
                                   ▼
┌──────────────────────────────────────────────────────────────────┐
│                    GeneHub Registry (K8s Pod)                     │
│                                                                  │
│   Hono HTTP Server (:3000)                                       │
│   ├── /api/v1/genes    REST API                                  │
│   ├── /api/v1/genomes  REST API                                  │
│   └── /mcp             MCP Streamable HTTP (token-gated)         │
│                                                                  │
│   MCP 20 Tools:                                                  │
│     Query:  list_genes / get_gene / search_genes /               │
│             find_similar / get_library_stats / evaluate_in_context│
│     Genome: list_genomes / get_genome /                          │
│             suggest_genome / validate_genome                      │
│     Manage: update_gene_category / update_gene_description /     │
│             update_gene_synergies / merge_genes                   │
│     Review: post_review / flag_for_deletion / approve_gene       │
│                           │                                      │
└───────────────────────────┼──────────────────────────────────────┘
                            │ SQL
                            ▼
                    ┌───────────────┐
                    │  PostgreSQL   │
                    │  gene_events  │◄── LISTEN/NOTIFY
                    └───────┬───────┘
                            │
                  ┌─────────┴──────────┐
                  ▼                    ▼
         ┌──────────────┐    ┌──────────────────┐
         │ gene-service  │    │ curator/listener │
         │ emitGeneEvent │    │ 实时事件监听       │
         └──────────────┘    └──────────────────┘
```

### 11.2 MCP Server

GeneHub MCP Server 将基因库能力暴露为 22 个标准 MCP 工具，任何支持 MCP 协议的 AI 框架（OpenCode、Claude Code、Cursor 等）都可以接入。

**代码位置**：`packages/registry/src/mcp/`

```
src/mcp/
├── server.ts          # MCP Server 定义，注册所有工具
├── http.ts            # Streamable HTTP 传输（挂载到 Hono /mcp）
├── index.ts           # stdio 传输入口（本地开发 / CLI）
└── tools/
    ├── query.ts       # 6 个查询工具
    ├── genome.ts      # 4 个基因组工具
    ├── template.ts    # 3 个模板工具
    ├── manage.ts      # 4 个管理工具
    └── review.ts      # 5 个审核工具
```

**传输方式**：

| 传输 | 端点 | 使用场景 |
|------|------|---------|
| **Streamable HTTP** | `POST /mcp` | K8s 内 Curator Agent、外部 MCP 客户端（需 Bearer Token） |
| stdio | `node dist/mcp/index.js` | 本地开发、CLI 调试 |

**启动方式**：

```bash
# 开发模式（stdio）
pnpm --filter @nodeskai/genehub-registry mcp:dev

# 生产模式 — HTTP 传输随主应用自动启动
# Curator 通过 http://genehub/mcp 连接，无需单独启动 MCP Server
```

**MCP 工具一览**：

| 类别 | 工具 | 说明 |
|------|------|------|
| 查询 | `list_genes` | 列出基因，按分类/来源/审核状态过滤 |
| 查询 | `get_gene` | 基因详情 + 已有点评 + 关联关系 |
| 查询 | `search_genes` | 关键词搜索 |
| 查询 | `find_similar` | 查找相似/重复候选 |
| 查询 | `get_library_stats` | 基因库总览统计 |
| 查询 | `evaluate_in_context` | 上下文评估：在已有库的背景下评价此基因 |
| 基因组 | `list_genomes` | 列出基因组，按分类和关键词过滤 |
| 基因组 | `get_genome` | 基因组详情 + 版本历史 |
| 基因组 | `suggest_genome` | 根据需求描述推荐合适的基因组 |
| 基因组 | `validate_genome` | 校验基因组合法性（存在性、发布状态、冲突检测） |
| 模板 | `list_templates` | 列出 AI 员工模板，按分类/角色/关键词过滤 |
| 模板 | `get_template` | 模板详情 + 版本历史 |
| 模板 | `suggest_template` | 根据需求描述推荐模板 |
| 管理 | `update_gene_category` | 重分类（需提供理由） |
| 管理 | `update_gene_description` | 改善描述文本 |
| 管理 | `update_gene_synergies` | 设置关联关系（synergy/conflict/extends/replaces） |
| 管理 | `merge_genes` | 合并重复基因 |
| 审核 | `post_review` | 发布点评（评分 0-10 + 评语） |
| 审核 | `flag_for_deletion` | 标记待删除（人工确认后才会删除） |
| 审核 | `approve_gene` | 审核通过基因 |
| 审核 | `review_genome` | 审核基因组（评分 + 评语 + 状态） |
| 审核 | `review_template` | 审核 AI 员工模板（评分 + 评语 + 状态） |

### 11.3 Gene Curator（基因库管理员）

Gene Curator 是一个自主运行的 AI Agent，基于 **OpenCode** 框架驱动，通过 MCP 工具与 GeneHub 交互，负责基因库的日常管理。

**配置文件**：`packages/registry/curator/`

```
curator/
├── opencode.json      # 本地开发配置（MCP stdio）
├── opencode-k8s.json  # K8s 生产配置（MCP Streamable HTTP → http://genehub/mcp）
├── opencode-prod.json # 本地连线上配置（kubectl exec）
├── AGENTS.md          # Curator 的角色定义和工作规范（支持基因 / 基因组 / 模板审核）
└── listener.ts        # 实时事件监听器（PostgreSQL LISTEN/NOTIFY）
```

#### 使用 OpenCode 驱动 Curator

**前置条件**：

1. 安装 OpenCode：`npm install -g opencode` 或 `brew install opencode`
2. 设置 LLM API Key：`export MINIMAX_API_KEY="sk-xxx"`
3. 确保 PostgreSQL 正在运行且 GeneHub Registry 已迁移

**OpenCode 配置**：

| 配置文件 | MCP 传输 | 使用场景 |
|---------|---------|---------|
| `opencode.json` | stdio (local) | 本地开发，MCP 直连本地 DB |
| `opencode-k8s.json` | Streamable HTTP (remote) | K8s 部署，连接 `http://genehub/mcp` |
| `opencode-prod.json` | kubectl exec | 本地调试线上环境 |

**手动运行 Curator（本地）**：

```bash
cd packages/registry

# 先构建 MCP Server
pnpm build

# 方式一：交互式对话（调试用）
cd curator
MINIMAX_API_KEY="sk-xxx" opencode

# 方式二：单次任务执行
cd curator
MINIMAX_API_KEY="sk-xxx" opencode run "审核最近新入库的基因"

# 方式三：全面巡检
MINIMAX_API_KEY="sk-xxx" opencode run "执行基因库全面巡检"
```

> **注意**：`opencode` 自动读取当前目录的 `opencode.json`，无需 `--config` 参数。

**也可以使用其他 MCP 兼容的 AI 框架**：

```bash
# 方式一：通过 HTTP（推荐，GeneHub 运行中即可用）
# 任何 MCP 客户端连接 http://localhost:3000/mcp 即可

# 方式二：通过 stdio（本地开发）
# Claude Code
claude --mcp-config '{"genehub":{"command":"node","args":["dist/mcp/index.js"]}}' \
  "审核最近新入库的基因"
```

### 11.4 事件驱动架构

基因库的变更事件通过 PostgreSQL 原生的 `LISTEN/NOTIFY` 机制发布，无需额外消息队列。

**事件发布**（`services/gene-events.ts`）：

```sql
NOTIFY gene_events, '{"type":"gene.created","slug":"xxx","source":"clawhub"}'
```

**支持的事件类型**：

| 事件 | 触发时机 |
|------|----------|
| `gene.created` | 新基因入库 |
| `gene.updated` | 基因版本发布或元数据更新 |
| `gene.reviewed` | Curator 发布点评 |
| `gene.flagged` | 基因被标记待删除 |

**事件监听器**（`curator/listener.ts`）：

监听 `gene_events` 频道，收到 `gene.created` 事件后自动触发 OpenCode 运行 Curator 审核新基因。

```bash
# 启动事件监听器（本地开发）
cd packages/registry/curator
DATABASE_URL="postgres://genehub:genehub@localhost:5432/genehub" \
MINIMAX_API_KEY="sk-xxx" \
tsx listener.ts
```

### 11.5 联邦搜索

搜索 API 支持同时查询本地 GeneHub 数据库和 ClawHub 外部 API，结果合并后按来源标记返回。

**端点**：`GET /api/v1/genes/search?q=xxx`

**工作流程**：

```
用户搜索 → 并行查询 ─┬─ 本地 DB (ILIKE)    → 本地结果 (source: local)
                     └─ ClawHub API (搜索) → 远程结果 (source: clawhub)
                                            ↓
                                  去重（本地优先）→ 分数归一化 → 合并排序 → 返回
                                            ↓ (后台 fire-and-forget)
                                  ClawHub 新结果 → downloadFile 下载 SKILL.md
                                       ↓                ↓
                                  创建 Gitea 仓库 → 上传 gene.yaml + SKILL.md → 打 tag
                                       ↓
                                  入库 DB（含 repository_url / commit_sha / git_tag / files）
                                       ↓
                                  发 gene.created 事件 → Curator AI 审核
```

**设计原则**：
- ClawHub 结果**立即展示**，用户无需等待入库
- 后台自动将新的外部结果入库为 `pending` + `is_published: false`，触发 AI 审核
- **入库时同步下载 ClawHub 文件内容，创建 Gitea 仓库存储**，确保版本历史和文件浏览可用
- 审核通过后 `approved` + `is_published: true`，后续搜索将作为本地结果命中
- 入库时通过 slug 去重，已存在的不重复插入
- ClawHub 下载失败或 Gitea 不可用时优雅降级：仍然入库但无文件仓库
- ClawHub 超时或失败时优雅降级，只返回本地结果
- NoDeskClaw 同步为白名单，直接 `approved` 入库
- 返回 `sources` 字段标明各来源命中数量

**响应示例**：

```json
{
  "code": 0,
  "data": {
    "query": "memory",
    "total": 10,
    "items": [
      { "slug": "memory", "name": "记忆管理", "source": "local", "score": 1.0 },
      { "slug": "elite-longterm-memory", "name": "Elite Longterm Memory", "source": "clawhub", "score": 0.85 }
    ],
    "sources": { "local": 6, "clawhub": 4 }
  }
}
```

### 11.6 K8s 部署

**镜像**：

| 镜像 | Dockerfile | 内容 |
|------|-----------|------|
| `genehub` | `Dockerfile` | Registry + MCP HTTP Server + Web UI |
| `genehub-curator` | `Dockerfile.curator` | OpenCode CLI + tsx + Curator 配置 |

**Curator 部署清单**：`deploy/k8s/curator.yaml`

| 资源 | 类型 | 说明 |
|------|------|------|
| `gene-curator` | CronJob | 每 6 小时执行一次全面巡检 |
| `gene-curator-listener` | Deployment | 常驻进程，监听 `gene_events` 实时触发审核 |

**MCP 通信**：Curator Pod 通过 `POST http://genehub/mcp`（ClusterIP Service）连接 GeneHub MCP Server，使用 `GENEHUB_ADMIN_TOKEN` Bearer 认证。

**所需 Secrets**（统一使用 `genehub-app-secret`）：

```yaml
DATABASE_URL: postgres://...
GENEHUB_ADMIN_TOKEN: ghb_admin_xxx
MINIMAX_API_KEY: sk-xxx
```

**CI/CD**：`release.yml` 自动构建两个镜像、推送到 Volcengine CR、部署 GeneHub + Curator。

---

## 十二、里程碑

### M0 - 基础设施

- [x] 项目 monorepo 搭建（packages/types + registry + sdk + cli）
- [x] Gene Manifest 规范定稿（`docs/gene-learning-protocol.md`）+ Zod schema
- [x] 数据模型与数据库 schema 设计（Drizzle ORM + PostgreSQL）
- [x] Registry API 骨架（CRUD + 搜索 + 统一响应/错误处理）
- [x] CLI 骨架（install / search / list / publish / init）

### M1 - 核心功能 ✅

- [x] Registry 完整 API（版本管理、依赖解析、兼容校验、认证中间件、效能数据上报）
- [x] TypeScript SDK（客户端 + OpenClaw Adapter L1 + nanobot Adapter L1 + Generic Adapter）
- [x] Learning Engine（L1 浅层学习 + L2 深度学习引擎 + genehub-learner 元学习基因）
- [x] CLI 完整命令集（install/uninstall/search/list/publish/init/config/learn）
- [x] NoDeskClaw 集成（→ M2.1，已合并）
- [x] 官方基因库（8 个高质量基因含 learning objectives + scenarios）

### M2 - 生态对接

#### M2.1 — NoDeskClaw 集成（最高优先级，M1 遗留）

将 GeneHub 与 NoDeskClaw 打通，使 NoDeskClaw 的基因市场以 GeneHub 为后端。

- [x] GeneHub 侧基础设施：Webhook 端点、NoDeskClaw Adapter（Client + Converter + Sync）、批量导入脚本
- [x] K8s 部署清单配置 `NODESKCLAW_DATABASE_URL` / `GENEHUB_WEBHOOK_SECRET`
- [x] GeneHub 补齐缺失 API：`/genes/tags`、`/genes/featured`、`/genes/:slug/synergies`、`/genomes/featured`
- [x] NoDeskClaw 基因市场 API 代理转发到 GeneHub Registry（Phase 2，`feat/genehub-integration` 分支）
- [x] NoDeskClaw 学习引擎接入 GeneHub 标准学习协议（Phase 3，manifest 从 GeneHub 拉取）
- [x] NoDeskClaw `genes` 表降级为本地缓存，GeneHub 为数据主源（Phase 4，`synced_at` 字段 + upsert 策略）

#### M2.2 — ClawHub Adapter ✅

从 ClawHub（clawhub.ai，OpenClaw 官方技能市场）拉取社区技能到 GeneHub。

- [x] ClawHub API 客户端（搜索 / 获取技能详情 / 下载技能包）
- [x] 格式转换：ClawHub `SKILL.md` frontmatter → GeneHub `gene.yaml` Manifest
- [x] ~~定时同步 / 手动触发同步（`POST /sync/clawhub`）~~ → **已弃用**，改用联邦搜索
- [x] 来源溯源：`source=clawhub` + `source_ref` 指向 ClawHub 原始 URL
- [x] 安全审查：过滤 ClawHavoc 事件后被标记的恶意技能
- [x] **联邦搜索（当前方案）**：实时查询 ClawHub API，后台下载文件并存储到 Gitea，按来源标记

#### M2.3 — Evomap Adapter ✅

对接 EvoMap（evomap.ai，AI 自进化基础设施）的 GEP 协议，获取进化推荐。

- [x] GEP 协议数据结构映射：EvoMap Gene/Capsule/Event → GeneHub Gene Manifest
- [x] Evolver 推荐接口对接：提交 Agent 能力画像 → 获取推荐基因组合
- [x] 进化信号集成：将 GeneHub 的效能数据回传给 EvoMap 用于进化分析
- [x] ~~`POST /sync/evomap`：请求 Evomap 推荐并导入推荐基因~~ → **已弃用**，改用联邦搜索

#### M2.4 — 推迟到 M3

- Python SDK（暂不紧急）
- npm / pip 分发支持（依赖 Python SDK）

### M3 - AI 能力 + 进阶功能 ✅（AI 部分）

- [x] MCP Server（22 个工具：查询 6 + 基因组 4 + 模板 3 + 管理 4 + 审核 5）
- [x] Gene Curator Agent（OpenCode 配置 + AGENTS.md 提示词 + 事件监听器，支持基因/基因组/模板审核）
- [x] 事件驱动架构（PostgreSQL LISTEN/NOTIFY + gene_events）
- [x] 联邦搜索（本地 DB + ClawHub + Evomap 并行查询、去重、分数归一化）
- [x] 基因审核 API（`gene_reviews` 统一表，支持 gene/genome/template 三种实体类型）
- [x] 基因关系模型（`gene_relations`：synergy / conflict / extends / replaces）
- [x] 基因组版本管理（`genome_versions` + resolve 解析）
- [x] K8s 部署清单（CronJob 定期巡检 + Deployment 实时监听）
- [x] Web 前端（React 19 + Vite + Tailwind CSS 4，8 个页面 + 16 个组件）
- [x] Gitea 集成（基因/基因组/模板文件 Git 版本管理、archive 下载）
- [x] Web 管理员功能（未发布内容筛选、审核状态过滤）
- [x] Web 版本历史展开查看文件内容和安装命令
- [x] GitHub OAuth + API Key 认证 + 管理员角色
- [x] GitHub Actions CI/CD（lint + build + test + npm publish + Docker deploy + K8s rolling update）
- [x] Python SDK（最小可用：GeneHubClient、GeneAdapter、GenericAdapter、LearningEngine）
- [ ] npm / pip 分发支持
- [ ] 基因效能数据聚合与排行
- [ ] 全文搜索升级（Meilisearch）
- [ ] DeskClaw Adapter（后续扩展）
- [ ] CLI `info` 命令
- [x] CLI `search` 接入联邦搜索（默认联邦，`--local` 仅本地）
- [x] SDK `federatedSearch()` 方法
- [ ] `POST /resolve` 批量解析
- [ ] `GET /genes/:slug/variants` 变体列表
- [ ] `POST /genes/:slug/deprecate` 废弃基因
- [ ] `POST /import/git` Git 仓库导入
- [ ] `POST /effectiveness/batch` 批量效能上报

---

## 十三(bis)、企业私有基因库

GeneHub = 公共基因注册中心（强制开源）。企业私有基因留在 NoDeskClaw（安全隔离）。

| 维度 | GeneHub | NoDeskClaw |
|------|---------|-----------|
| 定位 | 公共社区 | 企业私有 |
| 基因来源 | 社区贡献 / Agent 创造 | 企业内部 Agent 涌现 |
| 访问控制 | 公开读，发布需认证 | 企业内部访问 |
| 基因市场数据 | GeneHub 生产 API | 企业私有市场页面 |

## 十三(ter)、基因回馈与进化

Agent 涌现的新能力可以回馈到基因生态：

- Agent 涌现新能力 -> 自发或外部驱动分享
- 企业内部 Agent 反馈 -> 默认存企业私有库
- 手动或通过 public 接口推送到 GeneHub（公开分享）
- 社交进化：Agent A 通过 learning channel 指导 Agent B 学习

## 十三(quater)、效能评定机制

- 用户点赞/点踩 -> 对应 skill 评分 +/-
- Agent 自评通过 API 推送（EMA 算法，alpha=0.3）
- 使用频率加分（使用 = +分，不用不扣分）
- 建立淘汰机制（零效能基因标记/下架）

## 十三(quinque)、学习通道设计

学习通道 = 对 bot 的一次 CLI 非交互对话调用，bot 基于 genehub-learner 技能自主完成学习。

**工作流程**：

1. `genehub install <gene> --learn` 安装基因
2. CLI 创建学习任务文件 `learning-tasks/{slug}.md`
3. CLI 调用平台 CLI 触发 bot 对话（`GeneAdapter.triggerLearning()`）
4. bot 发现 learning-tasks/ 中的任务，自主学习，写入结果
5. `genehub learn --check <slug>` 检查结果并应用

**各平台触发方式**：

| 平台 | 命令 | 状态 |
|------|------|------|
| OpenClaw | `openclaw agent --message "..."` | 已实现 |
| nanobot | `nanobot run --prompt "..."` | 试验性 |
| DeskClaw | 待定 | 未实现 |

**串行学习**：学习任务文件中通过 `order` 字段排序，genehub-learner 按序逐个处理。

---

## 十三、开放问题

| # | 问题 | 结论 | 状态 |
|---|------|------|------|
| 1 | GeneHub 是独立部署还是嵌入 NoDeskClaw | 独立部署，NoDeskClaw 作为客户端 | 已确认 |
| 2 | 基因文件存储用数据库还是 Git 仓库 | Gitea 自托管 Git：每个基因一个仓库，git tag 管理版本，DB 仅存索引元数据 | 已实现 |
| 3 | Registry 是否对外公开 | 初期内网部署，后期开放公共 Registry | 已确认 |
| 4 | ClawHub API 协议 | Convex HTTP API，技能格式为 SKILL.md + frontmatter，有完整 CLI | 已调研 |
| 5 | Evomap GEP 协议 | Gene/Capsule/Event 三层结构，Evolver 引擎 + 能力市场 | 已调研 |
| 6 | 恶意技能过滤策略 | 依靠 AI Curator Agent 自动发现并标记，无需外部扫描服务 | 已确认 |

---

*文档持续更新中。*
