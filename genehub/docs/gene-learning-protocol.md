# Gene Learning Protocol（标准学习协议）

> 版本：v0.1
> 日期：2026-02-27
> 状态：草稿

---

## 一、概述

Gene Learning Protocol（GLP）是 GeneHub 定义的标准化基因注入协议，规范了基因从 Registry 到 Agent 产品的完整生命周期：**发现 → 安装 → 学习 → 使用 → 遗忘**。

任何 Agent 产品只要实现 GLP 的 Adapter 接口，即可接入 GeneHub 生态。

### 1.1 设计原则

| 原则 | 说明 |
|------|------|
| 产品无关 | 协议不绑定任何特定 Agent 框架，初期支持 OpenClaw / nanobot，后续可扩展 DeskClaw 等 |
| 渐进式 | 最简实现只需 `install` + `uninstall`，高级能力（深度学习、遗忘仪式）按需实现 |
| 向后兼容 | NoDeskClaw 现有的 Learning Channel Plugin 通信协议是 GLP 的第一个实现 |
| 可扩展 | Manifest 结构支持产品专属扩展字段，不影响通用字段 |

### 1.2 术语定义

| 术语 | 含义 |
|------|------|
| Gene（基因） | 原子能力单元，包含技能内容 + 配置 + 元数据 |
| Genome（基因组） | 一组基因的引用 + 配置覆盖，组合配方 |
| Gene Manifest | 基因的标准描述格式，JSON / YAML |
| Adapter | 产品适配器，负责将 Manifest 翻译为产品原生格式 |
| Agent Host | 运行 Agent 的宿主环境（OpenClaw 实例、nanobot 等） |
| Learning Engine | Agent 的学习能力引擎（meta-learning 基因 / 内置学习模块） |

---

## 二、Gene Manifest 规范

Gene Manifest 是基因的标准描述文件，所有 GeneHub 基因必须包含一个有效的 Manifest。

### 2.1 Manifest 结构

```yaml
# gene.yaml - GeneHub 标准基因清单

# === 元数据 ===
slug: "code-review"                    # 全局唯一标识符，kebab-case
name: "代码审查专家"                     # 显示名称
version: "1.2.0"                       # 语义化版本号
description: |                         # 详细描述（Markdown）
  帮助 Agent 进行深度代码审查，关注安全漏洞、性能问题和代码风格。
short_description: "深度代码审查与优化建议"  # 摘要（≤100 字符）
category: "development"                # 领域分类
tags:                                  # 标签（可多选）
  - "ability"                          # 能力 / personality / knowledge / tool
icon: "search-code"                    # Lucide 图标名
author:
  type: "human"                        # human / agent
  name: "NoDeskAI"
  ref: ""                              # 作者主页或 Agent 实例 ID

# === 兼容性 ===
compatibility:
  - product: "openclaw"                # 产品标识（初期支持）
    min_version: "0.5.0"               # 最低版本
  - product: "nanobot"                 # 初期支持
    min_version: "0.1.0"
  # - product: "deskclaw"             # 后续扩展
  #   min_version: "1.0.0"

# === 依赖 ===
dependencies:
  - slug: "analytical-thinking"
    version: ">=1.0.0"
    optional: false                    # false = 必须, true = 推荐
synergies:                             # 协同推荐（非强依赖）
  - "clean-code"
  - "test-driven-development"

# === 技能内容 ===
# 技能内容以独立文件存储在基因目录中（SKILL.md），不再嵌入 manifest。
# gene.yaml 中 skill.file 指向文件路径，skill.content 仅用于向后兼容。
skill:
  name: "code-review"                  # 技能名（用于文件/目录命名）
  always: false                        # true = 始终激活, false = 按需调用
  file: "SKILL.md"                     # 技能文件路径（推荐，存储在 Gitea 仓库中）
  content: |                           # 向后兼容：内联内容（新基因不建议使用）
    ---
    name: code-review
    description: 深度代码审查与优化建议
    metadata:
      openclaw:
        always: false
    ---
    
    你是一位资深代码审查专家。在审查代码时，你应该关注：
    
    ## 审查维度
    1. **安全性**：SQL 注入、XSS、敏感信息泄露
    2. **性能**：时间复杂度、内存泄漏、N+1 查询
    3. **可读性**：命名规范、函数粒度、注释质量
    4. **架构**：职责分离、依赖方向、接口设计
    
    ## 输出格式
    对每个发现的问题，按以下格式输出：
    - 严重程度：Critical / Major / Minor / Suggestion
    - 位置：文件名:行号
    - 问题描述
    - 修复建议（含代码示例）

# === 规则内容（可选，部分产品支持） ===
rules: []
#  - name: "code-review-style"
#    content: "审查时始终使用中文输出..."
#    applies_to: "**/*.{ts,py,go}"

# === 工程化配置（可选） ===
config:
  # 通用配置（所有产品共享）
  common: {}

  # 产品专属配置
  openclaw:
    openclaw_config:                   # 合并到 openclaw.json
      tools:
        timeout: 30000
    tool_allow:                        # 追加到 tools.allow
      - "file_read"
      - "file_write"

  nanobot:
    capabilities: []                   # nanobot 能力注册

  # deskclaw:                          # 后续扩展
  #   cursor_rules: []                 # 额外的 .cursor/rules 内容

# === MCP 工具（可选） ===
mcp_servers: []
#  - name: "github-mcp"
#    transport: "stdio"
#    command: "npx"
#    args: ["-y", "@modelcontextprotocol/server-github"]
#    env:
#      GITHUB_PERSONAL_ACCESS_TOKEN: "${GITHUB_TOKEN}"

# === 学习策略 ===
learning:
  force_deep_learn: false              # true = 强制深度学习，不允许直接安装
  objectives:                          # 学习目标（提供给 Learning Engine）
    - "理解代码审查的四个核心维度"
    - "掌握安全漏洞的常见模式"
    - "形成结构化的审查输出格式"
  scenarios:                           # 练习场景
    - title: "审查一个 FastAPI 路由"
      context: "包含 SQL 注入风险的用户输入处理"
      expected_focus: "security"
```

