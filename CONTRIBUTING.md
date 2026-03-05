# Contributing to NoDeskClaw

感谢你对 NoDeskClaw 的关注！以下是参与贡献的指南。

## 开发环境

### 前置条件

| 依赖 | 版本 |
|------|------|
| Python | >= 3.12 |
| [uv](https://docs.astral.sh/uv/) | 最新版 |
| Node.js | >= 18 |
| npm | 最新版 |
| PostgreSQL | 数据库 |

### 后端

```bash
cd nodeskclaw-backend
cp .env.example .env   # 填入实际配置
uv sync
uv run uvicorn app.main:app --reload --port 8000
```

### 前端（管理后台 / 用户门户）

```bash
cd nodeskclaw-frontend   # 或 nodeskclaw-portal
npm install
npm run dev
```

## 贡献流程

1. Fork 本仓库
2. 基于 `main` 创建功能分支：`git checkout -b feat/your-feature`
3. 编写代码并确保通过检查（见下方）
4. 提交 commit（格式见下方）
5. 推送分支并创建 Pull Request

## 代码检查

提交 PR 前请确保以下检查通过：

```bash
# 后端
cd nodeskclaw-backend
uv run ruff check .
uv run pytest

# 前端
cd nodeskclaw-frontend
npm run build
vue-tsc -b
```

## Commit Message 格式

```
<type>(<scope>): <中文描述>
```

- **type**: feat / fix / docs / style / refactor / perf / test / chore
- **scope**: 可选，如 frontend、backend、deploy、instance 等
- **描述**: 使用中文，50 字符内

示例：

```
feat(instance): 实例列表新增搜索功能
fix(deploy): 修复部署超时未清理资源的问题
docs: 更新后端架构设计文档
```

## 代码规范

- 禁止在 UI 中使用 emoji，统一使用 `lucide-vue-next` 图标组件
- Python 使用类型注解（Python 3.12+）
- 数据删除使用软删除（`deleted_at` 字段），禁止物理删除
- Docker 镜像构建必须指定 `--platform linux/amd64`

完整规范参见 [AGENTS.md](AGENTS.md)。

## CE/EE 边界

NoDeskClaw 采用 CE（Community Edition）/ EE（Enterprise Edition）双版本架构：

- **本仓库是 CE（社区版）**，以 Apache 2.0 协议开源
- **EE 代码位于私有的 `ee/` 目录**，已通过 `.gitignore` 排除，不在本仓库中
- 贡献者只需关注 CE 部分的代码

### 哪些属于 EE

EE 功能定义在 `features.yaml` 中，包括但不限于：多组织管理、套餐计费、组织级 SMTP 配置、拓扑审计日志等。

### 开发注意事项

- CE 代码不应直接 `import` `ee/` 下的模块
- 需要 CE/EE 行为差异的功能，通过抽象层 + Factory 模式实现（详见 AGENTS.md 中的 CE/EE 架构章节）
- 新增功能如果只属于 EE，请在 Issue 中说明

## Issue 规范

- Bug 报告请使用 [Bug Report 模板](.github/ISSUE_TEMPLATE/bug_report.md)
- 功能建议请使用 [Feature Request 模板](.github/ISSUE_TEMPLATE/feature_request.md)
- 描述尽量详细，附上复现步骤、截图、日志等

## License

贡献的代码将以 [Apache License 2.0](LICENSE) 发布。
