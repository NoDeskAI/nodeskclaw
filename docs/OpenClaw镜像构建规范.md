# OpenClaw 镜像构建规范

> 定义 OpenClaw 容器镜像的构建标准、版本管理策略和配置注入机制。

---

## 一、镜像仓库

| 项目 | 值 |
|------|-----|
| 仓库 | 火山云容器镜像服务 (CR) |
| 地址 | `cr-{region}.volces.com/{namespace}/openclaw` |
| 示例 | `cr-cn-beijing.volces.com/nodeskclaw/openclaw:v1.0.0` |
| 访问 | VKE 集群内走内网拉取，免公网带宽 |

---

## 二、版本管理策略

### 2.1 Tag 规范

镜像 Tag 与 OpenClaw npm 版本一一对应，格式为 `v{YYYY.M.DD}`：

| Tag 格式 | 说明 | 示例 |
|----------|------|------|
| `v{YYYY.M.DD}` | 正式版本（生产用），与 npm 版本对应 | `v2026.2.26` |
| `latest` | 最新构建版本（仅开发环境用） | — |

**生产环境必须用明确版本号**，禁止用 `latest`。

### 2.2 版本过滤策略

OpenClaw npm 同一天可能发多个版本（如 `2026.2.22-1`、`2026.2.23-beta.1`）。

**过滤规则**：只采纳"干净"的正式版本（匹配 `^\d{4}\.\d{1,2}\.\d{1,2}$`），排除所有带 `-` 后缀的版本（`-beta`、`-rc`、`-1`、`-2` 等）。

### 2.3 版本更新流程

通过 GitHub Actions 自动化检测和构建（详见第七节），也支持本地脚本手动操作：

```
GitHub Actions 定时检测 npm 新版本
  │
  ├─ 发现新版本 → 自动创建 PR（更新 Dockerfile 版本号）
  ├─ 人工审核 PR → 确认 Release Notes 无风险后合并
  ├─ 手动触发构建工作流 → 构建 + 推送镜像到火山云 CR
  └─ 管理员在前端选择新 tag → 部署到具体实例
```

### 2.4 构建参数

| 构建参数 | 说明 | 示例 |
|----------|------|------|
| `NODE_VERSION` | Node.js 大版本（用于选基础镜像） | `22` |
| `OPENCLAW_VERSION` | OpenClaw npm 包版本 | `2026.2.26` |
| `IMAGE_VERSION` | 镜像版本标记（自动为 `v` + `OPENCLAW_VERSION`） | `v2026.2.26` |

### 2.5 稳定性保障

| 环节 | 机制 |
|------|------|
| 版本过滤 | 只采纳正式版，排除 beta/rc/patch 后缀 |
| PR 审核 | 自动检测但不自动合并，人工确认后才构建 |
| 构建隔离 | 手动触发构建，合并 PR 不会自动推送镜像 |
| 实例级锁定 | 每个实例独立绑定 `image_version`，新镜像推送不影响现有实例 |
| 滚动升级 | 管理员在前端选择新 tag 后才更新具体实例，可逐个升级 |
| 回滚能力 | 旧 tag 始终保留在 CR 中，随时可回退 |

---

## 三、Dockerfile 规范

### 3.1 设计原则

1. **程序和数据分离** — Node.js + OpenClaw 在系统目录（镜像层），用户数据在 `/root`（PVC 层）
2. **不用 nvm** — 容器内只需一个 Node.js 版本，直接用官方 `node:{version}` 基础镜像
3. **镜像更新 = 程序更新** — 程序文件不在 PVC 里，换镜像就是升级，Init Container 不需要覆盖程序

### 3.2 目录结构约定

```
系统目录（镜像层，不在 PVC 中）
├── /usr/local/bin/node                  ← Node.js（来自基础镜像）
├── /usr/local/bin/openclaw              ← CLI 入口（npm -g 安装）
├── /usr/local/lib/node_modules/openclaw/ ← OpenClaw 核心代码
└── /docker-entrypoint.sh               ← 启动脚本

/root/（PVC 层，持久化用户数据）
├── .openclaw/                           ← 用户数据
│   ├── openclaw.json                    ← 主配置（由模板生成）
│   ├── openclaw.json.template           ← 配置模板（镜像预置）
│   ├── agents/main/sessions/            ← 会话历史
│   ├── config/                          ← 插件配置
│   ├── credentials/                     ← 凭证（API Key 等）
│   ├── extensions/                      ← 插件代码
│   ├── workspace/                       ← 工作区（SKILL、项目文件）
│   ├── memory/                          ← 长期记忆
│   ├── data/                            ← 持久化数据
│   ├── temp/                            ← 临时文件
│   ├── canvas/                          ← Web 控制台前端
│   ├── devices/                         ← 设备连接状态
│   ├── identity/                        ← bot 身份配置
│   └── cron/                            ← 定时任务配置
│
├── .openclaw-version                    ← 镜像版本标记（Init Container 用）
├── .bashrc                              ← Shell 配置
└── .profile
```

