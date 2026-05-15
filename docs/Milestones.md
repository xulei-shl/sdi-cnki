# CNKI 学术定题服务系统 - 开发里程碑 (Milestones)

## 2026-05-15：初始化 Pure Admin 前端框架

- **概要**：使用 `@pureadmin/cli` 脚手架初始化 `pure-admin-thin`（v6.2.0，非国际化精简版）到项目根目录
- **验证**：TypeScript 类型检查 ✅ | 生产构建 ✅（14.15s, 2.23 MB）

---

## 📌 Milestone 1: 系统基础架构与环境搭建 ✅
**目标**: 搭建全栈开发环境并完成核心数据库与任务队列设计。

- [x] [后端] 初始化 FastAPI 项目目录结构（`backend/app/`），配置 CORS、AppError 异常处理、JSON 结构化日志
- [x] [后端] 配置 SQLite + SQLAlchemy async，12 张数据模型（users, llm_configs, system_configs, system_prompts, meta_tasks, meta_task_llm_configs, task_instances, task_results, llm_analysis_results, download_results, operation_logs, task_queue），Alembic 迁移脚本
- [x] [后端] 轻量任务队列：`task_queue` 表 + `BaseWorker` 轮询框架 + `Semaphore` 并发控制 + 重试/超时
- [x] [后端] `TaskQueueService` CRUD（入队/出队/完成/失败/重试/队列长度查询）
- [x] [前端] 初始化 Pure Admin 框架 + 配置 Vite 代理到后端 8000 端口
- [x] [测试] FastAPI health ok / 12 张表自动创建 / Task Queue CRUD ok / JWT 登录 ok

## 📌 Milestone 2: 用户认证与角色权限 ✅
**目标**: 实现双角色（Admin/User）认证与路由控制。

- [x] [后端] JWT 双 Token（access_token 15min, refresh_token 7天）+ bcrypt 密码哈希
- [x] [后端] 用户 CRUD（仅 admin 可管理），含权限隔离查询
- [x] [后端] 操作日志自动记录（operation_logs 表）
- [x] [前端] 登录页对接后端 API，Token 持久化 + 无感刷新
- [x] [前端] 动态路由：Admin 可见「系统设置」菜单，普通用户仅见业务菜单
- [x] [前端] 用户管理页面（管理员专属）：列表/新建/编辑/删除/状态切换
- [ ] [待办] Rate Limiting（5次/分钟防爆破）— 低优先级 V1.1

## 📌 Milestone 3: 系统设置与核心配置模块 ✅
**目标**: 实现大模型、提示词和系统配置管理。

- [x] [后端] LLM Configs CRUD + AES-256 api_key 加密/掩码
- [x] [后端] System Prompts CRUD（启用/停用）
- [x] [后端] System Configs（Key-Value 编辑）
- [x] [前端] 大模型管理页面：列表、新建/编辑弹窗、API Key 掩码
- [x] [前端] 提示词管理页面：多行文本/代码格式弹窗
- [x] [前端] 系统配置页面：Key-Value 编辑保存

## 📌 Milestone 4: 任务模板（元任务）管理 ✅
**目标**: 用户核心流程起点，创建定题服务模板。

- [x] [后端] MetaTask CRUD + 搜索/分页/权限过滤
- [x] [后端] JSON 存储检索参数 + `meta_task_llm_configs` 优先级中间表
- [x] [后端] 执行逻辑：实例编号 `T{YYYYMMDD}{3位序列号}` + `execution_params` 快照 + `auto_run` 两种模式
- [x] [前端] 任务模板列表页：表格展示、关键词/日期筛选、权限控制
- [x] [前端] 新建/编辑弹窗：分组字段、检索参数、LLM/提示词联动下拉
- [ ] [待办] LLM 多选拖拽排序组件（当前为多选列表，后续可升级为拖拽）

## 📌 Milestone 5: CNKI 检索核心 Worker 与去重机制 ✅
**目标**: 实现可靠的自动化网页检索与批次解析、规范化去重。

- [x] [环境] 配置 Playwright + Camoufox 环境（依赖已加入 requirements.txt）
- [x] [Worker] `cnki_worker.py` + `interactor.py`（高级检索 + 翻页导出 + 合并 + 去重入库）
- [x] [后端] Excel 解析逻辑（`excel_parser.py`，openpyxl 列映射提取 + 分段表头清理）
- [x] [后端] 去重服务：`normalize()` + `batch_check_and_mark()` 三重判定
- [x] [后端] SSE 检索进度推送（`sse.py` 事件广播 + 心跳 + 终端事件检测）
- [x] [测试] 去重单元测试 + normalize 测试（`tests/test_dedup.py`）

