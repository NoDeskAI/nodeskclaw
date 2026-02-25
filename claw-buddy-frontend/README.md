# ClawBuddy Frontend（管理后台）

ClawBuddy 管理后台前端，基于 Vue 3 + TypeScript + Vite。

## 启动方式

```bash
cd claw-buddy-frontend
npm install
npm run dev
```

默认开发地址：`http://localhost:5173`

## i18n（国际化）

- 语言选择：浏览器语言 `zh*` -> `zh-CN`，`en*` -> `en-US`，其他默认 `en-US`
- 前端通过 `Accept-Language`（语言请求头）把当前语言传给后端
- 接口错误展示优先使用 `message_key`（文案键）翻译，词条缺失时回退 `message`（文案）

## 目录补充

```
claw-buddy-frontend/src/
├── i18n/
│   ├── index.ts               # i18n 初始化与 locale 策略
│   ├── locales/
│   │   ├── zh-CN.ts           # 中文词条
│   │   └── en-US.ts           # 英文词条
│   └── README.md              # i18n 模块说明
```
