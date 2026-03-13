# NoDeskClaw LLM Proxy

独立的 LLM 请求代理服务，负责 Working Plan 模式下的 API 请求转发、鉴权和用量记录。

## 功能

- 通过 `proxy_token` 鉴权，解析组织/个人 Key
- 支持 OpenAI、Anthropic、Gemini、OpenRouter、MiniMax 等 Provider
- Working Plan 额度检查
- 流式/非流式请求转发
- Token 用量自动记录

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
    config.py             # 配置（DATABASE_URL, HTTPS_PROXY）
    database.py           # 数据库连接
    models.py             # 精简 DB models（只含 proxy 所需列）
    proxy.py              # 代理核心逻辑
```

## 本地开发

```bash
# 安装依赖
uv sync

# 复制并编辑环境变量
cp .env.example .env

# 启动服务
uv run uvicorn app.main:app --port 8080 --reload
```

## 构建部署

### 使用 deploy.sh（推荐）

```bash
# 构建 + 推送 + 部署
./nodeskclaw-llm-proxy/deploy.sh --context <CTX>

# 部署到指定 namespace
./nodeskclaw-llm-proxy/deploy.sh --context <CTX> --namespace nodeskclaw-staging

# 仅构建推送，不更新 K8s
./nodeskclaw-llm-proxy/deploy.sh --context <CTX> --build-only

# 使用指定 tag 更新 K8s（不重新构建）
./nodeskclaw-llm-proxy/deploy.sh --context <CTX> --deploy-only --tag v0.1.0-beta.1
```

`deploy.sh` 从 `deploy/.env.local` 读取 REGISTRY 配置。

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

## 依赖关系

- 与 `nodeskclaw-backend` 共用同一个 RDS PostgreSQL 数据库
- models.py 是后端模型的精简子集，只声明 proxy 需要读写的列
- 数据库 schema 由 `nodeskclaw-backend` 管理，本服务不执行迁移
