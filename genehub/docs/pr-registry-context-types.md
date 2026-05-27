# fix(registry): 为 Hono Context 声明 Auth 变量类型，消除 genes 等 API 的 TypeScript 报错

## Summary

- 修复 Registry 中 `packages/registry/src/api/genes.ts` 等文件因 Hono Context 未声明 `authRole` / `publisherId` / `githubLogin` 导致的 TypeScript 报错（`c.get('authRole')` 等被判定为非法）。
- 在 auth 中间件中导出 `AuthVariables` 类型，并在主 App 与 genes 路由上使用 `Hono<{ Variables: AuthVariables }>`，使类型与运行时行为一致。

## Changes

| 文件 | 变更 |
|------|------|
| `packages/registry/src/middleware/auth.ts` | 新增并导出 `AuthVariables` 类型（authRole、publisherId、githubLogin） |
| `packages/registry/src/app.ts` | 使用 `new Hono<{ Variables: AuthVariables }>()` 创建 App |
| `packages/registry/src/api/genes.ts` | 使用 `new Hono<{ Variables: AuthVariables }>()` 创建 genesRouter |

## Impact

- **运行时**：无行为变化，auth 中间件原本就会注入上述变量。
- **构建 / CI**：带类型检查的构建与 `tsc` 可通过。
- **开发体验**：IDE 中相关类型错误与红色波浪线消失。

## Test plan

- 在 `packages/registry` 下执行 `pnpm build` 与 `pnpm test`，确认通过。
- 本地 `pnpm dev` 启动 Registry，调用需鉴权或 optionalAuth 的接口（如 `GET /api/v1/genes?review_status=...`），确认行为与修改前一致。
