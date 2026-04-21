# Ragent Python Frontend

基于 Vue 3 + Vite + TypeScript 的前端应用，为 Ragent Python API 提供图形化界面。

## 🚀 快速开始

### 1. 安装依赖

```bash
cd frontend
npm install
```

### 2. 启动开发服务器

```bash
npm run dev
```

前端将在 http://localhost:5173 启动，并自动代理 API 请求到后端 (http://localhost:8000)

### 3. 构建生产版本

```bash
npm run build
```

构建产物将输出到 `dist/` 目录

### 4. 预览生产构建

```bash
npm run preview
```

## 📁 项目结构

```
frontend/
├── src/
│   ├── components/          # 可复用组件
│   ├── pages/              # 页面组件
│   │   ├── ChatPage.vue    # 智能对话页面
│   │   └── KnowledgeBasePage.vue  # 知识库管理页面
│   ├── services/           # API 服务
│   │   ├── api.ts          # Axios 客户端
│   │   ├── chatService.ts  # 聊天服务
│   │   └── knowledgeService.ts  # 知识库服务
│   ├── stores/             # Pinia 状态管理
│   │   └── chatStore.ts    # 聊天状态
│   ├── router.ts           # 路由配置
│   ├── App.vue             # 根组件
│   ├── main.ts             # 入口文件
│   └── style.css           # 全局样式
├── index.html              # HTML 模板
├── vite.config.ts          # Vite 配置
├── tailwind.config.js      # Tailwind CSS 配置
├── tsconfig.json           # TypeScript 配置
└── package.json            # 依赖配置
```

## 🛠️ 技术栈

- **Vue 3** - 渐进式 JavaScript 框架
- **Vite** - 下一代前端构建工具
- **TypeScript** - 类型安全的 JavaScript
- **Vue Router** - 官方路由管理器
- **Pinia** - 官方状态管理库
- **Tailwind CSS** - 实用优先的 CSS 框架
- **Axios** - HTTP 客户端
- **Marked** - Markdown 解析器

## 🎨 功能特性

### 1. 智能对话
- ✅ 流式响应展示
- ✅ 多轮对话上下文
- ✅ 自动滚动到底部
- ✅ 新建对话

### 2. 知识库管理
- ✅ 创建/删除知识库
- ✅ 上传文档（PDF、Word、TXT、Markdown）
- ✅ 查看文档列表
- ✅ 触发分块处理
- ✅ 删除文档

## 🔧 配置说明

### API 代理配置

在 `vite.config.ts` 中配置：

```typescript
server: {
  port: 5173,
  proxy: {
    '/api': {
      target: 'http://localhost:8000',
      changeOrigin: true
    }
  }
}
```

如果后端 API 地址不同，请修改 `target` 字段。

## 📝 开发指南

### 添加新页面

1. 在 `src/pages/` 创建新的 `.vue` 文件
2. 在 `src/router.ts` 中添加路由配置
3. 在侧边栏导航中添加链接

### 添加新服务

1. 在 `src/services/` 创建新的服务文件
2. 使用 `apiClient` 发起 HTTP 请求
3. 在组件中导入并使用

### 状态管理

使用 Pinia Store 管理全局状态：

```typescript
import { useChatStore } from '@/stores/chatStore'

const chatStore = useChatStore()
chatStore.sendMessage('Hello')
```

## 🐳 Docker 部署

前端可以独立部署或使用 Nginx  serving 静态文件：

```dockerfile
FROM node:18-alpine AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

FROM nginx:alpine
COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

## 📄 许可证

Apache 2.0