> 关键变化：Node.js 和 OpenClaw 程序在 `/usr/local/`（镜像层），升级时自动跟随镜像版本，无需 Init Container 处理。

### 3.3 Dockerfile 结构

基础镜像直接用 `node:{version}-bookworm-slim`，自带 Node.js，无需 nvm。

**Stage 1: build** — 安装 OpenClaw + 预置用户数据目录

| 步骤 | 说明 |
|------|------|
| 基础镜像 | `node:${NODE_VERSION}-bookworm-slim` |
| 系统依赖 | `curl`, `git`, `ca-certificates`, `jq`, `procps`, `gettext-base`（envsubst） |
| 全局安装 | `npm install -g openclaw@${OPENCLAW_VERSION}` |
| 预置目录 | 在 `/root/.openclaw/` 下创建完整子目录结构 |
| 配置模板 | 拷入 `openclaw.json.template` 到 `/root/.openclaw/` |
| 默认插件 | 如有内置插件，拷入 `extensions/` |
| 版本标记 | 写入 `/root/.openclaw-version`（内容: `IMAGE_VERSION`） |
| 启动脚本 | 拷入 `/docker-entrypoint.sh` + `chmod +x` |
| Init 脚本 | 拷入 `/init-container.sh` + `chmod +x` |

**最终配置**

| 项目 | 值 |
|------|-----|
| `WORKDIR` | `/root` |
| `EXPOSE` | `18789` |
| `ENTRYPOINT` | `["/docker-entrypoint.sh"]` |

> 单阶段就够了（基础镜像即运行镜像）。如果后续镜像太大，可以拆成多阶段构建。

### 3.4 启动脚本 docker-entrypoint.sh

```
docker-entrypoint.sh
  │
  ├─ 1. 配置初始化
  │   ├─ 检查环境变量 OPENCLAW_FORCE_RECONFIG
  │   │   ├─ = "true" → 强制从模板重新生成 openclaw.json（用于配置更新场景）
  │   │   └─ 其他 → 仅在文件不存在时生成（首次部署）
  │   └─ envsubst 从模板生成，用环境变量替换占位符
  │
  ├─ 2. 凭证注入
  │   ├─ 环境变量 OPENCLAW_CREDENTIALS_JSON 有值
  │   └─ → 写入 /root/.openclaw/credentials/default.json
  │
  ├─ 3. 清理编译缓存
  │   └─ rm -rf /tmp/jiti/*
  │
  └─ 4. 前台启动
      └─ exec openclaw gateway --allow-unconfigured --bind lan
         ← exec 让进程成为 PID 1，接收 K8s SIGTERM 优雅关闭
         ← --allow-unconfigured: 允许无 openclaw.json 时启动
         ← --bind lan: 绑定到 0.0.0.0（容器内必须，否则外部无法访问）
```

### 3.5 前台启动命令设计

OpenClaw 的进程名是 `openclaw-gateway`，在宿主机上通过 systemd 管理。容器里不用 systemd，直接前台运行：

**启动命令：`exec openclaw gateway --allow-unconfigured --bind lan`**

| 参数 | 说明 |
|------|------|
| `--allow-unconfigured` | 允许在没有 openclaw.json 时启动（首次部署 entrypoint 还没生成配置时需要） |
| `--bind lan` | 绑定到 `0.0.0.0`，容器内必须设置，否则默认 loopback 外部无法访问 |

> 官方 Dockerfile CMD: `["node", "openclaw.mjs", "gateway", "--allow-unconfigured"]`，bind 默认 loopback，通过 `OPENCLAW_GATEWAY_BIND=lan` 环境变量或 `--bind lan` 参数覆盖。

前台运行的关键点：
- **必须用 `exec`**：替换 shell 进程，让 Node.js 成为 PID 1，K8s 发 SIGTERM 时进程能正确接收并优雅关闭
- **不能用 `&` 后台运行**：否则 shell 退出容器就死了
- **不能用 systemd/supervisor**：容器里多余，增加复杂度

K8s 相关配置：

