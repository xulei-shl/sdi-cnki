# CNKI 学术定题服务系统

基于 Camoufox + Playwright 自动化与 LLM 智能分析的学术文献定题跟踪与批量下载平台。

## 技术栈

| 类别 | 技术 |
|------|------|
| 前端 | React 18 + TypeScript + Tailwind CSS v4 + shadcn/ui |
| 后端 | FastAPI + SQLAlchemy 2.x async + SQLite |
| 爬虫 | Camoufox + Playwright（反检测浏览器自动化） |
| AI | OpenAI 兼容接口多配置轮询（LLM 批量分析） |
| 队列 | 轻量任务队列（SQLite 持久化，零外部依赖） |
| 推送 | SSE (Server-Sent Events) 实时进度 |

## 快速开始

```bash
# 后端
cd backend
pip install -r requirements.txt
playwright install chromium
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
uvicorn app.main:app --reload --port 8000

# Worker 进程（每种队列新终端）
python worker_runner.py cnki 1
python worker_runner.py llm 5
python worker_runner.py download 1
python worker_runner.py export 2

# 前端（需先进入 frontend）
cd frontend
npm install
npm run dev
```

```
# 后端启动 (端口 8000)
cd backend && python -m uvicorn app.main:app --reload --port 8000

# 前端启动 (端口 8848)
cd frontend && npx vite --port 8848
```

管理后台：http://localhost:8848（前端，自动代理 /api 到 8000）
API 文档：http://localhost:8000/docs  
默认账号：`admin` / `admin123`

## 核心功能

- **任务模板**：配置 CNKI 检索参数 + LLM 分析配置，支持手动/周期性执行
- **CNKI 自动检索**：Camoufox 自动化高级检索、翻页导出、Excel 解析入库
- **智能去重**：基于题名+期刊+年份的规范化三重判定
- **LLM 批量分析**：多 Provider 轮询、4 级 JSON 解析容错、并发控制
- **人工审核**：单条/批量通过/拒绝、相关性评分可视化
- **PDF 下载**：哲舍科→万方→CNKI 三来源轮询、引用计数跨实例复用
- **数据导出**：异步 ZIP 打包（含 results.xlsx + analysis_results.xlsx + PDFs）
- **实时推送**：SSE 进度（检索/分析/下载），企业微信 Webhook 通知
- **权限控制**：Admin/User 双角色，动态路由 + 按钮级鉴权

## 项目结构

```
sdi-cnki/ (v2)
├── backend/                      # FastAPI 后端
│   ├── app/
│   │   ├── main.py              # FastAPI 入口
│   │   ├── config.py             # Pydantic Settings
│   │   ├── database.py           # SQLAlchemy async engine
│   │   ├── dependencies.py       # JWT + bcrypt 工具
│   │   ├── models/               # 14 张 ORM 模型
│   │   ├── routers/              # 10 个路由模块
│   │   ├── services/             # 业务服务层
│   │   ├── task_queue/           # 轻量任务队列
│   │   ├── utils/                # 日志/异常/加密/标准化
│   │   └── worker/               # Worker 实现
│   ├── worker_runner.py          # Worker 进程入口
│   ├── alembic/                  # 数据库迁移
│   ├── tests/                    # 测试用例
│   └── requirements.txt
├── frontend/                     # React 18 + Tailwind + shadcn/ui 前端
│   ├── src/
│   │   ├── pages/                # 页面组件
│   │   ├── api/                  # HTTP API 模块
│   │   ├── lib/                  # SSE 客户端、HTTP 工具等
│   │   ├── context/              # Auth 上下文
│   │   ├── components/           # UI 组件
│   │   └── types/                # TypeScript 类型
│   └── package.json
├── docs/                         # 设计文档与手册
├── Dockerfile                    # 构建镜像
└── .rules/                       # 开发规范
```

## 任务队列

| 队列 | 用途 | 并发 | 说明 |
|------|------|------|------|
| `cnki` | CNKI 检索 | 1 | 浏览器操作，串行 |
| `llm` | LLM 分析 | 5 | API 调用 |
| `download` | PDF 下载 | 1 | 浏览器操作，串行 |
| `export` | 导出打包 | 2 | 文件操作 |

## 状态流转

```
pending → running → search_completed → analyzing
→ analyzing_completed → ready_for_download → downloading → completed
```

任意阶段失败 → `failed`，通过 SSE 和企微 Webhook 即时通知。
