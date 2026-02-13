# claw-buddy-artifacts

ClawBuddy 部署到 K8s 的制品仓库 -- 存放需要构建成 Docker 镜像并在集群中运行的文件。

## 目录结构

```
claw-buddy-artifacts/
└── openclaw-image/              # OpenClaw 定制镜像
    ├── Dockerfile               # 基于 node:24-bookworm-slim，npm 全局安装 openclaw
    ├── docker-entrypoint.sh     # 容器启动脚本（配置生成 + 凭证注入 + 前台启动）
    ├── init-container.sh        # Init Container 脚本（PVC 数据初始化 + 版本升级）
    └── openclaw.json.template   # 配置模板，启动时 envsubst 替换占位符
```

## OpenClaw 镜像

### 这是什么

ClawBuddy 管理的 OpenClaw 实例运行的 Docker 镜像。不从源码构建，而是通过 `npm install -g openclaw` 安装发布版本。

### 构建

```bash
cd claw-buddy-artifacts/openclaw-image

docker build \
  --build-arg NODE_VERSION=24 \
  --build-arg OPENCLAW_VERSION=1.0.0 \
  --build-arg IMAGE_VERSION=v1.0.0 \
  -t cr-cn-beijing.volces.com/clawbuddy/openclaw:v1.0.0 \
  .
```

| 构建参数 | 说明 | 默认值 |
|----------|------|--------|
| `NODE_VERSION` | Node.js 大版本 | `24` |
| `OPENCLAW_VERSION` | openclaw npm 包版本 | `1.0.0` |
| `IMAGE_VERSION` | 镜像 Tag 版本标记 | `v1.0.0` |

### 推送到火山云 CR

```bash
docker login cr-cn-beijing.volces.com -u <access_key>
docker push cr-cn-beijing.volces.com/clawbuddy/openclaw:v1.0.0
```

### 镜像内文件说明

| 文件 | 作用 |
|------|------|
| `docker-entrypoint.sh` | 容器启动入口。检查 `OPENCLAW_FORCE_RECONFIG` 决定是否从模板重建配置，注入凭证，然后 `exec openclaw gateway` 前台运行 |
| `init-container.sh` | K8s Init Container 执行。首次部署时将 `/root/.openclaw` 模板拷贝到 PVC；版本升级时合并内置插件、更新版本标记 |
| `openclaw.json.template` | 配置模板，包含 `${OPENCLAW_GATEWAY_PORT}` 等占位符，由 entrypoint 用 `envsubst` 替换生成 `openclaw.json` |

### 关键环境变量

| 环境变量 | 说明 | 默认值 |
|----------|------|--------|
| `OPENCLAW_GATEWAY_PORT` | 监听端口 | `18789` |
| `OPENCLAW_GATEWAY_BIND` | 绑定策略（lan = 0.0.0.0） | `lan` |
| `OPENCLAW_GATEWAY_TOKEN` | Gateway 认证 Token | 必填 |
| `OPENCLAW_LOG_LEVEL` | 日志级别 | `info` |
| `OPENCLAW_FORCE_RECONFIG` | 设为 `true` 时强制从模板重建配置 | `false` |
| `OPENCLAW_CREDENTIALS_JSON` | JSON 格式凭证，写入 credentials/default.json | 可选 |
| `OPENAI_API_KEY` | OpenAI 模型 Key，OpenClaw 原生读取 | 可选 |
| `ANTHROPIC_API_KEY` | Anthropic 模型 Key | 可选 |

### 构建产物检查清单

构建完成后验证：

```bash
docker run --rm <image> node --version          # 输出 Node.js 版本
docker run --rm <image> openclaw --version       # 输出 OpenClaw 版本
docker run --rm <image> which openclaw           # /usr/local/bin/openclaw
docker run --rm <image> ls /root/.openclaw/      # 目录结构完整
docker run --rm <image> cat /root/.openclaw-version  # 版本标记正确
```

## 与其他项目的关系

- **claw-buddy-backend** -- ClawBuddy 管理平台后端，有自己的 Dockerfile
- **claw-buddy-frontend** -- ClawBuddy 管理平台前端，开发阶段无需独立镜像
- **本目录** -- 被 ClawBuddy 部署到 K8s 的 OpenClaw 实例镜像

详细的镜像设计文档见 `docs/OpenClaw镜像构建规范.md`。
