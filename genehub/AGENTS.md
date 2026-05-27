# AGENTS.md - GeneHub 开发指南

## 项目概述

GeneHub 是 NoDeskClaw 生态的基因注册中心，为全体 AI 员工提供可复用、可组合、可演化的能力基因。包含三个核心模块：Registry（注册中心）、SDK（标准学习协议）、CLI（命令行工具）。

## 技术栈

| 组件 | 技术 |
|------|------|
| Registry API | TypeScript + Hono |
| 数据库 | PostgreSQL |
| CLI | TypeScript (tsx) |
| SDK (TypeScript) | TypeScript |
| SDK (Python) | Python 3.12+ |
| 包管理 | pnpm (monorepo) |
| 测试 | Vitest (TS) / pytest (Python) |
| Lint | Biome (TS) / Ruff (Python) |

## 目录结构

```
genehub/
├── docs/                         # 设计文档
│   ├── architecture.md           # 架构设计
│   └── gene-learning-protocol.md # 标准学习协议规范
├── packages/
│   ├── registry/                 # Gene Registry Service
│   ├── sdk/
│   │   ├── typescript/           # TypeScript SDK
│   │   └── python/               # Python SDK
│   └── cli/                      # 命令行工具
├── genes/                        # 官方基因库
├── adapters/                     # 安装方式兼容层
├── AGENTS.md                     # 开发指南（本文件）
├── README.md
├── LICENSE
├── CONTRIBUTING.md
└── package.json                  # monorepo 根配置
```

## 构建/测试命令

```bash
# 安装依赖（monorepo 全量）
pnpm install

# Registry
cd packages/registry
pnpm dev          # 开发模式
pnpm test         # 测试
pnpm build        # 构建

# CLI
cd packages/cli
pnpm dev
pnpm test

# TypeScript SDK
cd packages/sdk/typescript
pnpm test

# Python SDK
cd packages/sdk/python
uv sync
uv run pytest
uv run ruff check .

# 全量 lint
pnpm lint
```

## 版本号规则

**格式**：`yyyy-MM-dd[-tag]`

| 格式 | 用途 | 示例 |
|------|------|------|
| `yyyy-MM-dd` | 正式发布 | `2026-02-27` |
| `yyyy-MM-dd-alpha` | 内测版 | `2026-02-27-alpha` |
| `yyyy-MM-dd-beta` | 公测版 | `2026-02-27-beta` |
| `yyyy-MM-dd-rc.N` | 候选版 | `2026-02-27-rc.1` |
| `yyyy-MM-dd-hotfix.N` | 热修复 | `2026-02-27-hotfix.1` |

Git Tag 统一加 `v` 前缀：`v2026-02-27`。

同一天多次发布时，tag 递增区分：`v2026-02-27`、`v2026-02-27-hotfix.1`。

基因版本号（Gene Manifest 中的 `version`）使用 SemVer（`1.0.0`），与项目版本号独立。

## 代码风格

### 通用

- 使用中文交流，commit message 中文
- 禁止 emoji（代码、注释、文档均禁止）
- 布尔变量用 `is_`、`has_`、`can_` 前缀
- 禁止中文变量名
- 禁止无意义缩写（允许业界标准：API、URL、ID、DB、CLI）

### TypeScript

- 模块/函数：`camelCase`
- 类/接口/类型：`PascalCase`
- 常量：`UPPER_SNAKE_CASE`
- 文件名：`kebab-case.ts`
- 使用 `type` 优先于 `interface`（除非需要声明合并）
- 严格模式 `strict: true`

### Python

- 模块/函数：`snake_case`
- 类：`PascalCase`
- 常量：`UPPER_SNAKE_CASE`
- 类型注解：必须使用

## Git 提交规范

### Commit Message 格式

```
<type>(<scope>): <subject>
```

- type：`feat` / `fix` / `docs` / `style` / `refactor` / `perf` / `test` / `chore` / `revert` / `build`
- scope：选填（`registry` / `cli` / `sdk` / `protocol` / `genes` 等）
- subject：**中文**，祈使语态，50 字符内

### 示例

```
feat(registry): 基因搜索 API 支持标签过滤
fix(cli): 修复 install 命令依赖解析死循环
docs(protocol): 补充 nanobot Adapter 映射规则
chore: 升级 Hono 到 4.x
```

### 禁止

- 禁止 `Co-authored-by` 署名
- 禁止提交 `.env`、`node_modules/`、`__pycache__/`、`.venv/`

## 分支策略

| 分支 | 用途 | 保护 |
|------|------|------|
| `main` | 稳定发布分支 | 禁止直推，PR 合入 |
| `dev` | 开发主分支 | PR 合入 |
| `feat/<name>` | 功能分支 | 从 dev 拉出，合回 dev |
| `fix/<name>` | 修复分支 | 从 dev 拉出，合回 dev |
| `release/<version>` | 发布分支 | 从 dev 拉出，合回 main + dev |

## 文档规范

### 文档驱动开发

功能实现前，先更新对应设计文档。不允许跳过文档直接写代码。

### 新建目录/模块

必须包含 README，至少包含：用途、目录结构、使用方法。

### 文档同步

代码和文档必须在同一次操作中同步完成。

### 设计文档风格

重架构轻代码。代码块仅用于说明接口签名或数据结构，不写实现。

## 错误处理

- 先查证再开口，不确定的先查证
- 明确依据来源（哪个文件、哪行代码）
- 不知道就是不知道，不编造
- 出错就认，不找借口

## Issue / PR 规范

### Issue

- 标题简明，包含模块前缀：`[registry] 基因搜索不支持模糊匹配`
- 正文包含：背景、期望行为、实际行为、复现步骤
- 标签：`bug` / `feature` / `docs` / `question`

### Pull Request

- 标题格式同 commit：`feat(registry): 基因搜索 API 支持标签过滤`
- 正文包含：变更摘要、测试计划
- 关联 Issue：`Closes #123`
- 必须通过 CI（lint + test）才能合入