| 配置 | 值 | 说明 |
|------|-----|------|
| `terminationGracePeriodSeconds` | `30` | 发 SIGTERM 后等 30 秒，超时 SIGKILL |
| `livenessProbe` | `exec: ["openclaw", "health"]` | 进程存活检测（通过 WebSocket RPC） |
| `readinessProbe` | `exec: ["openclaw", "health"]` | 就绪检测（同上） |

---

## 四、配置注入机制

### 4.1 三层配置体系

```
优先级 (高 → 低)
  │
  ├─ 1. 环境变量 (ConfigMap/Secret)   ← NoDeskClaw 部署时注入
  ├─ 2. 配置文件 (entrypoint 生成)     ← 模板 + 环境变量替换
  └─ 3. 镜像内默认值 (模板默认值)       ← Dockerfile 构建时写入
```

### 4.2 openclaw.json 模板

镜像内预置模板 `/root/.openclaw/openclaw.json.template`，entrypoint 启动时用 `envsubst` 替换占位符。

> openclaw.json 采用 JSON5 格式，完整 schema 定义在源码 `src/config/zod-schema.ts`（`OpenClawSchema`），类型在 `src/config/types.openclaw.ts`（`OpenClawConfig`）。

**模板 envsubst 占位符**（NoDeskClaw 部署时注入的核心字段）：

| 模板占位符 | 环境变量 | 映射到 openclaw.json | 默认值 |
|-----------|----------|---------------------|--------|
| `${OPENCLAW_GATEWAY_PORT}` | `OPENCLAW_GATEWAY_PORT` | `gateway.port` | `18789` |
| `${OPENCLAW_GATEWAY_BIND}` | `OPENCLAW_GATEWAY_BIND` | `gateway.bind` | `lan`（容器内必须 lan） |
| `${OPENCLAW_GATEWAY_TOKEN}` | `OPENCLAW_GATEWAY_TOKEN` | `gateway.auth.token` | （必填） |
| `${OPENCLAW_LOG_LEVEL}` | `OPENCLAW_LOG_LEVEL` | `logging.level` | `info` |

**模型配置通过环境变量直接注入**（OpenClaw 原生支持，不需要写入 openclaw.json）：

| 环境变量 | 说明 |
|----------|------|
| `OPENAI_API_KEY` | OpenAI API Key |
| `ANTHROPIC_API_KEY` | Anthropic API Key |
| `GEMINI_API_KEY` | Google Gemini API Key |
| 其他 `*_API_KEY` | 各 provider 的 Key，见 `.env.example` |

> OpenClaw 的模型配置在 `models.providers` 字段，支持 provider/baseUrl/apiKey/models 等。但 API Key 通常直接通过环境变量注入（如 `OPENAI_API_KEY`），不需要写入配置文件。

**openclaw.json 核心字段概览**（完整字段 30+，这里列 NoDeskClaw 关心的）：

| 字段路径 | 类型 | 说明 |
|----------|------|------|
| `gateway.port` | number | 监听端口，默认 18789 |
| `gateway.bind` | string | 绑定策略：auto/lan/loopback/custom |
| `gateway.auth.mode` | string | token / password |
| `gateway.auth.token` | string | 认证 token |
| `gateway.controlUi.enabled` | boolean | 是否启用 Web UI |
| `models.providers` | object | 按 provider 的模型配置 |
| `logging.level` | string | silent/fatal/error/warn/info/debug/trace |
| `channels` | object | Telegram/Discord/Slack 等渠道配置 |
| `plugins` | object | 插件加载配置 |
| `agents` | object | Agent 列表与默认值 |

**不需要外部数据库** — OpenClaw 仅用本地 SQLite（`node:sqlite` + `sqlite-vec`），数据存在 `~/.openclaw/memory/` 下。

### 4.3 配置更新机制

用户通过 NoDeskClaw 修改实例配置后，需要让新配置生效：

```
NoDeskClaw 用户修改配置
  │
  ├─ 1. 后端更新 ConfigMap/Secret（新的环境变量值）
  │
  ├─ 2. 后端在 ConfigMap 中设置 OPENCLAW_FORCE_RECONFIG=true
  │
  ├─ 3. 触发 Pod 重启（patch annotation）
  │
  ├─ 4. Pod 启动 → entrypoint 检测到 FORCE_RECONFIG=true
  │   └─ 从模板重新生成 openclaw.json（覆盖旧文件）
  │
  └─ 5. 后端将 OPENCLAW_FORCE_RECONFIG 改回 false
      └─ 下次正常重启不会意外覆盖用户手动修改的配置
```

