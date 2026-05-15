# @nodeskai/genehub-types

GeneHub 共享类型定义与 Zod schemas，供 Registry、SDK、CLI 共用。

## 安装

```bash
npm install @nodeskai/genehub-types
```

## 导出内容

### Zod Schemas

- `GeneManifestSchema` -- 基因 Manifest 完整校验
- `AuthorSchema` -- 作者信息
- `CompatibilityEntrySchema` -- 产品兼容性
- `SkillSchema` / `RuleSchema` / `McpServerSchema` -- 技能、规则、MCP 配置

### 枚举

- `GeneCategory` -- `development` | `data` | `operations` | `network` | `creative` | `communication` | `security` | `efficiency`
- `GeneTag` -- `ability` | `personality` | `knowledge` | `tool`
- `GeneSource` -- `official` | `clawhub` | `evomap` | `community` | `agent` | `github`
- `ReviewStatus` -- `draft` | `pending` | `approved` | `rejected` | `flagged`
- `ProductId` -- `openclaw` | `nanobot` | `deskclaw`

### 实体类型

- `Gene` / `GeneVersion` / `GeneManifest` -- 基因相关
- `Genome` / `GenomeVersion` -- 基因组相关
- `Author` -- 作者

### API 类型

- `GeneListParams` / `GenomeListParams` -- 列表查询参数
- `GeneUpdateInput` / `GenomeUpdateInput` -- 更新输入
- `FederatedSearchParams` / `FederatedSearchResult` -- 联邦搜索
- `ResolveResult` -- 依赖解析结果

### 适配器接口

- `GeneAdapter` -- 产品适配器标准接口（`install` / `uninstall` / `list` / `detect`）

## 开发

```bash
pnpm build          # 构建
pnpm dev            # 开发模式（watch）
pnpm test           # 运行测试
```
