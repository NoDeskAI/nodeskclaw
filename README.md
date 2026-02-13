# ClawBuddy

OpenClaw 实例可视化管理平台 -- One-click deploy, full control.

通过 Web 界面管理 K8s 集群上的 OpenClaw 实例，支持一键部署、实时日志、集群健康巡检、飞书 SSO 登录。

## 项目结构

```
ClawBuddy/
├── claw-buddy-frontend/      # 前端（Vue 3 + shadcn-vue + Tailwind CSS）
├── claw-buddy-backend/       # 后端（Python 3.12 + FastAPI）
├── claw-buddy-artifacts/     # 镜像构建 & 部署制品
├── openclaw/                 # OpenClaw 源码（独立仓库，不纳入 Git）
└── vibecraft/                # VibeCraft 源码（独立仓库，不纳入 Git）
```

## 本地启动

### 前置条件

| 依赖 | 说明 |
|------|------|
| Python >= 3.12 | 后端运行环境 |
| [uv](https://docs.astral.sh/uv/) | Python 包管理 |
| Node.js >= 18 | 前端运行环境 |
| npm / pnpm | 前端包管理 |
| 火山云 RDS PostgreSQL | 数据库，需提前创建好库 |
| 飞书开放平台应用 | SSO 登录，需要 App ID / App Secret |

### 1. 配置后端环境变量

```bash
cd claw-buddy-backend
cp .env.example .env
```

编辑 `.env`，填入实际值（必填项见下表）：

| 变量 | 说明 |
|------|------|
| `DATABASE_URL` | `postgresql+asyncpg://user:pass@host:5432/dbname` |
| `JWT_SECRET` | JWT 签名密钥，生产环境务必替换 |
| `ENCRYPTION_KEY` | KubeConfig AES 加密密钥（32 字节 base64） |
| `FEISHU_APP_ID` | 飞书应用 App ID |
| `FEISHU_APP_SECRET` | 飞书应用 App Secret |
| `FEISHU_REDIRECT_URI` | 飞书 OAuth 回调地址，本地开发填 `http://localhost:5173/api/v1/auth/feishu/callback` |

### 2. 启动后端

```bash
cd claw-buddy-backend
uv sync                    # 安装依赖（首次）
uv run uvicorn app.main:app --reload --port 8000
```

后端启动后：
- API 地址: `http://localhost:8000`
- Swagger 文档: `http://localhost:8000/docs`
- 首次启动自动建表，无需手动迁移

### 3. 启动前端

```bash
cd claw-buddy-frontend
npm install                # 安装依赖（首次）
npm run dev
```

前端启动后：
- 访问地址: `http://localhost:5173`
- `/api` 和 `/stream` 请求自动代理到后端 `http://localhost:8000`

### 4. 访问

浏览器打开 `http://localhost:5173`，通过飞书账号登录即可。

> 飞书开放平台的重定向 URL 需配置为 `http://localhost:5173/api/v1/auth/feishu/callback`

## 各子项目文档

- [后端 README](claw-buddy-backend/README.md) -- API 概览、目录结构、环境变量详解
- [制品 README](claw-buddy-artifacts/README.md) -- OpenClaw 镜像构建、Dockerfile 说明
