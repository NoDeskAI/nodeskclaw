# cccc 分支 PR 描述（合并时请复制到 GitHub PR 正文）

---

在 GitHub 创建 PR 时，将下方「PR 正文」整段复制到描述框。PR 合并后，正文中的 6 个 `Closes #N` 会使对应 Issue 自动关闭。

---

## PR 正文（复制以下内容）

### 概述

本 PR 包含 Web 端错误态与 emoji 替换、Python SDK 最小可用实现、Registry Context 类型修复等改动。

Closes #4
Closes #5
Closes #6
Closes #7
Closes #8
Closes #9

### 关联的 Issues（[GeneHub Issues](https://github.com/NoDeskAI/genehub/issues)，合并后将自动关闭）

| Issue | 标题 |
|-------|------|
| #9 | [sdk] Python SDK 初始化实现 |
| #8 | [web] 版本历史加载失败静默吞错 + 违规使用 emoji |
| #7 | [cli] 实现 genehub info 命令，查看单个基因详情 |
| #6 | [cli] search 命令未接入联邦搜索，无法搜到外部基因源 |
| #5 | [sdk] Nanobot Adapter 缺少测试覆盖，config.nanobot 配置注入未实现 |
| #4 | [registry] 删除基因/基因组/模板时 Gitea 仓库清理失败不抛错，导致数据不一致 |

### 主要变更

**Web（packages/web）**
- 列表/版本历史加载失败时展示错误提示；列表失败时重置 totalPages / federatedSources
- 详情页 slug 变化时清空 error 与数据，避免一直显示错误页
- 剩余 emoji 替换为 Lucide 图标（Home 分类、GenomeBrowse 空态、CategoryNav 等）

**Python SDK（packages/sdk/python）**
- 新增 GeneHubClient、GeneAdapter、GenericAdapter、LearningEngine（最小可用）
- 按 Copilot 评论修正：URL 编码、JSON 异常处理、GeneManifest 类型、safe_dump、时间戳、非 JSON 响应测试

**Registry（packages/registry）**
- 为 Hono Context 声明 AuthVariables 类型，消除 genes API 等处的 TypeScript 报错

**文档**
- architecture.md、README、AGENTS.md 等补充/更新 Python SDK 与目录结构
- docs/pr-registry-context-types.md、docs/pr-cccc-branch.md（本 PR 说明）

### Test plan

- `pnpm build`、`pnpm test` 全量通过
- Web：本地 `pnpm dev` 验证列表/详情错误态与分类图标
- Python SDK：`cd packages/sdk/python && uv run pytest tests/ -v`
- Registry：本地启动后调用需鉴权接口验证行为不变