### 2.2 基因目录结构

每个基因以目录形式存储，发布时整个目录上传到 Registry（存入 Gitea），安装时以 tarball 下载：

```
<gene-slug>/
├── gene.yaml        # 基因元数据（必须）
├── SKILL.md         # 技能内容（推荐）
├── scripts/         # 脚本文件（可选）
│   └── setup.sh
├── rules/           # 规则文件（可选）
│   └── naming.mdc
├── templates/       # 模板文件（可选）
│   └── prompt.md
└── assets/          # 静态资源（可选）
    └── diagram.png
```

**文件存储与版本管理**：

- 每个基因对应 Gitea 上一个 Git 仓库（`genes/<slug>`）
- 每次发布创建 git tag（`v1.0.0`），对应一个不可变版本
- commit SHA 记录在 DB 的 `gene_versions.commit_sha` 中
- 安装时通过 `GET /genes/:slug/archive?version=x.y.z` 下载 tarball
- DB 仅存索引元数据，文件内容全部由 Gitea 管理

### 2.3 字段说明

#### 必填字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `slug` | string | 全局唯一标识，`[a-z0-9-]`，3-64 字符 |
| `name` | string | 显示名称，≤128 字符 |
| `version` | string | 语义化版本号（SemVer），如 `1.2.0` |
| `description` | string | 详细描述，Markdown 格式 |
| `short_description` | string | 摘要，≤256 字符 |
| `category` | string | 领域分类（见 2.3） |
| `tags` | string[] | 标签数组（见 2.3） |
| `skill` | object | 技能内容定义 |
| `skill.name` | string | 技能名，用于文件命名 |
| `skill.content` | string | 技能的完整文本内容 |
| `compatibility` | object[] | 兼容产品列表 |

#### 可选字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `icon` | string | Lucide 图标名 |
| `author` | object | 作者信息 |
| `dependencies` | object[] | 基因依赖 |
| `synergies` | string[] | 协同推荐 |
| `rules` | object[] | 规则定义（DeskClaw 等产品使用） |
| `config` | object | 工程化配置（按产品分区） |
| `mcp_servers` | object[] | MCP Server 配置 |
| `learning` | object | 学习策略 |

### 2.3 枚举值

**category（领域分类）**：

| 值 | 含义 |
|------|------|
| `development` | 开发 |
| `data` | 数据 |
| `operations` | 运维 |
| `network` | 网络 |
| `creative` | 创意 |
| `communication` | 沟通 |
| `security` | 安全 |
| `efficiency` | 效率 |

