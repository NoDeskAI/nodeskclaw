# portal i18n 模块

## 用途

该目录提供 `nodeskclaw-portal`（用户门户前端）的 i18n（国际化）基础设施：

- locale（语言）自动选择与持久化
- 多语言词条管理（`zh-CN` / `en-US`）
- API 错误统一解析（`message_key` 优先，`message` 回退）

## 目录结构

```
src/i18n/
├── index.ts                 # i18n 初始化、locale 策略
├── error.ts                 # API 错误文案解析
└── locales/
    ├── zh-CN.ts             # 中文词条
    └── en-US.ts             # 英文词条
```

## 使用方式

1. 在 `main.ts` 注入 `app.use(i18n)`。
2. 组件中通过 `useI18n()` 或模板 `$t()` 使用词条。
3. 处理接口错误时使用 `resolveApiErrorMessage(error, fallback)` 统一获取展示文案。