这样既解决了"配置更新不生效"的问题，又不会在普通重启时意外覆盖用户自定义配置。

### 4.4 敏感数据注入

通过 K8s **Secret**（非 ConfigMap）注入，API Key 直接用环境变量，OpenClaw 原生读取：

| 环境变量 | 注入方式 | 说明 |
|----------|----------|------|
| `OPENAI_API_KEY` | 环境变量（Secret） | OpenAI 模型 Key，OpenClaw 自动读取 |
| `ANTHROPIC_API_KEY` | 环境变量（Secret） | Anthropic 模型 Key |
| 其他 `*_API_KEY` | 环境变量（Secret） | 各 provider 的 Key |
| `OPENCLAW_GATEWAY_TOKEN` | 环境变量（Secret） | Gateway 认证 token |
| `OPENCLAW_CREDENTIALS_JSON` | entrypoint 写入 `/root/.openclaw/credentials/oauth.json` | OAuth 凭证（如需要） |

> **credentials/ 目录说明**：OpenClaw 的 credentials 目录包含 `oauth.json`（OAuth 凭据）、`<channel>-pairing.json`（渠道配对）、`<channel>-allowFrom.json`（白名单）等 JSON 文件。对于 NoDeskClaw 管理的实例，大部分配置通过环境变量注入即可，credentials 文件按需处理。

### 4.5 部署时注入流程

```
NoDeskClaw 部署表单
  │
  ├─ 用户填写配置（模型、插件、凭证等）
  ├─ 后端存入 DB（敏感字段加密）
  │
  ├─ 部署时生成 K8s 资源：
  │   ├─ ConfigMap ← 非敏感配置（MODEL_PROVIDER、LOG_LEVEL 等）
  │   ├─ Secret   ← 敏感配置（API_KEY、CREDENTIALS_JSON 等）
  │   └─ Deployment ← envFrom: ConfigMap + Secret
  │
  └─ Pod 启动 → entrypoint.sh → 环境变量 → 配置文件
```

---

## 五、Init Container 与 PVC 初始化

### 5.1 职责

去掉 nvm 后，程序文件在镜像层，Init Container 只需要处理 **PVC 中的用户数据初始化**：

| 场景 | 行为 |
|------|------|
| 首次部署（PVC 为空） | 拷贝 `/root/.openclaw/` 模板目录 + `.openclaw-version` 到 PVC |
| 版本相同 | 跳过 |
| 版本不同（镜像升级） | 只更新 `.openclaw-version` + 合并内置插件，保留所有用户数据 |

### 5.2 升级策略

镜像升级时，PVC 中哪些动、哪些不动：

| PVC 中的内容 | 升级行为 | 原因 |
|-------------|---------|------|
| `.openclaw-version` | **覆盖** | 版本标记 |
| `.openclaw/extensions/` 内置插件 | **合并** | 更新内置插件，保留用户自定义插件 |
| `.openclaw/openclaw.json` | **保留** | 用户自定义配置 |
| `.openclaw/agents/` | **保留** | 会话历史 |
| `.openclaw/credentials/` | **保留** | 用户凭证 |
| `.openclaw/workspace/` | **保留** | 用户工作区 |
| `.openclaw/memory/` | **保留** | 长期记忆 |
| `.openclaw/data/` | **保留** | 持久化数据 |
| `.openclaw/config/` | **保留** | 插件配置 |
| `.bashrc`, `.profile` | **覆盖** | Shell 配置跟随镜像 |

> **程序文件（Node.js + OpenClaw）在镜像层**，换镜像就是升级，Init Container 完全不用管。

### 5.3 Init Container 逻辑

```
/init-container.sh
  │
  ├─ PVC 挂载到 /init-data
  │
  ├─ Case 1: /init-data/.openclaw-version 不存在 → 首次部署
  │   ├─ cp -a /root/.openclaw /init-data/.openclaw
  │   ├─ cp /root/.openclaw-version /init-data/.openclaw-version
  │   └─ cp /root/.bashrc /root/.profile /init-data/
  │
  ├─ Case 2: 版本相同 → 跳过
  │
  └─ Case 3: 版本不同 → 轻量升级
      ├─ 更新版本标记
      ├─ 合并内置插件到 extensions/
      └─ 更新 .bashrc / .profile
```

---

## 六、构建命令

### 6.1 一键构建推送（推荐）

