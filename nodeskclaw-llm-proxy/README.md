# DeskClaw LLM Proxy

DeskClaw LLM 代理 -- AI 经营伙伴的智力供给中枢。负责大语言模型 API 的请求转发、鉴权、额度检查和用量记录，确保每位 AI 经营者获得所需的推理能力。

## 功能

- 通过 `proxy_token` 鉴权，解析组织/个人 Key
- 支持 OpenAI、Anthropic、Gemini、OpenRouter、MiniMax 等 Provider
- 支持 `codex` Provider，通过服务端 Codex CLI 登录态执行模型请求
- Working Plan 额度检查（仅组织 Key）
- 流式/非流式请求转发
- 全量 Token 用量记录（组织 Key + 个人 Key），含 latency、status_code、request_path 等元数据
- Workspace 用量归因：按优先级 signed token → `X-NoDeskClaw-Session-Key: workspace:<id>` → 旧 runtime session header 兼容 → active_tracking（仅单办公室实例的兼容兜底）→ unattributed
- `stream_options` 按 provider 白名单自动注入（OpenAI/OpenRouter/MiniMax/Gemini）
- 可选请求体记录（`LLM_LOG_CONTENT` 环境变量控制，默认关闭）
- 响应元数据记录（去除 content 后的结构化 JSON，始终存储）

## 目录结构

```
nodeskclaw-llm-proxy/
  pyproject.toml          # Python 依赖
  Dockerfile              # 容器镜像
  build-and-push.sh       # 构建并推送镜像到容器镜像仓库
  .env.example            # 环境变量模板
  deploy/                 # K8s 部署清单
    deployment.yaml       # Deployment（LLM Proxy + Clash sidecar）
    service.yaml          # ClusterIP Service
    secret.yaml.example   # Secret 模板
    clash-config.yaml     # Clash 出站代理配置
  app/
    main.py               # FastAPI 入口
    config.py             # 配置（DATABASE_URL, HTTPS_PROXY, LLM_LOG_CONTENT, CODEX_*）
    database.py           # 数据库连接
    models.py             # 精简 DB models（只含 proxy 所需列）
    proxy.py              # 代理核心逻辑
```

## 本地开发

推荐使用项目根目录的 `./dev.sh`，它会自动启动 LLM Proxy（port 8080）、Backend、前端并覆盖 `LLM_PROXY_URL`。

手动启动：

```bash
# 安装依赖
uv sync

# 复制并编辑环境变量
cp .env.example .env

# 如果需要使用 codex Provider，先完成 Codex CLI 登录
codex login

# 启动服务
uv run uvicorn app.main:app --port 8080 --reload
```

默认情况下，`CODEX_BYPASS_APPROVALS_AND_SANDBOX=false`，不会绕过 Codex CLI 自带的审批和沙箱保护。如果你确实需要无审批执行，必须显式改为 `true`，并自行承担对应的执行风险。

**已知限制**：Codex CLI 的 stream 模式是"伪流式" — 请求会同步等待 CLI 执行完毕（最长 `CODEX_TIMEOUT_SECONDS`，默认 300 秒），然后一次性返回所有 SSE 事件。用户在 CLI 执行期间不会看到逐 token 的流式输出。

## 构建部署

### 使用发版/部署脚本（推荐）

```bash
# 构建 + 推送版本镜像
./deploy/release.sh create v0.1.0-beta.1

# 部署到生产
./deploy/deploy.sh deploy proxy --tag v0.1.0-beta.1 --prod --context <CTX>

# 如需独立验证环境，可显式初始化临时 staging 后部署
./deploy/deploy.sh deploy proxy --tag v0.1.0-beta.1 --staging --context <CTX>
```

脚本从 `deploy/.env.local` 读取 REGISTRY 和 KUBE_CONTEXT 配置，也可以用 `--context` 覆盖。

### 手动部署

```bash
# 1. 构建并推送镜像
./build-and-push.sh

# 2. 创建 K8s Secret（修改 secret.yaml.example 为实际值）
cp deploy/secret.yaml.example deploy/secret.yaml
kubectl --context <CTX> -n <NS> apply -f deploy/secret.yaml

# 3. 部署 Clash 配置 + Deployment + Service
kubectl --context <CTX> -n <NS> apply -f deploy/clash-config.yaml
kubectl --context <CTX> -n <NS> apply -f deploy/deployment.yaml
kubectl --context <CTX> -n <NS> apply -f deploy/service.yaml
```

K8s 清单不包含 `namespace` 字段，由 `kubectl -n <NS>` 在运行时指定。

如果要在 K8s 中启用 `codex` Provider，除了部署 `llm-proxy` 镜像外，还需要自行提供容器内可访问的 Codex CLI 登录态目录，并将其挂载到 `CODEX_HOME`。仓库默认 K8s 清单未内置这部分用户态凭据分发逻辑。

## 依赖关系

- 与 `nodeskclaw-backend` 共用同一个 RDS PostgreSQL 数据库
- models.py 是后端模型的精简子集，只声明 proxy 需要读写的列
- 数据库 schema 由 `nodeskclaw-backend` 管理，本服务不执行迁移