**tags（标签类型）**：

| 值 | 含义 | SKILL.md 特征 |
|------|------|-------------|
| `ability` | 能力——做什么 | `always: false` |
| `personality` | 性格——怎么做 | `always: true` |
| `knowledge` | 知识——领域背景 | `always: true` |
| `tool` | 工具——接入外部 | `always: false` + mcp_servers |

### 2.4 与 NoDeskClaw manifest 的映射

| GeneHub Manifest | NoDeskClaw manifest |
|------------------|-------------------|
| `skill.name` | `manifest.skill.slug` |
| `skill.content` | `manifest.skill.content` |
| `config.openclaw.openclaw_config` | `manifest.openclaw_config` |
| `config.openclaw.tool_allow` | `manifest.tool_allow` |
| `mcp_servers` | `manifest.mcp_servers` |
| `learning` | `manifest.learning` |

NoDeskClaw 的 `gene_service.py` 可以零成本适配：只需在 `install_gene` 时从 GeneHub Manifest 提取 NoDeskClaw 格式的 manifest。

---

## 三、安装协议

### 3.1 安装流程

```
Client (CLI / SDK / NoDeskClaw)        GeneHub Registry         Agent Host
     │                                      │                      │
     │  1. GET /genes/:slug/manifest        │                      │
     │ ─────────────────────────────────────►│                      │
     │ ◄───── Gene Manifest ────────────────│                      │
     │                                      │                      │
     │  2. POST /resolve                    │                      │
     │ ─────────────────────────────────────►│                      │
     │ ◄───── 安装计划（含依赖） ────────────│                      │
     │                                      │                      │
     │  3. 检测目标产品                       │                      │
     │  ────── 自动识别 ──────               │                      │
     │                                      │                      │
     │  4. 调用 Adapter.install(manifest)   │                      │
     │ ──────────────────────────────────────────────────────────►│
     │                                      │                      │
     │  5. Adapter 执行产品专属安装逻辑       │                      │
     │     ├── OpenClaw: 写 SKILL.md +      │                      │
     │     │   合并 openclaw.json            │                      │
     │     ├── nanobot: 配置注入（待定）     │                      │
     │     └── Generic: 输出 gene.yaml      │                      │
     │                                      │                      │
     │  6. POST /genes/:slug/installed      │                      │
     │ ─────────────────────────────────────►│ (上报安装统计)        │
     │                                      │                      │
```

### 3.2 Adapter 接口

所有产品适配器必须实现以下接口：

```typescript
interface GeneAdapter {
  /** 产品标识 */
  readonly product: string;

  /** 检测当前环境是否为该产品 */
  detect(): Promise<boolean>;

  /** 安装基因到 Agent Host */
  install(manifest: GeneManifest, options?: InstallOptions): Promise<InstallResult>;

  /** 卸载基因 */
  uninstall(slug: string, options?: UninstallOptions): Promise<UninstallResult>;

  /** 列出已安装的基因 */
  list(): Promise<InstalledGene[]>;

  /** 检查基因是否已安装 */
  isInstalled(slug: string): Promise<boolean>;

  /** 获取已安装基因的版本 */
  getInstalledVersion(slug: string): Promise<string | null>;

  /** 触发 bot 处理学习任务（可选，各平台 CLI 实现） */
  triggerLearning?(prompt: string): Promise<void>;
}

interface InstallOptions {
  /** 安装目标路径（可选，适配器有默认值） */
  targetPath?: string;
  /** 是否强制覆盖已安装版本 */
  force?: boolean;
  /** 是否跳过依赖安装 */
  skipDependencies?: boolean;
}

interface InstallResult {
  success: boolean;
  slug: string;
  version: string;
  /** 安装的文件列表 */
  files: string[];
  /** 是否需要重启 Agent Host */
  needsRestart: boolean;
  /** 安装的依赖列表 */
  dependencies: string[];
}

interface InstalledGene {
  slug: string;
  version: string;
  installedAt: string;
  files: string[];
}
```

### 3.3 OpenClaw Adapter 实现

OpenClaw Adapter 负责将 Gene Manifest 转化为 OpenClaw 能理解的格式：

