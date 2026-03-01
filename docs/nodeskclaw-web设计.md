# nodeskclaw-web 项目设计文档

## 项目概述

nodeskclaw-web 是 NoDeskClaw（现 ClawBuddy）的综合主页，承载 Landing Page、文档站、演示站等功能，作为产品的统一入口。

- **项目名称**：nodeskclaw-web
- **域名**：claw.nodeskai.com
- **技术栈**：Vue 3 + Vite + Tailwind CSS + Vue I18n

## 页面规划

| 页面 | 路由 | 说明 |
|------|------|------|
| 首页 | `/` | Landing Page，产品介绍、特性、入口按钮 |
| 文档 | `/docs` | 文档列表页 |
| 文档详情 | `/docs/:slug` | 单篇文档渲染 |
| 演示 | `/demo` | 产品功能演示 |
| 关于 | `/about` | 团队、联系方式 |

## 技术架构

### 1. 技术栈

| 依赖 | 版本 | 说明 |
|------|------|------|
| vue | ^3.5.25 | 框架 |
| vite | ^7.3.1 | 构建工具 |
| tailwindcss | ^4.1.18 | 样式 |
| vue-router | ^4.6.4 | 路由 |
| vue-i18n | ^11.1.12 | 国际化 |
| pinia | ^3.0.4 | 状态管理 |
| lucide-vue-next | ^0.563.0 | 图标 |
| marked | ^17.0.3 | Markdown 渲染 |
| axios | ^1.13.5 | HTTP 客户端 |

### 2. 目录结构

```
nodeskclaw-web/
├── src/
│   ├── assets/             # 静态资源
│   ├── components/         # 共享组件
│   │   ├── layout/        # 布局组件（Header、Footer）
│   │   └── ui/            # UI 组件（复用现有）
│   ├── composables/       # 组合式函数
│   ├── router/            # 路由配置
│   │   └── index.ts
│   ├── styles/            # 样式
│   │   └── globals.css
│   ├── views/             # 页面
│   │   ├── Home.vue       # 首页
│   │   ├── Docs.vue       # 文档列表
│   │   ├── DocDetail.vue  # 文档详情
│   │   ├── Demo.vue       # 演示页
│   │   └── About.vue      # 关于
│   ├── i18n/              # 国际化
│   │   ├── index.ts
│   │   └── locales/
│   │       ├── zh-CN.ts
│   │       └── en-US.ts
│   ├── App.vue
│   └── main.ts
├── public/
│   └── docs/              # 文档软链接或复制
├── index.html
├── package.json
├── vite.config.ts
├── tsconfig.json
├── tsconfig.app.json
├── tsconfig.node.json
├── Dockerfile
├── nginx.conf
└── .env.example
```

## 功能设计

### 1. 首页（Landing Page）

**内容模块**：

- **Hero 区**：产品标题、副标题、CTA 按钮
- **特性展示**：3-4 个核心功能卡片
- **入口区**：管理后台、用户门户按钮
- **底部**：链接、版权信息

**交互**：
- 语言切换（顶部）
- 响应式布局

### 2. 文档系统

**数据来源**：`ClawBuddy/docs/` 目录下的 Markdown 文件

**实现方式**：
- 方案 A：复制 docs/ 到 public/docs，通过 fetch 加载
- 方案 B：构建时复制，构建后静态部署
- 方案 C：Vite 插件读取 docs/ 动态生成路由

**推荐方案 A**，简单可靠。

**渲染**：
- 使用 `marked` 渲染 Markdown
- 支持代码高亮（highlight.js 或 prism）
- 支持目录导航

### 3. 演示页

**内容**：
- 产品截图轮播
- 功能 GIF 展示
- 视频演示（可选）

### 4. 国际化

**语言**：`zh-CN`、`en-US`

**实现**：
- 复用现有 i18n 结构
- 与 nodeskclaw-frontend、nodeskclaw-portal 保持一致

## 与现有系统的关系

| 系统 | 关系 |
|------|------|
| nodeskclaw-backend | 复用 API（如获取版本信息） |
| nodeskclaw-frontend | 复用 UI 组件、样式、i18n |
| nodeskclaw-portal | 复用 i18n、样式 |
| docs/ | 文档来源 |

## 部署设计

### 1. Docker 构建

```dockerfile
# Dockerfile
FROM node:22-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm install
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

### 2. K8s 部署

参考 `nodeskclaw-frontend` 的 Deployment 和 Service 配置。

### 3. Ingress 配置

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: nodeskclaw-web
  annotations:
    nginx.ingress.kubernetes.io/proxy-body-size: "50m"
spec:
  rules:
    - host: claw.nodeskai.com
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: nodeskclaw-web
                port:
                  number: 80
```

## 实施计划

### 阶段 1：项目初始化

- [ ] 初始化 Vue 3 + Vite 项目
- [ ] 配置 Tailwind CSS
- [ ] 配置 Vue I18n
- [ ] 配置 Vue Router

### 阶段 2：基础页面

- [ ] 创建首页 Landing Page
- [ ] 创建布局组件（Header、Footer）
- [ ] 实现响应式布局

### 阶段 3：文档系统

- [ ] 集成 docs/ 目录
- [ ] 实现 Markdown 渲染
- [ ] 实现文档列表页
- [ ] 实现文档详情页

### 阶段 4：扩展功能

- [ ] 添加演示页
- [ ] 添加关于页
- [ ] 完善 i18n 文案

### 阶段 5：部署

- [ ] 编写 Dockerfile
- [ ] 编写 nginx.conf
- [ ] 编写 K8s 部署配置
- [ ] 配置 Ingress 域名

## 环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| `VITE_API_BASE` | 后端 API 地址 | `http://localhost:8000` |
| `VITE_APP_TITLE` | 网站标题 | `NoDeskClaw` |

## 注意事项

1. **样式统一**：与现有前端保持一致的 Tailwind 配置
2. **i18n 复用**：考虑抽取到共享包或保持结构一致
3. **文档同步**：docs/ 更新时需同步到 web 项目
4. **SEO**：添加必要的 meta 标签
5. **性能**：首屏加载优化，图片懒加载
