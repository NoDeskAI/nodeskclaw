# AGENTS.md - NoDeskClaw 开发指南

## 项目概述

NoDeskClaw 是 DeskClaw 实例可视化管理系统，通过 Web 界面管理 K8s 集群上的 DeskClaw 实例。

| 组件 | 技术 | 可用版本 |
|------|------|---------|
| 后端 | Python 3.12 + FastAPI + SQLAlchemy + PostgreSQL | CE + EE |
| 管理前端 | Vue 3 + Vite + TypeScript + Tailwind CSS + shadcn-vue | EE-only |
| 用户门户 | Vue 3 + Vite + TypeScript + Tailwind CSS + Three.js | CE + EE |

## 构建/测试命令

### 后端（nodeskclaw-backend）

```bash
cd nodeskclaw-backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
uv run pytest                              # 运行全部测试
uv run pytest tests/test_xxx.py            # 运行指定文件
uv run pytest tests/test_xxx.py::test_func # 运行指定函数
uv run ruff check .                        # Lint 检查
uv run ruff check --fix .                  # 自动修复
```

### 前端（ee/nodeskclaw-frontend / nodeskclaw-portal）

```bash
cd ee/nodeskclaw-frontend  # 管理后台（EE-only）
npm install
npm run dev
npm run build
vue-tsc -b                                # 类型检查
```

## 代码风格

### 命名约定

| 类型 | 规则 |
|------|------|
| 组件文件 | PascalCase（如 `UserProfile.vue`） |
| 工具函数 | camelCase（如 `useAuth.ts`） |
| 类型/接口 | PascalCase（如 `UserInfo`） |
| 常量 | UPPER_SNAKE_CASE |
| Python 模块/函数 | snake_case |
| Python 类 | PascalCase |
| 布尔变量 | `is_`、`has_`、`can_` 前缀 |
| 通用 | 禁止中文命名、禁用缩写（API/URL/ID/DB 除外） |

### Emoji 禁止

禁止使用 emoji，使用 `lucide-vue-next` 图标库。

```vue
<!-- 禁止 -->
<span>🔍 搜索</span>
<!-- 正确 -->
<Search class="w-4 h-4" />
```

### 语言表达

所有专业术语、变量名、配置项后面必须跟中文说明。

- `IMAGE_REGISTRY`（镜像仓库地址）
- SSE（服务端推送）、KubeConfig（集群连接凭证）

### 软删除规则

所有数据删除必须使用逻辑删除，严禁物理删除。

- 删除操作设置 `deleted_at = func.now()`
- 所有查询过滤：`Model.deleted_at.is_(None)`
- 禁止 `db.delete()` 和原生 `DELETE FROM`
- 唯一约束使用 Partial Unique Index：`Index(..., unique=True, postgresql_where=text("deleted_at IS NULL"))`

### Docker 镜像架构

所有 Docker 操作必须显式指定 `linux/amd64` 平台。

```bash
docker build --platform linux/amd64 -t my-image:latest .
```

### 导入完整性

在函数/代码块内使用模型或工具类时，必须确保该作用域内有对应的 import。不要假设外层已导入。

### i18n 规则

新增或修改用户可见文案时，必须同步接入 i18n 词条，不允许新增硬编码中文 UI 文案。

- 统一使用小写点分级：`errors.auth.token_invalid`
- 一律使用命名参数：`t('errors.instance.not_found', { name })`
- 错误响应必须包含 `error_code` + `message_key` + `message`

## 错误处理原则

### 必须遵循

- **先查证再开口**：不确定的事情先查证，查不到就说查不到
- **明确依据来源**：回答时说明依据（哪个文件、哪行代码）
- **不知道就是不知道**：列出做了哪些尝试，最终为什么仍不确定
- **出错就认**：说错了直接承认

### 严禁

- 禁止猜测性断言（"应该是这样"）
- 禁止想当然（"一般项目都这样"）
- 禁止半吊子回答（查一半就急着回答）
- 禁止信息编造

## K8s/DeskClaw 排查

**必须先通过 kubectl 实际查看集群状态，再作判断。**

排查流程：
1. `kubectl get pods -n <namespace>` — Pod 状态
2. `kubectl describe pod <pod> -n <namespace>` — 详情和 Events
3. `kubectl logs <pod> -n <namespace>` — 日志

### 多集群上下文选择

执行 kubectl 前必须确认目标集群：
- 先 `kubectl config get-contexts` 确认上下文
- 每条命令显式指定 `--context <name>`
- 禁止盲用 current-context

## 问题处理流程

发现问题后不要立即动手修，先报告给用户，等用户确认方案后再改。

流程：
1. 明确描述问题、影响范围、根因分析
2. 提出建议修复方案（可多个），说明优缺点
3. 等待用户确认
4. 确认后执行修复