```
Gene Manifest
     │
     ▼
┌─────────────────────────────────────────┐
│ OpenClaw Adapter                         │
│                                         │
│  1. 写入 SKILL.md                        │
│     路径: /root/.openclaw/skills/        │
│           {skill.name}/SKILL.md         │
│     内容: skill.content                  │
│     自动补全 YAML front matter           │
│                                         │
│  2. 合并 openclaw.json                   │
│     config.openclaw.openclaw_config     │
│     → 浅合并到 openclaw.json            │
│                                         │
│  3. 追加 tools.allow                     │
│     config.openclaw.tool_allow          │
│     → 去重追加到 tools.allow 数组        │
│                                         │
│  4. 注入 MCP Servers                     │
│     mcp_servers                          │
│     → 写入 openclaw.json 的 mcpServers  │
│                                         │
│  5. 确保 skill 发现配置                   │
│     skills.load.extraDirs 包含           │
│     /root/.openclaw/skills              │
│                                         │
│  6. 标记需要重启                          │
│     needsRestart = true                  │
└─────────────────────────────────────────┘
```

### 3.4 DeskClaw Adapter 实现（后续扩展，预留设计）

```
Gene Manifest
     │
     ▼
┌─────────────────────────────────────────┐
│ DeskClaw Adapter                         │
│                                         │
│  1. 写入 SKILL.md                        │
│     路径: .cursor/skills/                │
│           {skill.name}/SKILL.md         │
│     或:   skills/{skill.name}/SKILL.md  │
│                                         │
│  2. 写入 Rules（如果有）                  │
│     路径: .cursor/rules/                 │
│           {rule.name}.mdc               │
│                                         │
│  3. 应用 DeskClaw 专属配置               │
│     config.deskclaw → 项目配置           │
│                                         │
│  4. 无需重启                             │
│     needsRestart = false                 │
│     （Cursor 自动检测文件变化）            │
└─────────────────────────────────────────┘
```

---

## 四、学习协议

学习协议定义了 Agent 深度内化基因的标准流程。这是一个可选的高级能力——最简实现可以只做 `install`（文件写入），跳过学习过程。

### 4.1 学习能力等级

| 等级 | 名称 | 能力 | 实现要求 |
|------|------|------|---------|
| L0 | 直接安装 | 文件写入，无学习过程 | 实现 Adapter.install |
| L1 | 浅层学习 | Agent 阅读技能描述并确认理解 | L0 + 学习回调 |
| L2 | 深度学习 | Agent 个性化改写技能，生成专属版本 | L1 + Learning Engine |
| L3 | 自主进化 | Agent 主动发现、学习、创造、遗忘基因 | L2 + meta-learning 基因 |

NoDeskClaw 当前实现了 L0-L3 全部等级。新接入的产品可以从 L0 开始，逐步升级。

### 4.2 学习任务协议

当 Agent Host 具备学习能力（L1+）时，安装流程扩展为：

```
Client                    Agent Host                Learning Engine
  │                           │                          │
  │  install(manifest)        │                          │
  │ ─────────────────────────►│                          │
  │                           │                          │
  │                           │  发送学习任务              │
  │                           │ ────────────────────────►│
  │                           │                          │
  │                           │  Agent 评估并执行学习      │
  │                           │                          │
  │                           │  学习结果回调              │
  │                           │ ◄────────────────────────│
  │                           │                          │
  │  InstallResult            │                          │
  │ ◄─────────────────────────│                          │
  │                           │                          │
```

#### 学习任务请求（Agent Host → Learning Engine）

```typescript
interface LearningTask {
  mode: "learn" | "create" | "forget";
  task_id: string;

  // learn 模式
  gene_slug?: string;
  gene_content?: string;
  gene_meta?: {
    name: string;
    description: string;
    category: string;
  };
  learning?: {
    objectives?: string[];
    scenarios?: LearningScenario[];
    force_deep_learn?: boolean;
  };

  // create 模式
  creation_prompt?: string;

  // forget 模式
  learning_output?: string;
  usage_count?: number;

  // 通用
  callback_url: string;
}

interface LearningScenario {
  title: string;
  context: string;
  expected_focus: string;
}
```

#### 学习结果回调（Learning Engine → Agent Host）

