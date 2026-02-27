# AGENTS.md - NoDeskClaw 开发指南

## 项目概述

NoDeskClaw 是 OpenClaw 实例可视化管理系统，通过 Web 界面管理 K8s 集群上的 OpenClaw 实例，支持一键部署、实时日志、集群健康巡检、飞书 SSO 登录。

## 技术栈

| 组件 | 技术 |
|------|------|
| 后端 | Python 3.12 + FastAPI + SQLAlchemy + PostgreSQL |
| 管理前端 | Vue 3 + Vite + TypeScript + Tailwind CSS + shadcn-vue |
| 用户门户 | Vue 3 + Vite + TypeScript + Tailwind CSS + Three.js |
| LLM Proxy | Go |
| 部署 | K8s + Docker（目标架构 linux/amd64） |

## 目录结构

```
NoDeskClaw/
├── nodeskclaw-backend/           # 后端 API 服务（Python 3.12 + FastAPI）
├── nodeskclaw-frontend/          # 管理后台前端（Vue 3）
├── nodeskclaw-portal/            # 用户门户前端（Vue 3 + Three.js）
├── nodeskclaw-llm-proxy/         # LLM 代理服务（Go）
├── nodeskclaw-artifacts/         # 镜像构建 & 部署制品
├── openclaw/                     # OpenClaw 源码副本
├── openclaw-channel-nodeskclaw/   # Channel 插件
├── deploy/                       # K8s 部署配置
└── docs/                         # 设计文档
```

## 构建/测试命令

### 后端（nodeskclaw-backend）

```bash
cd nodeskclaw-backend
uv sync
uv run uvicorn app.main:app --reload --port 8000
uv run pytest
uv run pytest tests/test_xxx.py
uv run pytest tests/test_xxx.py::test_function_name
uv run ruff check .
uv run ruff check --fix .
```

### 前端（nodeskclaw-frontend / nodeskclaw-portal）

```bash
cd nodeskclaw-frontend
npm install
npm run dev
npm run build
vue-tsc -b
```

## 代码风格指南

### Emoji 禁止规则

**禁止在任何地方使用 emoji。** 包括 Vue 模板、提示文字、Toast 消息。使用 `lucide-vue-next` 图标库。

```vue
<!-- 禁止 -->
<span>🔍 搜索</span>

<!-- 正确 -->
<Search class="w-4 h-4" />
```

### 语言表达规范

**所有专业术语、变量名、配置项后面必须跟中文说明。**

- 配置项：`IMAGE_REGISTRY`（镜像仓库地址）
- 技术概念：SSE（服务端推送）、KubeConfig（集群连接凭证）
- 禁止堆砌纯英文术语来"装专业"

### 软删除规则

**所有数据删除必须使用逻辑删除，严禁物理删除。**

- 删除操作统一设置 `deleted_at = func.now()`
- 所有查询必须过滤：`Model.deleted_at.is_(None)`
- 禁止 `db.delete()` 和原生 `DELETE FROM`

### Docker 镜像架构规则

**所有 Docker 操作必须显式指定 `linux/amd64` 平台。**

```bash
# 正确
docker build --platform linux/amd64 -t my-image:latest .

# 错误 - Mac 默认 arm64，K8s 节点拉不了
docker build -t my-image:latest .
```

### 导入完整性规则

在函数/代码块内使用模型或工具类时，必须确保该作用域内有对应的 import。不要假设外层已经导入。

### 同源逻辑同步修改规则

修改一处逻辑后，必须搜索项目中是否存在相同或相似的逻辑副本，全部同步修改。

| 逻辑类型 | 可能位置 |
|---------|----------|
| slug 生成、表单校验 | frontend 和 portal 的对应页面 |
| API 调用封装 | 两个前端的 `api.ts` |
| K8s 资源构建逻辑 | 后端 `resource_builder.py`、`deploy_service.py` |

## 命名约定和类型规范

### TypeScript/Vue