例外（可直接修）：明显拼写错误、导入缺失、lint 错误、用户明确说"直接修"。

## Git 规范

### 分支命名

格式：`<type>/<kebab-case-description>`

- 前缀：`feat`、`fix`、`refactor`、`chore`、`docs`、`perf`、`test`、`build`
- description 使用 kebab-case，2-5 个词，描述分支做什么
- 特殊分支：`main`、`release-<version>`

```
feat/operation-audit
fix/deploy-env-serialize
refactor/ce-ee-split
chore/upgrade-fastapi
```

禁止无意义名称（`cccc`、`temp`）、纯日期名称（`chore/openclaw-2026.3.8`）、`feature/` 全称、中文/大写/下划线。

### PR 标题

格式与 commit message 一致：`<type>(<scope>): <中文描述>`，概括整个 PR 的变更目标。

```
feat(backend): CE 操作审计系统 — Hook 埋点 + 持久化 + AuthActor 识别
fix(portal): 修复实例列表分页后状态丢失问题
```

### 自动提交

- 每完成一个单元性改动后，必须立即提交 commit，不要攒多个独立改动一起提交
- 单元性改动指：一个可独立描述、可独立验证、可独立回滚的最小完整改动（如一个 bug 修复、一次样式微调、一次规则更新）
- 只有多个修改明确属于同一个改动单元时，才允许合并为一个 commit

### Commit Message 格式

```
<type>(<scope>): <subject>
```

- type：feat、fix、docs、style、refactor、perf、test、chore
- subject：**必须使用中文**，祈使语态，50字符内

### 示例

```
feat(instance): 实例列表新增搜索和过滤功能
fix(deploy): 修复 env_vars 存数据库未序列化的问题
```

### 禁止

- 禁止 `Co-authored-by` 署名
- 禁止提交 `.env`、`.venv/`、`node_modules/`

## 用户偏好

- 使用中文交流
- 代码不加注释（除非特别要求）
- 回答风格：简洁直接

## 破坏性操作确认

以下操作执行前必须逐项列出并获得用户明确确认：
- K8s 资源删除/替换
- 数据库操作（DROP/DELETE/TRUNCATE）
- DNS/域名变更
- Docker 镜像删除
- `git push --force`、`git reset --hard`

## 同源逻辑同步

修改一处逻辑后，必须搜索项目中是否存在相同或相似的逻辑副本，全部同步修改。

| 逻辑类型 | 可能位置 |
|---------|----------|
| slug 生成、表单校验 | `ee/nodeskclaw-frontend` 和 `nodeskclaw-portal` 的对应页面 |
| API 调用封装 | 两个前端的 `api.ts` |
| K8s 资源构建逻辑 | `resource_builder.py`、`deploy_service.py` |

## CE/EE 架构

### 目录结构

- `features.yaml` — EE 功能清单定义
- `ee/` — EE 私有仓库（`.gitignore` 排除，开发者通过 `scripts/setup-ee.sh` 拉取）
  - `ee/backend/` — EE 后端（路由、Service、Model、Hook）
  - `ee/nodeskclaw-frontend/` — Admin 管理后台前端（EE-only，完整 Vue 项目）
  - `ee/frontend/portal/` — Portal 前端 EE 页面和路由

### FeatureGate

`app/core/feature_gate.py` — 检测 `ee/` 目录是否存在决定 edition，控制功能开关。

### 后端抽象层

4 个 Factory 模式抽象层，CE/EE 各自实现：

| 抽象层 | CE 实现 | EE 实现（ee/backend/） |
|--------|---------|----------------------|
| DeploymentAdapter | BasicK8sAdapter | FullK8sAdapter |
| EmailTransport | GlobalSmtpTransport | OrgSmtpTransport |
| OrgProvider | SingleOrgProvider | MultiOrgProvider |
| QuotaChecker | NoopQuotaChecker | PlanBasedQuotaChecker |

### EE Model 注册

EE Model 使用 CE 的 `Base`，在 `main.py` lifespan 中 `create_all` 前条件导入 `ee.backend.models`。

### 前端架构

- **Admin**（`ee/nodeskclaw-frontend/`）：完整独立的 Vue 项目，EE-only，CE 版不包含此目录。EE 路由直接定义在 `src/router/index.ts` 中。
- **Portal**（`nodeskclaw-portal/`）：CE + EE 共用。CE 前端定义 `src/router/ee-stub.ts`（空数组），Vite 在检测到 `ee/` 时通过 alias 替换为 `ee/frontend/portal/routes.ts` 提供的 EE 路由。

### 开发指南

- 新增 EE 功能：在 `ee/` 中添加，CE 通过 Factory/Hook/Stub 扩展点接入
- 新增 CE 功能：直接在主仓库中开发
- EE Model 必须 import CE 的 `Base`/`BaseModel`
