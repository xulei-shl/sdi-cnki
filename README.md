# CNKI 学术定题服务系统

基于 Camoufox + Playwright 自动化与 LLM 智能分析的学术文献定题跟踪与批量下载平台。

## 技术栈

| 类别 | 技术 |
|------|------|
| 前端 | React 19 + TypeScript + Tailwind CSS v4 + shadcn/ui |
| 后端 | FastAPI + SQLAlchemy 2.x async + SQLite |
| 爬虫 | Camoufox + Playwright（反检测浏览器自动化） |
| AI | OpenAI 兼容接口多配置轮询（LLM 批量分析） |
| 队列 | 轻量任务队列（SQLite 持久化，零外部依赖），支持自动内嵌或独立进程 |
| 推送 | SSE (Server-Sent Events) 实时进度 |

## 快速开始（开发环境）

```bash
# 1. 后端依赖
pip install -r requirements.txt

# 2. Playwright 浏览器（Camoufox 基于 Firefox）
playwright install firefox

# 3. 初始化数据库 & 默认管理员
mkdir -p data
python -c "
import asyncio; from app.database import init_db, engine; from app.dependencies import hash_password
from sqlalchemy import text
async def s():
    await init_db()
    async with engine.begin() as c:
        await c.execute(text(\"INSERT OR IGNORE INTO users (username, password_hash, email, role, is_active) VALUES ('admin', :pw, 'admin@example.com', 'admin', 1)\"), {'pw': hash_password('admin123')})
    print('DB ready'); await engine.dispose()
asyncio.run(s())
"

# 4. 启动后端（端口 8456，worker 自动内嵌启动）
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8456

# 5. 前端
npm install
npm run dev
```

管理后台：http://localhost:8848（前端，自动代理 `/api` 到 `localhost:8456`）
API 文档：http://localhost:8456/docs  
默认账号：`admin` / `admin123`

## 核心功能

- **任务模板**：配置 CNKI 检索参数 + LLM 分析配置，支持手动/周期性执行
- **CNKI 自动检索**：Camoufox 自动化高级检索/专业检索、翻页导出、Excel 解析入库；支持普通检索（多关键词独立执行）和专业检索（双域交叉，一条布尔表达式，1 次检索完成）两种模式
- **智能去重**：基于题名+期刊+年份的规范化三重判定
- **LLM 批量分析**：多 Provider 轮询、4 级 JSON 解析容错、并发控制
- **人工审核**：单条/批量通过/拒绝、相关性评分可视化
- **PDF 下载**：哲舍科→万方→CNKI 三来源轮询、引用计数跨实例复用
- **数据导出**：异步 ZIP 打包（含 results.xlsx + analysis_results.xlsx + references.enw + PDFs）
- **实时推送**：SSE 进度（检索/分析/下载），企业微信 Webhook 通知（按账号独立配置）
- **权限控制**：Admin/User 双角色，动态路由 + 按钮级鉴权

## Hiagent AI 助手浮窗