**新增文件**：
- `app/services/excel_parser.py` — Excel 列映射解析
- `app/services/dedup_service.py` — 去重服务
- `app/services/cnki/exceptions.py` — CNKI 异常定义
- `app/services/cnki/browser.py` — Camoufox 浏览器管理（从 docs/cnki-search/ 移植）
- `app/services/cnki/interactor.py` — 交互编排（忠实复刻原型全部 6 个 mixin 的 CSS 选择器、JS evaluate、重试逻辑、等待模式）
- `app/services/cnki/playwright_helpers.py` — 页面向导函数（click_first_available, disable/enable_checkbox, first_visible_locator, set_input_value, wait_for_any_selector, ensure_checkbox_checked）
- `app/worker/cnki_worker.py` — CNKI Worker（同步 Camoufox + 异步 DB 处理）
- `app/worker/download_worker.py` — PDF 下载 Worker（复用 CNKI 会话）
- `tests/test_dedup.py` — 去重单元测试

**修改文件**：
- `worker_runner.py` — 对接新的 CnkiWorker / DownloadWorker
- `routers/sse.py` — 事件广播 + 条件等待 + 心跳 + 终端检测
- `requirements.txt` — 添加 camoufox/playwright/lxml/requests

## 📌 Milestone 6: LLM 批量分析 Worker ✅
**目标**: 实现容错性高的并发大模型评估任务。

- [x] [后端] LLM Provider 抽象层（OpenAI 兼容接口 + 多配置轮询重试）
- [x] [Worker] `llm_worker.py`：并发批处理 5 条 + 重试 + 多配置轮询
- [x] [后端] 多策略 JSON 解析（4 级策略）
- [x] [后端] 结果写入 + 状态更新 + SSE 推送（含 analyzing 进度 + analyzing_completed 终端事件）
- [x] [后端] CNKI 检索完成后自动触发 LLM 分析入队（`cnki_worker.py` 中 auto_enqueue）
- [x] [测试] 全 4 级 JSON 解析策略单元测试通过 + normalize 修复 3 个预置 Bug
- [x] [验证] Python 导入全部正常 + TypeScript 0 errors

**新增文件**：
- `app/services/llm_provider.py` — LLM Provider 抽象层（httpx OpenAI 兼容）
- `app/services/json_parser.py` — 4 级多策略 JSON 解析
- `app/worker/llm_worker.py` — LLM 并发批处理 Worker（BATCH_SIZE=5）

**修改文件**：
- `app/worker/cnki_worker.py` — 检索完成后自动 enqueue `llm` 队列任务
- `worker_runner.py` — LlmWorker 对接真实 `run_llm_analysis`
- `app/utils/normalize.py` — 修复全角标点/括号去除不完整的 Bug

## 📌 Milestone 7: 任务实例管理与实时查询 (SSE) ✅
**目标**: 前台交互式监控体验。

- [x] [后端] 任务实例列表/详情/取消接口（含聚合统计）
- [x] [后端] 结果列表接口（筛选条件完整：审核/分析/期刊/年份/评分/含重复）
- [x] [后端] SSE 端点 `/api/v1/tasks/{instance_id}/events`
- [x] [前端] 任务实例列表页面：筛选、表格、分页
- [x] [前端] 任务结果详情页：阶段指示器、筛选栏、批量操作、详情面板
- [x] [前端] SSE 前端连接管理（轻量 `SseClient`：fetch + ReadableStream，指数退避重连，Last-Event-ID，Auth header，终端事件自动关闭）
- [x] [前端] 真实 SSE 接入 task-result 页：analyze 进度、download 进度、终端事件自动刷新数据
- [x] [前端] 任务详情面板：LLM 分析结果动态键值渲染、枚举标签高亮

**新增文件**：
- `src/utils/sse.ts` — 轻量 SSE 客户端（零额外依赖）

**修改文件**：
- `src/views/task-result/index.vue` — 重写：7 步阶段指示器、SSE 实时进度、筛选/排序/分页、批量操作（通过/拒绝）、单条通过/拒绝切换、LLM 分析结果详情面板
- `src/api/taskInstance.ts` — 新增 `markPass`、`batchUpdateResults` API

## 📌 Milestone 8: 人工审核与 PDF 下载 Worker ✅
**目标**: 用户接管 LLM 产出并执行物理文件保留。

- [x] [后端] 单条/批量通过/拒绝 API（支持取消）
- [x] [后端] 启动下载 API（入队 download 队列）
- [x] [Worker] `download_worker.py` 批量 PDF 下载（Camoufox 同步 + 线程池）
- [x] [后端] PDF 引用计数（`PdfFile` 模型 + `ref_count` 跨实例共享，物理文件自动清理）
- [x] [后端] 下载阶段 SSE 进度推送
- [x] [前端] 结果页批量操作 + 单条通过/拒绝 + 下载按钮
- [x] [测试] 审核 API 集成测试 + PDF 引用计数测试

