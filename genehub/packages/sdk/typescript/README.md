# @nodeskai/genehub-sdk

GeneHub TypeScript SDK -- API 客户端、产品适配器和学习引擎。

## 安装

```bash
npm install @nodeskai/genehub-sdk
```

## 使用

### API 客户端

```typescript
import { GeneHubClient } from '@nodeskai/genehub-sdk';

const client = new GeneHubClient({
  registryUrl: 'https://genehub.nodeskai.com',
  token: 'ghb_...',
});

const genes = await client.searchGenes({ q: 'code-review' });
const gene = await client.getGene('code-review');
const manifest = await client.getManifest('code-review');
```

### 产品适配器

为不同 AI 产品提供统一的基因安装/卸载接口：

```typescript
import { OpenClawAdapter } from '@nodeskai/genehub-sdk';

const adapter = new OpenClawAdapter({ workspaceDir: '/path/to/workspace' });
await adapter.install(manifest);
await adapter.uninstall('code-review');
const installed = await adapter.list();
```

支持的适配器：

| 适配器 | 产品 | 说明 |
|---|---|---|
| `OpenClawAdapter` | OpenClaw | AGENTS.md + memory + MCP 配置 |
| `NanobotAdapter` | nanobot | memory 记录、版本解析 |
| `GenericAdapter` | 通用 | 基础文件写入 |

### 学习引擎

```typescript
import { LearningEngine } from '@nodeskai/genehub-sdk';

const engine = new LearningEngine(client, adapter);
const task = await engine.createTask('code-review');
const result = await engine.checkResult('code-review');
```

## 目录结构

```
packages/sdk/typescript/
├── src/
│   ├── index.ts              # 导出入口
│   ├── client.ts             # GeneHubClient API 客户端
│   ├── adapters/             # 产品适配器
│   │   ├── base.ts
│   │   ├── openclaw.ts
│   │   ├── nanobot.ts
│   │   └── generic.ts
│   └── learning/
│       └── engine.ts         # L2 深度学习引擎
├── dist/                     # 构建产物
└── package.json
```

## 开发

```bash
pnpm build          # 构建
pnpm dev            # 开发模式（watch）
pnpm test           # 运行测试
```