页面右下角的 AI 助手浮窗基于 [Hiagent Web SDK](https://hiagent.library.sh.cn) 嵌入，支持两种方式：

### 方式 A：全局嵌入（所有页面）

适用于全站使用同一 hiagent 实例的场景。

```html
<!-- index.html → body 末尾 -->
<script src="https://hiagent.library.sh.cn/resources/product/llm/public/sdk/embedLite.js"></script>
<script>
  new HiagentWebSDK.WebLiteClient({ appKey: 'your-key', baseUrl: 'https://hiagent.library.sh.cn' })
</script>
```

SDK + 实例化均在 `index.html` 中以原生 `<script>` 同步加载，简单可靠。

### 方式 B：页面级嵌入（不同页面不同 appKey）

适用于各页面需挂载不同 hiagent 实例的场景。

**1. SDK 加载层 — `index.html`**

```html
<script src="https://hiagent.library.sh.cn/resources/product/llm/public/sdk/embedLite.js"></script>
```

SDK 必须在页面解析阶段以原生 `<script>` 同步加载，否则 `WebLiteClient` 构造函数内部 `fetchAgentConfig()` 的执行上下文会错乱，浮窗无法渲染/交互。

**2. 实例化层 — 页面组件**

```typescript
useHiagentWidget('your-app-key')
```

通过 `src/hooks/use-hiagent-widget.ts` 的 `useHiagentWidget(appKey)` 创建/销毁实例。SDK 已由 `index.html` 加载，hook 仅做直接调用 + cleanup 清理 SDK 生成的 DOM 节点。不调用的页面不产生浮窗。

### 历史

尝试过纯 `useEffect` 动态加载 script + 实例化，但 SDK 构造函数内部的跨域 `fetch` 依赖主线程同步执行上下文，动态执行时序不一致导致请求失败、浮窗不出现。最终方案：原生 `<script>` 只加载 SDK，页面组件通过 hook 控制实例化时机与 appKey。

## 项目结构

```
sdi-cnki/ (v2)
├── app/                          # FastAPI 后端
│   ├── main.py                  # FastAPI 入口
│   ├── config.py                 # Pydantic Settings
│   ├── database.py               # SQLAlchemy async engine
│   ├── dependencies.py           # JWT + bcrypt 工具
│   ├── models/                   # ORM 模型
│   ├── routers/                  # 路由模块
│   ├── services/                 # 业务服务层
│   ├── task_queue/               # 轻量任务队列
│   ├── utils/                    # 日志/异常/加密/标准化
│   └── worker/                   # Worker 实现
├── src/                          # React 前端
│   ├── pages/                    # 页面组件
│   ├── api/                      # HTTP API 模块
│   ├── lib/                      # HTTP 客户端、SSE、工具函数
│   ├── context/                  # Auth 上下文
│   ├── components/               # UI 组件
│   └── types/                    # TypeScript 类型
├── data/                         # 运行时数据（DB、上传、下载、导出）
├── docs/                         # 设计文档与手册
├── tests/                        # 测试用例
├── worker_runner.py              # Worker 独立进程入口
├── run.py                        # 开发用启动入口
├── vite.config.ts                # Vite 配置（含 /api 反向代理）
└── Dockerfile                    # 构建镜像
```

## 任务队列

| 队列 | 用途 | 并发 | 说明 |
|------|------|------|------|
| `cnki` | CNKI 检索 | 1 | 浏览器操作，串行；多用户任务排队等候 |
| `llm` | LLM 分析 | 5 | API 调用 |
| `download` | PDF 下载 | 1 | 浏览器操作，串行；同队列内逐条执行，完成后下一个用户任务才启动 |
| `export` | 导出打包 | 2 | 文件操作 |

## 状态流转

```
pending → running → search_completed → analyzing
→ analyzing_completed → download_queued → downloading → completed
```

任意阶段失败 → `failed`，通过 SSE 和企微 Webhook（按账号独立配置）即时通知。

## 生产部署（Ubuntu + systemd）

详见 `Ubuntu部署说明.md`，关键步骤概览：

```bash
# 1. 安装依赖 & 构建
pip install -r requirements.txt
playwright install firefox
npm install && npm run build

# 2. 初始化数据库（自动在首次启动完成，亦可手动）
mkdir -p data

# 3. 防火墙（允许局域网访问后端 API 和前端页面）
ufw allow 8456/tcp comment 'SDI-CNKI Backend API'
ufw allow 8848/tcp comment 'SDI-CNKI Frontend'

# 4. systemd 服务（开机自启）
cp systemd/*.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now sdi-cnki-backend sdi-cnki-frontend
```

| systemd 服务 | 端口 | 说明 |
|---|---|---|
| `sdi-cnki-backend.service` | **8456** | FastAPI + 4 个 Worker 内嵌自动启动 |
| `sdi-cnki-frontend.service` | **8848** | Vite 服务器，自动反向代理 `/api` → `localhost:8456` |

> **端口 8456** 替代默认 8000，避免与系统上可能的 chromadb 等服务冲突。