```typescript
interface LearningResult {
  task_id: string;
  instance_id: string;
  mode: "learn" | "create" | "forget";

  decision:
    // learn 模式
    | "direct_install"    // Agent 决定直接安装，无需个性化
    | "learned"           // Agent 完成深度学习，输出个性化版本
    | "failed"            // 学习失败
    // create 模式
    | "created"           // Agent 创造了新基因
    // forget 模式
    | "forgotten"         // 完全遗忘
    | "simplified"        // 简化保留
    | "forget_failed";    // 遗忘失败

  content?: string;       // SKILL.md 内容（learned / simplified / created）
  self_eval?: number;     // Agent 自评分 0.0-1.0
  reason?: string;        // 失败原因 / 决策理由

  // create 模式专属
  meta?: {
    gene_name: string;
    gene_slug: string;
    gene_description: string;
    suggested_tags: string[];
    suggested_category: string;
    icon?: string;
  };
}
```

### 4.3 遗忘协议

基因遗忘是学习的逆过程。分为两种模式：

#### 直接卸载（L0）

```
1. 删除技能文件（SKILL.md）
2. 清除配置（openclaw.json / nanobot config 等）
3. 重启 Agent Host（如需要）
```

#### 深度遗忘（L2+）

```
1. 发送遗忘任务到 Learning Engine
2. Agent 回顾该基因的使用经验
3. Agent 决策：
   ├── forgotten: 完全遗忘，删除所有相关文件
   ├── simplified: 保留简化版，降级为精简技能描述
   └── forget_failed: 遗忘失败，回滚到原状态
4. 执行清理
5. 重启 Agent Host（如需要）
```

### 4.4 创造协议

Agent 可以基于工作经验创造新基因，并通过 GeneHub 发布到生态：

```
Agent Host              GeneHub Registry          审核者
    │                        │                      │
    │  Agent 提炼经验         │                      │
    │  生成 Gene Manifest    │                      │
    │                        │                      │
    │  POST /genes           │                      │
    │ ──────────────────────►│                      │
    │                        │                      │
    │                        │  review_status=       │
    │                        │  pending              │
    │                        │                      │
    │                        │  通知审核              │
    │                        │ ────────────────────►│
    │                        │                      │
    │                        │  审核通过/拒绝         │
    │                        │ ◄────────────────────│
    │                        │                      │
    │  Webhook: 审核结果      │                      │
    │ ◄──────────────────────│                      │
    │                        │                      │
```

Agent 创造的基因需要两步审核：
1. 实例所有者审核（`pending_owner`）
2. 管理员审核（`pending_admin`）

### 4.5 对话触发学习

学习通道利用各 bot 平台自有的 CLI 非交互对话能力，让 bot 基于 `genehub-learner` 技能自主完成学习。

**流程**：

```
genehub install <gene> --learn
  |-- 1. 安装基因文件
  |-- 2. 创建学习任务文件 learning-tasks/{slug}.md
  |-- 3. 调用 adapter.triggerLearning() 触发 bot 对话
         |-- bot 发现 learning-tasks/ 中的任务
         |-- 自主学习并写入 learning-results/
```

Adapter 的 `triggerLearning` 方法是可选的。各平台实现：

| 平台 | CLI 命令 | 说明 |
|------|---------|------|
| OpenClaw | `openclaw agent --message "检查 learning-tasks/ 并处理学习任务"` | 非交互对话 |
| nanobot | `nanobot run --prompt "..."` | 试验性，待确认 |
| DeskClaw | 待定 | 后续扩展 |

触发后不阻塞等待结果，学习在后台异步进行。

### 4.6 串行学习

多个基因同时安装时，学习任务按序串行执行：

- 任务文件通过 front matter 的 `order` 字段标识执行顺序
- `genehub-learner` SKILL.md 指引 Agent 按 order 排序逐个处理
- 完成一个任务后再开始下一个，避免认知过载

---

## 五、效能数据协议

GeneHub 收集各产品的基因使用效能数据，用于排行和推荐。

### 5.1 效能信号

| 信号类型 | 来源 | 权重 |
|---------|------|------|
| `user_positive` | 用户点赞/好评 | 25% |
| `user_negative` | 用户点踩/差评 | 25% |
| `agent_self_eval` | Agent 自评分 | 25% |
| `task_success` | 使用该基因完成任务的成功率 | 50% |

### 5.2 效能上报接口

```typescript
interface EffectivenessReport {
  gene_slug: string;
  gene_version: string;
  product: string;                 // 上报产品
  instance_id: string;             // Agent 实例标识
  metric_type: "user_positive" | "user_negative" | "agent_self_eval" | "task_success";
  value: number;                   // 0.0 - 1.0
  context?: string;                // 上下文说明
  timestamp: string;               // ISO 8601
}
```

