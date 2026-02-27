# NoDeskClaw Frontend（管理后台）

NoDeskClaw 管理后台前端，基于 Vue 3 + TypeScript + Vite。

## 启动方式

```bash
cd nodeskclaw-frontend
npm install
npm run dev
```

默认开发地址：`http://localhost:5173`

## 刷新鲁棒性（初始化）

- 管理端 App 启动采用统一初始化状态（`loading`（加载中）/`ready`（就绪）/`error`（错误））
- 初始化接口任一失败时会展示可见错误态，并提供“重试初始化”入口，不会无限 loading
- 全局 `SSE`（服务端推送）与 token 健康轮询只在“初始化完成 + 当前集群有效”后启动
- 连接失败采用受控重试策略（退避 + 上限），避免高频重连导致页面持续抖动
- 开发环境建议先启动后端 `http://localhost:8000` 再启动前端，后端短暂不可达时前端会进入错误态并可手动重试

## i18n（国际化）

- 语言选择：浏览器语言 `zh*` -> `zh-CN`，`en*` -> `en-US`，其他默认 `en-US`
- 前端通过 `Accept-Language`（语言请求头）把当前语言传给后端
- 接口错误展示优先使用 `message_key`（文案键）翻译，词条缺失时回退 `message`（文案）

## 目录补充

```text
nodeskclaw-frontend/src/
├── i18n/
│   ├── index.ts               # i18n 初始化与 locale 策略
│   ├── locales/
│   │   ├── zh-CN.ts           # 中文词条
│   │   └── en-US.ts           # 英文词条
│   └── README.md              # i18n 模块说明
```
