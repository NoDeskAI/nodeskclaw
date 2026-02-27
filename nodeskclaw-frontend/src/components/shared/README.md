# shared 组件目录

## 用途

放置 `nodeskclaw-frontend`（管理前端）中可复用的共享组件。

## 当前组件

- `LocaleSelect.vue`：语言切换组件（非原生下拉，按钮 + 浮层选项）

## 使用方式

- 通过 `modelValue` 传入当前语言值（`zh-CN` / `en-US`）
- 监听 `update:modelValue` 接收变更后的语言值