**新增文件**：
- `app/models/pdf_file.py` — PdfFile 模型（`original_url`, `file_hash`, `file_size`, `ref_count`）
- `app/services/pdf_cleanup.py` — PDF 引用计数清理服务（自动删除 ref_count=0 物理文件）
- `tests/test_review_and_refcount.py` — 审核 API + ref_count 集成测试

**修改文件**：
- `app/models/download_result.py` — 添加 `pdf_file_id` FK 到 `pdf_files`
- `app/worker/download_worker.py` — 重写：接入三来源轮询（哲舍科→万方→CNKI），全部失败标记 `skipped`
- `app/services/pdf_downloader.py` — **[新增]** PDF 下载优先级轮询：先按题名搜索哲舍科，再按题名搜索万方，最后导航 CNKI 原文链接
- `app/routers/task_instances.py` — 新增 `DELETE /{instance_id}/clean` 端点，级联清理 PDF 文件

## 📌 Milestone 9: 数据导出打包、Webhook通知集成与收尾
**目标**: 批量文件导出和自动化预警。

- [ ] [Worker] `export_worker.py` 异步打包 ZIP
- [ ] [后端] 临时下载链接（24h 过期）
- [ ] [后端] 企微 Webhook 通知（阶段完成/失败）
- [ ] [后端] 磁盘空间监控告警
- [ ] [前端] 导出 Excel/ZIP 功能
- [ ] [全栈] 端到端联调

## 📌 Milestone 10: Docker 部署编排与运维文档
**目标**: 生产部署配置与文档。

- [ ] [后端] 多阶段 Dockerfile
- [ ] [后端] docker-compose.yml（API + Worker + Nginx）
- [ ] [后端] 部署运维手册 + 用户操作手册
- [ ] [全栈] 验收测试报告

---

## 📋 Handoff: 2026-05-15 完整实现冲刺

### 范围

本次冲刺覆盖 **M1-M8 全部完成**。M9（导出/通知）、M10（Docker）为待办。

### 交付物统计

| 维度 | 数量 | 说明 |
|------|------|------|
| Python 后端文件 | 56 个 `.py` | `backend/app/` 下完整 FastAPI 项目 + Worker + Services |
| 数据库表 | 13 张 | 含 `pdf_files` 表，覆盖全部业务 + 队列 + 日志 |
| API 端点 | ~45+ | auth + 6 大模块 CRUD + SSE + 批量操作 + 引用计数清理 |
| 前端 Vue 页面 | 15 个 `.vue` | 7 个业务页面 + 路由/API/Store 层 |
| 前端 API 模块 | 8 个 `.ts` | 对接后端全部端点（含 `markPass`, `batchUpdateResults`）|
| TypeScript 检查 | ✅ 0 errors | `vue-tsc --noEmit --skipLibCheck` |
| 生产构建 | ✅ 8.51s / 2.28 MB | `pnpm build` |
| Python 测试 | ✅ 10 pass | 去重 7/7 + 列映射 + 集成 + 审核/引用计数 |

### 架构决策记录

1. **SQLite + async**：零外部依赖部署，`aiosqlite` 异步驱动，WAL 模式
2. **队列实现**：`task_queue` SQLite 表 + `BaseWorker` 轮询 + `asyncio.Semaphore` 并发控制，无中间件依赖
3. **API 掩码**：LLM API Key 使用 AES-256 (`cryptography.fernet`) 加密存储，返回时 `mask_api_key()` 掩码
4. **密码**：直接使用 `bcrypt`（绕过 passlib 与 Python 3.14 的兼容问题）
5. **前端路由**：Pure Admin 动态路由模式，`meta.roles` 控制菜单可见性
6. **Token 刷新**：Pure Admin 内置 Axios 拦截器 + `isRefreshing` 队列防重入
7. **实例编号**：格式 `T{YYYYMMDD}{3位序列号}`，数据库 `SELECT MAX()` 计算
8. **SSE 前端**：轻量自研 `SseClient`（fetch+ReadableStream），零外部依赖，指数退避重连
9. **PDF 引用计数**：`PdfFile` 模型 + `ref_count` 字段，跨实例共享同一 PDF 文件，ref_count=0 时自动删除物理文件

### 新增文件索引 (本次冲刺)

