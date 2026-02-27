# i18n 手工回归测试报告

**执行时间**: 2025-02-25  
**测试范围**: 门户 (nodeskclaw-portal) + 管理前端 (nodeskclaw-frontend)

---

## 1. 门户登录页 (http://127.0.0.1:5174/login)

| 步骤 | 操作 | 结果 | 截图/说明 |
|-----|------|------|----------|
| 1 | 打开门户登录页 | **通过** | 页面正常加载 |
| 2 | 记录默认语言主标题 | **通过** | 主标题：「欢迎回来」；副标题：「登录以管理你的 AI 助手实例」；默认语言：zh-CN |
| 3 | 切换语言为 English | **无法执行** | 登录页无语言切换器。语言切换器仅在登录后的主布局 header 中（`App.vue`），未登录无法访问 |
| 4 | 验证切换后文案变化 | **N/A** | 依赖步骤 3 |
| 5 | 触发错误提示（错误登录） | **通过** | 错误文案：「邮箱或密码错误」；可读、非 detail 字段；后端返回 `message_key: errors.auth.invalid_email_or_password`、`message: 邮箱或密码错误`；`resolveApiErrorMessage` 优先使用 message_key 翻译 |

---

## 2. 管理前端 (http://localhost:5173/)

| 步骤 | 操作 | 结果 | 截图/说明 |
|-----|------|------|----------|
| 6 | 打开管理前端 | **通过** | 页面正常加载，默认 zh-CN |
| 6 | 切换语言为 English | **通过** | 顶部有语言下拉框（select），可切换为 English |
| 6 | 验证至少 2 处文案变化 | **通过** | 侧边栏：总览→Dashboard、实例→Instances、事件→Events、集群→Clusters、基因运营→Gene Operations、设置→Settings；主标题：总览→Dashboard；共 7+ 处变化 |

---

## 3. 错误提示契约验证

| 项目 | 结果 | 依据 |
|-----|------|------|
| message_key 优先 | **符合** | `nodeskclaw-portal/src/i18n/error.ts`：`if (message_key && i18n.global.te(message_key)) return i18n.global.t(message_key)` |
| message 回退 | **符合** | 同上：`if (message && message.trim()) return message` |
| 不使用 detail | **符合** | `resolveApiErrorMessage` 仅读取 `message_key`、`message`，无 `detail` 逻辑 |
| 中文错误文案可读 | **通过** | 登录失败显示「邮箱或密码错误」 |
| 英文错误文案 | **未实测** | 门户登录页无切换器，无法在英文态下触发登录错误 |

---

## 4. 结论汇总

| 结论项 | 结果 |
|-------|------|
| **门户 zh/en 切换是否生效** | **部分**：登录页无切换器，需登录后才能切换；登录后主布局有 select 切换器，逻辑正确，但本次未登录无法实测 |
| **管理端 zh/en 切换是否生效** | **是**：切换后侧边栏、主标题等多处文案由中文变为英文 |
| **错误提示契约** | **符合**：message_key 优先、message 回退，未使用 detail；错误文案可读 |

---

## 5. 建议

1. **门户登录页增加语言切换器**：在 `Login.vue` 或登录布局中增加与 `App.vue` 相同的 select，便于未登录用户切换语言并验证英文错误提示。
2. **管理端 Dashboard 部分文案**：如「快捷操作」「最近实例」「实时动态」「部署实例」「管理集群」等仍为中文，可检查是否接入 i18n 词条。