- 组件文件：`PascalCase`（如 `UserProfile.vue`）
- 工具函数/组合式函数：`camelCase`（如 `useAuth.ts`）
- 类型/接口：`PascalCase`（如 `UserInfo`）
- 常量：`UPPER_SNAKE_CASE`

### Python

- 模块/函数：`snake_case`
- 类：`PascalCase`
- 常量：`UPPER_SNAKE_CASE`
- 类型注解：必须使用（Python 3.12+）

### 通用规则

- 禁止中文命名
- 禁用缩写（除非业界标准：API、URL、ID、DB）
- 布尔变量用 `is_`、`has_`、`can_` 前缀

## 错误处理原则

### 必须遵循

- **先查证再开口**：不确定的事情先查证，查不到就说查不到，绝不编造
- **明确依据来源**：回答问题时说明依据（哪个文件、哪行代码、哪个命令）
- **不知道就是不知道**：列出做了哪些尝试，最终为什么仍不确定
- **出错就认**：说错了直接承认，不要找借口圆

### 严禁

- 禁止猜测性断言（"应该是这样"）
- 禁止想当然（"一般项目都这样"）
- 禁止半吊子回答（查一半就急着回答）
- 禁止信息编造（没验证过的内容当作事实陈述）

### K8s/OpenClaw 排查规则

用户提到的任何 OpenClaw 或 K8s 相关问题，**必须先通过 kubectl 实际查看集群状态**，再作判断。

排查流程：
1. `kubectl get pods -n <namespace>` — Pod 状态
2. `kubectl describe pod <pod> -n <namespace>` — 详情和 Events
3. `kubectl logs <pod> -n <namespace>` — 日志

## 问题处理流程

**发现问题后不要立即动手修，先报告给用户，等用户确认方案后再改。**

流程：
1. 明确描述问题、影响范围、根因分析
2. 提出建议修复方案（可多个），说明优缺点
3. 等待用户确认
4. 确认后执行修复

例外（可直接修）：明显拼写错误、导入缺失、lint 错误、用户明确说"直接修"。

## Git 提交规范

### Commit Message 格式

```
<type>(<scope>): <subject>
```

- type：feat、fix、docs、style、refactor、perf、test、chore、revert、build
- scope：选填（frontend、backend、deploy、cluster、instance 等）
- subject：**必须使用中文**，祈使语态，50字符内

### 示例

```
feat(instance): 实例列表新增搜索和过滤功能
fix(deploy): 修复 env_vars 存数据库未序列化的问题
refactor(frontend): SSE 流 baseURL 统一走配置常量
```

### 禁止

- 禁止 `Co-authored-by` 署名
- 禁止提交 `.env`、`.venv/`、`node_modules/`

## 用户偏好

- 使用中文交流
- 代码不加注释（除非特别要求）
- 回答风格：简洁直接
- 涉及多步骤任务时，一个一个来

## 文档规范

### 文档驱动开发

任何功能实现之前，必须先更新对应的设计文档。不允许跳过文档直接写代码。

### README 规则

新建目录/项目/模块，必须包含 README，至少包含：用途、目录结构、使用方法。

### 文档同步

代码和文档必须在同一次操作中同步完成。

## 工具脚本

### Git 统计脚本（scripts/git_stats/）

生成 Git 仓库的 commit 数量和代码行数折线图。

#### 安装

```bash
cd scripts/git_stats
pip install -r requirements.txt
```

#### 使用

```bash
# 基本用法
python git_stats.py --author "your.email@example.com" --granularity daily

# 参数说明
--repo REPO         # 仓库路径，默认当前目录
--author AUTHOR     # 作者名称/邮箱
--since DATE        # 开始日期，默认自动（第一个 commit）
--until DATE        # 结束日期，默认自动（最后一个 commit）
--granularity       # 时间粒度：daily/weekly/monthly，默认 monthly
--output-dir DIR    # 输出目录
```

#### 输出图表

| 文件 | 说明 |
|------|------|
| commit_counts.png | Commit 数量折线图 |
| code_lines.png | 新增/删除代码行数折线图 |
| total_lines.png | 累计净代码量折线图 |
| code_breakdown.png | 目录占比饼图 |
