# 网站响应性能优化方案

## 1. 性能瓶颈分析

### 1.1 Bundle 体积过大（最严重）

| 指标 | 当前值 | 问题 |
|------|--------|------|
| 初始 JS 体积 | **727KB**（单文件） | 所有页面代码打包在一起 |
| 入口文件 | `dist/assets/index-DB4fzu5W.js` | 无路由级代码分割 |
| 原因 | `src/router.tsx:1-16` 全部静态 `import` | 用户下载了从不访问的页面代码 |

**根本原因**：13 个页面组件全部通过顶层 `import` 静态导入，Vite 默认将所有代码打包到单一 chunk 中。

### 1.2 渲染阻塞资源

| 资源 | 当前状态 | 影响 |
|------|----------|------|
| hiagent SDK | `<script src="...">` 同步加载 | 阻塞 HTML 解析直至下载+执行完毕 |
| 位置 | `index.html:12` | 在 body 末尾，但未加 `async`/`defer` |

### 1.3 认证阻塞初始渲染

- **`protected-route.tsx:12`**：`if (loading) return null` → 白屏
- **`auth.tsx:24-42`**：虽已从 localStorage 读取 token，但仍需等待 `/auth/me` 网络请求完成
- **影响**：每次应用加载至少增加 1 次网络往返的空白时间

### 1.4 大图片资源

- **`dist/logo-large-icon.jpg`**：**1.33MB**（全项目最大文件）
- 登录页必加载，直接拖慢首次有效绘制

### 1.5 无生产压缩

- **`.env.production:13`**：`VITE_COMPRESSION = "none"`
- 727KB JS 未经压缩传输（gzip 后可降至约 200KB）

### 1.6 HTTP 超时过长

- **`src/lib/http.ts:5`**：`timeout: 60000`
- 后端慢时用户需等待 60 秒才能看到错误

### 1.7 页面组件过大

| 文件 | 行数 | 大小 |
|------|------|------|
| `src/pages/task-result/index.tsx` | **911 行** | **44KB** |
| `src/pages/meta-task/index.tsx` | 388 行 | 17KB |
| `src/pages/task-instance/index.tsx` | 446 行 | 21KB |

### 1.8 无 Vendor 代码分割

- 所有第三方依赖（React, Axios, Radix UI, etc.）与应用代码打包在同一 chunk
- 无法利用浏览器缓存隔离（vendor 代码变更少，应单独缓存）

---

## 2. 优化方案（按优先级排序）

### Phase 1：快速见效（低投入，高回报）

| # | 优化项 | 文件 | 操作 | 预期收益 |
|---|--------|------|------|----------|
| 1 | 启用 Gzip 压缩 | `.env.production` | `VITE_COMPRESSION = "gzip-clear"` | JS 传输体积从 727KB → ~200KB |
| 2 | SDK 脚本异步加载 | `index.html` | 添加 `async` 属性 | 消除渲染阻塞 |
| 3 | 压缩 Logo 图片 | `public/logo-large-icon.jpg` | 压缩至 <100KB，或转换为 WebP | 减少 1.2MB+ 传输量 |
| 4 | 降低 HTTP 超时 | `src/lib/http.ts` | `timeout: 60000` → `timeout: 15000` | 失败反馈从 60s 降至 15s |

### Phase 2：路由级代码分割（中等投入，高回报）

| # | 优化项 | 文件 | 操作 | 预期收益 |
|---|--------|------|------|----------|
| 5 | 实现 `React.lazy()` + `Suspense` | `src/router.tsx` | 将 13 个静态 import 改为 `React.lazy()`，外层包裹 `Suspense` | 初始 JS 从 727KB 降至 ~150KB |
| 6 | Vendor 代码分割 | `vite.config.ts` | 配置 `manualChunks` 分离 react 全家桶 | 利用浏览器缓存，减少重复下载 |

### Phase 3：认证体验优化（中等投入，中等回报）

| # | 优化项 | 文件 | 操作 | 预期收益 |
|---|--------|------|------|----------|
| 7 | 加载骨架屏 | `protected-route.tsx` | `return null` → `return <Skeleton className="..." />` | 消除白屏，提供视觉反馈 |
| 8 | 背景验证 Token | `auth.tsx` | 先渲染缓存用户，后台异步验证 `/auth/me`，不阻塞 `loading` | 首屏渲染 0 等待 |

### Phase 4：组件重构（较高投入，中低回报）

| # | 优化项 | 文件 | 操作 | 预期收益 |
|---|--------|------|------|----------|
| 9 | 拆分 task-result | `src/pages/task-result/` | 提取 dialog、progress、table 到独立子组件 | 降低单文件体积，提升可维护性 |
| 10 | 拆分 meta-task | `src/pages/meta-task/` | 提取 search-bar、detail-panel、dialogs | 同上 |

---

## 3. 预期效果汇总

| 指标 | 优化前 | 优化后（估计） | 降幅 |
|------|--------|---------------|------|
| 初始 JS 体积 | 727KB | ~150KB（路由分割） | **-79%** |
| 传输体积（gzip） | 727KB（原） | ~200KB（gzip后） | **-72%** |
| 图片传输 | 1.33MB | <100KB | **-92%** |
| 渲染阻塞 | SDK 同步 + 727KB JS | 仅首屏异步加载 | 消除 |
| 首屏白屏时间 | 1~2 次网络往返 | 0（骨架屏+缓存渲染） | 消除 |
| 错误反馈时间 | 60s | 15s | **-75%** |

---

## 4. 实施顺序建议

```
Phase 1 → Phase 2 → Phase 3 → Phase 4
  快速      核心      体验      打磨
  (1-4)     (5-6)     (7-8)     (9-10)
```