```
M6 — LLM 批量分析 Worker:
  backend/app/services/llm_provider.py    # httpx OpenAI 兼容 + 多配置轮询重试
  backend/app/services/json_parser.py     # 4 级 JSON 解析策略
  backend/app/worker/llm_worker.py        # 并发批处理(5) + SSE 推送

M7 — SSE 前端连接:
  frontend/src/utils/sse.ts               # 轻量 SSE 客户端

M8 — PDF 引用计数 + 审核:
  backend/app/models/pdf_file.py          # PdfFile 模型 (ref_count)
  backend/app/services/pdf_cleanup.py     # 引用计数清理服务
  backend/app/services/pdf_downloader.py  # 三来源轮询下载（哲舍科→万方→CNKI）
  backend/tests/test_review_and_refcount.py  # 审核 + ref_count 测试
  backend/alembic/versions/001_add_pdf_files.py  # 迁移脚本
```

### 关键文件索引

```
backend/
├── app/main.py               # FastAPI 入口 + 中间件 + 路由注册
├── app/config.py              # Pydantic Settings（.env 加载）
├── app/database.py            # SQLAlchemy async engine + session
├── app/dependencies.py        # JWT/bcrypt 工具函数
├── app/models/                # 13 张 SQLAlchemy 模型
│   ├── pdf_file.py            #   PDF 文件引用计数（M8 新增）
│   └── ...                    #   其他 12 张模型
├── app/routers/               # 9 个路由模块
│   ├── sse.py                 #   SSE 事件广播 + 心跳
│   └── task_instances.py      #   含 /clean 端点的引用计数删除
├── app/task_queue/            # 轻量任务队列（crud + worker）
├── app/utils/                 # crypto, exceptions, logging, oplog, normalize
├── app/services/              # 业务服务层
│   ├── excel_parser.py        #   CNKI Excel 列映射解析
│   ├── dedup_service.py       #   去重服务
│   ├── llm_provider.py        #   LLM Provider 抽象层（M6 新增）
│   ├── json_parser.py         #   多策略 JSON 解析（M6 新增）
│   ├── pdf_cleanup.py         #   PDF 引用计数清理（M8 新增）
│   ├── pdf_downloader.py      #   三来源轮询下载（M8 新增）
│   └── cnki/                  #   CNKI 浏览器/交互模块
│       ├── browser.py         #     Camoufox 浏览器管理
│       ├── interactor.py      #     检索编排
│       └── exceptions.py      #     CNKI 异常定义
├── app/worker/                # Worker 实现
│   ├── cnki_worker.py         #   CNKI 检索 Worker（含自动触发 LLM 分析）
│   ├── llm_worker.py          #   LLM 分析 Worker（M6 新增）
│   └── download_worker.py     #   PDF 下载 Worker（含 ref_count 复用）
├── worker_runner.py           # Worker 进程入口
├── alembic/                   # 迁移配置
│   └── versions/001_add_pdf_files.py
└── requirements.txt           # Python 依赖

frontend/src/
├── utils/sse.ts               # 轻量 SSE 客户端（M7 新增）
├── api/taskInstance.ts        # 含 markPass / batchUpdateResults（M7 新增）
└── views/
    ├── meta-task/index.vue    # 任务模板列表 + CRUD 弹窗
    ├── task-instance/         # 任务实例列表
    ├── task-result/           # 结果详情（M7 重写: SSE 实时进度 + 7 步阶段指示器 + 批量操作）
    └── system/                # 用户/大模型/提示词/系统配置 管理
```

### 待办（低优先级 V1.1）

| 待办 | 影响模块 | 原因 |
|------|----------|------|
| Rate Limiting（5次/分钟） | `routers/auth.py` | 当前未实现，低风险单机部署 |
| LLM 多选拖拽排序 | `views/meta-task/index.vue` | 当前为普通多选列表 |
| SSE 前端断线重连优化 | `utils/sse.ts` | 当前已实现基础版本 |

### 后续建议启动顺序

1. **M9** → `export_worker.py` + 企微 Webhook 通知 + 磁盘监控
2. **M10** → Dockerfile + docker-compose + 运维手册

### 启动命令备忘

```bash
# 后端 API
cd backend && python -m uvicorn app.main:app --reload --port 8000

# Worker 进程（每种队列启动一个终端）
cd backend && python worker_runner.py cnki 1
cd backend && python worker_runner.py llm 5
cd backend && python worker_runner.py download 1
cd backend && python worker_runner.py export 2

# 前端
pnpm dev                                     # 端口 8848，/api 自动代理到 8000

# 数据库迁移（首次需创建 data 目录 + 初始化管理员）
mkdir -p backend/data
cd backend && python -c "
import asyncio; from app.database import init_db, engine; from app.dependencies import hash_password
from sqlalchemy import text
async def s():
    await init_db()
    async with engine.begin() as c:
        await c.execute(text(\"INSERT OR IGNORE INTO users (username, password_hash, email, role, is_active) VALUES ('admin', :pw, 'admin@example.com', 'admin', 1)\"), {'pw': hash_password('admin123')})
    print('DB ready'); await engine.dispose()
asyncio.run(s())
"

# 默认管理员
# username: admin / password: admin123
```