上报方式：
- 实时：`POST /api/v1/genes/:slug/effectiveness`
- 批量：`POST /api/v1/effectiveness/batch`

---

## 六、版本管理

### 6.1 版本号规范

遵循语义化版本（SemVer）：`MAJOR.MINOR.PATCH`

| 版本变更 | 含义 |
|---------|------|
| MAJOR | 不兼容的 skill 内容变更（如删除关键能力） |
| MINOR | 新增能力或改进，向后兼容 |
| PATCH | 修复错误、优化描述 |

### 6.2 版本解析规则

依赖声明支持 SemVer 范围：

| 声明 | 含义 |
|------|------|
| `"1.2.0"` | 精确版本 |
| `">=1.0.0"` | 大于等于 |
| `"^1.2.0"` | 兼容版本（≥1.2.0, <2.0.0） |
| `"~1.2.0"` | 近似版本（≥1.2.0, <1.3.0） |
| `"*"` | 任意版本 |

### 6.3 变体（Variant）

Agent 深度学习产生的个性化版本作为原始基因的变体：

```
code-review@1.0.0 (原始)
  ├── code-review@1.0.0-variant.agent-alice (Agent Alice 的变体)
  └── code-review@1.0.0-variant.agent-bob   (Agent Bob 的变体)
```

变体保留 `parent_gene_id` 指向原始基因，版本号使用 prerelease 后缀标识。

---

## 七、基因文件格式

### 7.1 目录结构

发布到 GeneHub 的基因包结构：

```
<gene-slug>/
├── gene.yaml          # Gene Manifest（必须）
├── SKILL.md           # 技能内容（可选，也可内联在 gene.yaml 的 skill.content 中）
├── README.md          # 说明文档（可选）
├── rules/             # 规则文件（可选）
│   └── *.mdc
└── examples/          # 使用示例（可选）
    └── *.md
```

### 7.2 SKILL.md 格式

SKILL.md 是 OpenClaw 生态的标准技能描述文件，GeneHub 将其作为基因内容的主要载体：

```markdown
---
name: code-review
description: 深度代码审查与优化建议
metadata:
  openclaw:
    always: false
---

你是一位资深代码审查专家...

## 审查维度

1. 安全性
2. 性能
...
```

#### Front Matter 字段

| 字段 | 必填 | 说明 |
|------|------|------|
| `name` | 是 | 技能名，与 gene.yaml 的 `skill.name` 一致 |
| `description` | 是 | 一行描述 |
| `metadata.openclaw.always` | 否 | 是否始终激活（默认 false） |

### 7.3 gene.yaml vs 内联

基因内容可以选择两种方式之一：

**方式 A：外部文件引用**

```yaml
# gene.yaml
skill:
  name: "code-review"
  file: "SKILL.md"          # 引用外部文件
```

**方式 B：内联内容**

```yaml
# gene.yaml
skill:
  name: "code-review"
  content: |                 # 直接内联
    ---
    name: code-review
    ...
```

Registry 存储时统一展开为内联格式。

---

## 八、认证与安全

### 8.1 API 认证

| 操作 | 认证要求 |
|------|---------|
| 搜索、查看基因 | 无需认证（公开读） |
| 安装基因（下载 manifest） | 无需认证 |
| 发布基因 | API Token 认证 |
| 上报效能数据 | API Token 认证 |
| 管理操作（审核、删除） | API Token + Admin 角色 |

### 8.2 API Token

```
Authorization: Bearer ghb_xxxxxxxxxxxxxxxxxxxxx
```

Token 通过 `genehub auth login` 或 GeneHub Web UI 生成。

### 8.3 基因内容安全

| 检查项 | 说明 |
|--------|------|
| Manifest Schema 校验 | 发布时校验 gene.yaml 结构完整性 |
| MCP Server 白名单 | mcp_servers 中的 command 需在允许列表内 |
| 配置注入审查 | openclaw_config / tool_allow 变更需审核 |
| 内容扫描 | 检测恶意指令注入（prompt injection 防护） |

---

## 九、错误码