```bash
cd nodeskclaw-artifacts/openclaw-image

# 使用 Dockerfile 中的默认版本
./build-and-push.sh

# 指定版本
./build-and-push.sh --version 2026.2.26

# 仅构建不推送
./build-and-push.sh --build-only
```

脚本自动完成：npm 版本校验 → `docker build --platform linux/amd64` → 打 `v{version}` + `latest` tag → 推送 → 验证。

### 6.2 版本检查

```bash
cd nodeskclaw-artifacts/openclaw-image

# 检查是否有新版本
./check-update.sh

# 检查并自动更新 Dockerfile
./check-update.sh --update
```

### 6.3 手动构建（不使用脚本）

```bash
cd nodeskclaw-artifacts/openclaw-image

docker build --platform linux/amd64 \
  --build-arg OPENCLAW_VERSION=2026.2.26 \
  --build-arg IMAGE_VERSION=v2026.2.26 \
  -t nodesk-center-cn-beijing.cr.volces.com/base-image/nodeskclaw-openclaw-base:v2026.2.26 \
  .

docker login nodesk-center-cn-beijing.cr.volces.com -u {access_key}
docker push nodesk-center-cn-beijing.cr.volces.com/base-image/nodeskclaw-openclaw-base:v2026.2.26
```

### 6.4 构建产物检查清单

- [ ] `node --version` 输出正确版本
- [ ] `openclaw --version` 输出正确版本
- [ ] `which openclaw` → `/usr/local/bin/openclaw`
- [ ] `/root/.openclaw/` 目录结构完整（所有子目录存在）
- [ ] `/root/.openclaw/openclaw.json.template` 存在
- [ ] `/root/.openclaw-version` 内容正确
- [ ] `/docker-entrypoint.sh` 可执行
- [ ] `/init-container.sh` 可执行
- [ ] 镜像大小合理（目标 < 400MB）

---

## 七、GitHub Actions 自动化

### 7.1 版本检测工作流

文件：`.github/workflows/check-openclaw-update.yml`

- **触发**：每天 UTC 08:00（北京时间 16:00）+ 手动触发
- **逻辑**：查询 npm 最新稳定版 → 对比 Dockerfile → 版本不同时自动创建 PR
- **不自动合并**：PR 创建后等人工审核

### 7.2 镜像构建推送工作流

文件：`.github/workflows/build-openclaw-image.yml`

- **触发**：仅手动触发（`workflow_dispatch`），需输入 `openclaw_version`
- **逻辑**：验证 npm 版本 → 登录火山云 CR → 构建 linux/amd64 → 推送 `v{version}` + `latest`

### 7.3 GitHub Secrets 配置

| Secret | 说明 |
|--------|------|
| `VOLCENGINE_CR_REGISTRY` | 镜像仓库地址（如 `nodesk-center-cn-beijing.cr.volces.com`） |
| `VOLCENGINE_CR_USERNAME` | 仓库用户名 |
| `VOLCENGINE_CR_PASSWORD` | 仓库密码 |

---

## 八、待确认事项

| # | 问题 | 状态 |
|---|------|------|
| 1 | ~~OpenClaw gateway 实际监听端口是多少？~~ | ✅ **18789**（`DEFAULT_GATEWAY_PORT`，通过 `OPENCLAW_GATEWAY_PORT` 覆盖） |
| 2 | ~~OpenClaw 是否有 HTTP 健康检查端点？~~ | ✅ **没有 HTTP 端点**，健康检查通过 WebSocket RPC `health` 方法，K8s 用 exec probe: `openclaw health` |
| 3 | ~~`openclaw-gateway` 前台运行的正确命令是什么？~~ | ✅ `exec openclaw gateway`（官方 Dockerfile 用 `node openclaw.mjs gateway --allow-unconfigured`） |
| 4 | ~~`openclaw.json` 的完整 schema~~ | ✅ 源码 `src/config/zod-schema.ts`（`OpenClawSchema`），类型 `src/config/types.openclaw.ts`，已在 4.2 节摘录核心字段 |
| 5 | ~~OpenClaw 是否需要外部数据库/Redis？~~ | ✅ **不需要**，仅用本地 SQLite（`node:sqlite` + `sqlite-vec`），数据在 `~/.openclaw/memory/` |
| 6 | ~~飞书插件 `feishu-db.json` 的完整字段定义~~ | 🔘 暂不处理（属于插件层，后续按需） |
| 7 | ~~`credentials/` 目录下的文件格式~~ | ✅ `oauth.json`、`<channel>-pairing.json`、`<channel>-allowFrom.json` 等 JSON 文件，已在 4.4 节说明 |
