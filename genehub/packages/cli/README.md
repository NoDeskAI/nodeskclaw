# @nodeskai/genehub - GeneHub CLI

AI 员工基因管理命令行工具，用于搜索、安装、发布基因到 GeneHub Registry。

## 安装

```bash
npm install -g @nodeskai/genehub
```

## 配置

### 配置文件

```bash
genehub config set registry https://genehub.nodeskai.com
genehub config set token <your-token>
genehub config get
```

配置文件存储在 `~/.genehub/config.json`。

### 环境变量

环境变量优先级高于配置文件：

| 环境变量 | 说明 | 对应配置项 |
|---|---|---|
| `GENEHUB_REGISTRY_URL` | Registry 地址 | `registry` |
| `GENEHUB_REGISTRY` | Registry 地址（别名） | `registry` |
| `GENEHUB_TOKEN` | 认证 Token | `token` |

本地开发示例：

```bash
GENEHUB_REGISTRY_URL=http://localhost:3000 GENEHUB_TOKEN=dev genehub publish ./my-gene
```

## 认证

使用 GitHub OAuth 登录，自动创建 API Key：

```bash
genehub auth login      # 打开浏览器完成 GitHub 登录，自动保存 token
genehub auth status     # 查看当前登录状态
genehub auth logout     # 退出登录（清除本地 token）
```

## 命令

| 命令 | 说明 |
|---|---|
| `genehub auth login` | GitHub OAuth 登录 |
| `genehub auth status` | 查看登录状态 |
| `genehub auth logout` | 退出登录 |
| `genehub search [keyword]` | 搜索基因库（默认联邦搜索；`--local` 仅本地 DB） |
| `genehub install <slug>` | 安装基因到当前 Agent 环境 |
| `genehub uninstall <slug>` | 卸载基因 |
| `genehub publish <path>` | 发布基因到 Registry（自动检测 CLAUDE.md / SKILL.md / AGENTS.md） |
| `genehub publish <path> -y` | 非交互模式发布（使用默认值） |
| `genehub list` | 列出已安装的基因 |
| `genehub learn <slug>` | 触发基因深度学习（L2） |
| `genehub init` | 初始化基因项目 |
| `genehub config` | 管理配置 |

## 自动检测发布

`genehub publish` 支持直接发布包含 skill 文件的目录，无需预先创建 `gene.yaml`：

```bash
# 目录中有 CLAUDE.md / SKILL.md / AGENTS.md 等文件即可
genehub publish ./my-claude-project
```

**检测优先级**：`CLAUDE.md` > `SKILL.md` > `AGENTS.md` > `.cursorrules` > `.clinerules` > `instructions.md` > `*.md`

自动推断的字段：
- **slug**：从目录名生成（kebab-case）
- **name**：从文件 H1 标题或 frontmatter 提取
- **description**：从文件首段内容提取
- **skill.content**：完整文件内容

需要交互确认的字段（`-y` 可跳过）：
- category（默认 `development`）
- tags（默认 `ability`）

首次发布后会自动生成 `gene.yaml` 保存到目录中，后续发布可直接使用。

## 目录结构

```
packages/cli/
├── src/
│   ├── index.ts          # 入口，注册所有命令
│   ├── config.ts         # 配置管理（文件 + 环境变量）
│   ├── output.ts         # 格式化输出工具
│   ├── utils/
│   │   ├── detect-skill.ts         # Skill 文件自动检测
│   │   └── interactive-manifest.ts # 交互式 manifest 构建
│   └── commands/
│       ├── auth.ts       # GitHub OAuth 登录
│       ├── config.ts     # config set / get
│       ├── init.ts       # 初始化基因项目
│       ├── install.ts    # 安装基因
│       ├── learn.ts      # 深度学习
│       ├── list.ts       # 列出已安装基因
│       ├── publish.ts    # 发布基因（支持自动检测）
│       ├── search.ts     # 搜索基因
│       └── uninstall.ts  # 卸载基因
├── dist/                 # 构建产物
├── package.json
└── tsup.config.ts
```

## 开发

```bash
cd packages/cli
pnpm install
pnpm build          # 构建
pnpm dev            # 开发模式
pnpm test           # 测试
```