| 范围 | 模块 | 示例 |
|------|------|------|
| 1xxxx | 认证 | 10001 Token 无效 |
| 2xxxx | 基因 | 20001 基因不存在, 20002 版本冲突 |
| 3xxxx | 基因组 | 30001 基因组不存在 |
| 4xxxx | 安装 | 40001 依赖解析失败, 40002 兼容性不匹配 |
| 5xxxx | 学习 | 50001 学习任务超时, 50002 回调失败 |
| 9xxxx | 系统 | 90001 内部错误 |

---

## 十、实现参考

### 10.1 NoDeskClaw 现有实现对照

| GLP 概念 | NoDeskClaw 对应实现 |
|----------|-------------------|
| Gene Manifest | `Gene.manifest` JSON 字段 |
| Adapter.install | `gene_service._direct_install()` |
| Adapter.uninstall | `gene_service.uninstall_gene()` |
| Learning Task | `gene_service._send_learning_task()` |
| Learning Result | `gene_service.handle_learning_callback()` |
| Learning Engine | `openclaw-channel-learning` Plugin |
| 效能上报 | `gene_service.log_effectiveness()` |
| 创造协议 | `gene_service.trigger_gene_creation()` + `handle_creation_callback()` |
| 遗忘协议 | `gene_service._send_forgetting_task()` + `handle_forgetting_callback()` |

### 10.2 最小实现清单

一个新产品接入 GeneHub 的最低要求：

| 步骤 | 工作量 | 说明 |
|------|--------|------|
| 1. 实现 GeneAdapter 接口 | 1-2 天 | install / uninstall / list |
| 2. 实现 detect() | 0.5 天 | 自动检测当前环境 |
| 3. 映射 Manifest → 产品格式 | 1-2 天 | skill.content → 产品原生技能文件 |
| 4. 测试 CLI 安装 | 0.5 天 | `genehub install xxx` 验证 |

总计约 **3-5 天**即可完成一个产品的基础接入。

---

## 十一、基因组与模板的目录结构

基因组和 AI 员工模板与基因一样通过 Git 仓库管理。它们本质是**引用清单（composition manifest）**，Git 仓库中存放 manifest 文件和可选文档，不含基因实际文件。

### 11.1 Gitea 组织结构

| Gitea Org | 存储内容 | 示例仓库 |
|-----------|---------|---------|
| `genes` | 基因文件（gene.yaml + SKILL.md + 额外文件） | `genes/clean-code` |
| `genomes` | 基因组 manifest（genome.yaml + README.md） | `genomes/fullstack-dev` |
| `templates` | 模板 manifest（template.yaml + README.md） | `templates/senior-backend` |

### 11.2 genome.yaml 结构

```yaml
name: "全栈开发基因组"
slug: "fullstack-dev"
version: "1.0.0"
description: "全栈开发必备基因组合"
short_description: "全栈开发基因组合"
category: "development"
tags: ["fullstack", "development"]
genes:
  - slug: "code-review"
    version: "1.0.0"
  - slug: "clean-code"
    version: "1.0.0"
  - slug: "debugging"
    version: "1.0.0"
compatibility: ["openclaw", "nanobot"]
author:
  type: "human"
  name: "GeneHub Team"
```

### 11.3 template.yaml 结构

```yaml
name: "高级后端工程师"
slug: "senior-backend"
version: "1.0.0"
description: "适合后端开发的 AI 员工模板"
short_description: "后端工程师模板"
role: "后端工程师"
category: "engineering"
tags: ["backend", "engineering"]
genomes:
  - slug: "fullstack-dev"
    version: "1.0.0"
genes:
  - slug: "data-analysis"
    version: "1.0.0"
compatibility: ["openclaw", "nanobot"]
author:
  type: "human"
  name: "GeneHub Team"
```

### 11.4 CLI 命令

```bash
genehub genome publish <dir>     # 发布基因组（扫描 genome.yaml + 目录文件）
genehub genome install <slug>    # 安装基因组：解析基因列表 -> 逐个安装所有基因
genehub genome list              # 搜索基因组
genehub genome info <slug>       # 查看基因组详情 + 引用的基因列表

genehub template publish <dir>   # 发布 AI 员工模板
genehub template install <slug>  # 递归安装：先安装基因组 -> 再安装额外基因
genehub template list            # 搜索模板
genehub template info <slug>     # 查看模板详情
```

---

*协议持续演进中，欢迎各产品团队反馈。*
