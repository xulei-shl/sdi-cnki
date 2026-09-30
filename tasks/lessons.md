# 经验教训

## 2026-09-30: 重跑分析把已完成实例打回「审核中」

### Bug: `completed` 终态被后续分析覆盖（实例 T20260830002）
- **现象**: 实例 7 条审核通过记录已全部下载成功，本应 `completed`，页面上却永久显示「审核中」。
- **根因**: 实例状态是**派生值**（由 `task_results` / `download_results` 算出），却被 7 个文件里 20 余处代码各自直接赋值。其中 `app/worker/llm_worker.py` 的成功分支**写死** `instance.status = "analyzing_completed"`，而 `retry-analysis` 端点允许对 `completed` 实例重跑（前端 `canRetryAnalysis` 也把 `completed` 列进去了）——于是“重跑分析”把终态打回中间态。
- **证据链**: 批量下载队列行 269 于 `09:42:50` 完成（`completed_cnt >= approved_cnt` → 应置 `completed`）→ `09:52:43` 重跑分析（队列行 292）→ `09:52:47` 写完，`analysis_completed_at` 与之完全吻合，状态 = `analyzing_completed`。
- **教训**: “是否已终态”这条规则不能由每个 worker 各自实现。凡是在审核/下载阶段结束时决定实例状态的路径，**必须**复用数据派生的 `app/services/download_progress.py:resolve_review_status()`，不得写死常量。新增此类路径时同样适用。
- **验证方式**: `tests/test_review_status.py` 钉死该不变量；已反向验证（把判定退回“写死常量”后用例确实失败）。

### 不是 Bug: 行级「下载」按钮不修改实例状态
- **约定**: `POST /{instance_id}/results/{result_id}/retry-download` **有意**不修改实例状态（见 2026-05-18 条目）。
- **由此产生的正常现象**: 用户逐条下载完所有已通过记录、但从未点过批量「下载」时，实例会一直停在「审核中」，`download_started_at` 为 `NULL`（实例 T20260608002 即如此）。这是操作顺序问题，**不要**为此把行级下载改成会推进终态——那会让实例变 `completed`，而前端 `isEditableStatus` 只含 `analyzing_completed`/`downloading`，「下载」与审核入口会随之消失，反而锁死用户。

## 2026-09-30: API 作业在队列层失败后实例永久卡在 search_queued

### Bug: 业务对象回收靠 `task_key` 反查实例，而 task_key 被覆盖
- **根因**: `app/worker/recovery.py` 的 cnki 分支把 `row.task_key` 直接当 `instance_no` 用，但开放接口带 `idempotency_key` 时入队的 `task_key` 是 `api_<idempotency_key>`，查找必然落空并静默返回。
- **教训**: 反查业务对象应优先用 `params_json.instance_id` 这类**强标识**，`task_key` 是“队列去重键”而非“业务主键”，两者语义不同，不能混用。

## 2026-05-18: 下载步骤中无 URL 的已通过记录被静默跳过

### Bug: 下载工作线程过滤条件导致 4 条记录永久"未下载"
- **根因**: `app/worker/download_worker.py:47-53` 的 SQL 查询额外过滤了 `original_url IS NOT NULL AND original_url != ""`，导致已通过人工审核但无原始链接的记录被彻底忽略，不会创建任何 `DownloadResult` 记录，永远停留在"未下载"状态。
- **教训**: 下载工作线程应处理**所有** `is_passed=True` 的记录，无 URL 的情况应在业务逻辑层（`_process_sync` 循环内）标记为 `skipped`，而非在 SQL 层静默过滤。这样所有已通过记录都会有一条 `DownloadResult` 记录，状态可追溯。
- **改进了 3 处**: (1) 下载工作线程移除 SQL 层的 `original_url` 过滤，在循环内处理无 URL 情况（标记 skipped）; (2) API 统计增加 `skipped`/`pending` 计数; (3) 前端任务实例列表展示跳过的记录数。

## 2026-05-17: T20260517002 任务实例结果显示异常

### Bug 1: 前端调用错误 API 端点导致"暂无数据"
- **根因**: `src/api/task-results.ts:getTaskResults()` 请求 `GET /task-results`，而该端点是返回 `{"items": []}` 的桩代码。真实实现在 `GET /task-instances/{id}/results`。
- **教训**: 代码库中存在同名但语义不同的两个路由时，前端必须确认路由前缀匹配正确的后端 Router。`task-results` 路由注册到 `/api/v1/task-results` 但真正的列表接口在 `task-instances` 路由下。

### Bug 2: 变量名笔误导致 "This result object is closed"
- **根因**: `app/services/export_service.py:47` 中，查询 `TaskResult` 后将结果赋给 `result_rows`，但下一行误用了同函数前面已消耗的 `result` 变量（`TaskInstance` 查询的结果对象）。SQLAlchemy 对已消耗的 Result 对象再次调用 `.scalars()` 会抛出 `ResourceClosedError`。
- **教训**: 同一函数内多个查询时，必须使用不同的变量名，避免复用。Review 时应特别关注 SQLAlchemy Result 对象的变量名是否与查询对应。

### Bug 3: `handleSingleReject` 调用了 `markPass`
- **根因**: `src/pages/task-result/index.tsx:180` 调用 `markPass(row.id)` 而非 `markReject(row.id)`，导致点击"拒绝"实际执行了"通过"。
- **教训**: 复制粘贴条件/事件处理器时，必须确认调用的函数名与语义一致。

### Bug 4: `mark_pass` 和 `mark_reject` 前后端合约不一致
- **根因**: 后端 `mark_pass` 期望 `PassRequest` 请求体（含 `is_passed: bool`），但前端 `markPass()` 发送空 body。后端 `mark_reject` 使用 `not row.is_passed`（切换而非设置为 False）。
- **教训**: 前后端 API 合约必须在开发阶段就保持一致。PUT/PATCH 请求体字段应按需设默认值，保证可选性。

### Bug 5: `is_passed` 默认值不允许 `NULL`
- **根因**: `Column(Boolean, default=False)` 导致所有新记录 `is_passed=False`（"拒绝"状态），无法表示"待审核"（NULL）。
- **教训**: 三态布尔字段（通过/拒绝/待审核）必须用 `nullable=True`。`default=False` 不等同于 `NULL`，会影响过滤逻辑。

## 2026-05-17: LLM 分析并发写入 DB 失败

### Bug: `asyncio.gather` 共享同一个 `db` session 导致并发冲突
- **根因**: `app/worker/llm_worker.py` 中 `asyncio.gather` 并发调用多个 `_process_one`，但所有协程共享同一个 `db: AsyncSession`。SQLite + aiosqlite 不支持单连接并发操作，触发 `This session is provisioning a new connection; concurrent operations are not permitted`。
- **教训**: 同一个 `AsyncSession` 不能被多个协程同时使用（尤其是 SQLite 场景）。应将 DB 操作（串行）与 IO 密集型操作（并发）分离。
- **修复**: 将原 `_process_one` 拆分为 `_call_llm`（纯 LLM HTTP 调用，可并发）和 `_write_analysis_result`（DB 写入，在主循环中串行执行）。

## 2026-05-18: Excel 导入功能 — CNKI 的 .xls 并非真实 Excel

### 经验 1: CNKI 导出的 .xls 是 HTML 表格伪装
- **现象**: `pd.read_excel(engine="openpyxl")` 打开 CNKI 下载的 `.xls` 文件时失败
- **根因**: CNKI 导出功能生成的是 `<html>` 格式的表格文件，仅后缀名为 `.xls`，并非真实二进制 Excel
- **处理**: 先尝试 `openpyxl` 解析，失败后用 `pd.read_html()` 提取 HTML 中的 `<table>`
- **教训**: `excel_parser.py` 与 `interactor.py` 中各有独立但功能重复的 HTML 兜底逻辑，导入时应统一收敛到一处

### 经验 2: 文件格式抽象应放在解析层，而非路由层
- **重构**: 新增 `_read_raw_data()` 函数作为格式检测层，`_read_and_sanitize()` 不再关心文件格式
- **效果**: 后续扩展 `.csv` 等格式只需改 `_read_raw_data()` 一处，不涉及其余业务逻辑
- **教训**: 文件解析的入口点应抽象出"原始读取"与"结构化清洗"两层，避免路由/业务代码关心底层格式

## 2026-05-18: 下载遗留记录批量跳过 + 单条重试下载功能

### Bug: 下载工作线程过滤条件导致已通过记录静默跳过
- **根因**: `app/worker/download_worker.py:47-53` SQL 查询额外过滤了 `original_url IS NOT NULL`，已通过但无链接的记录被彻底忽略，`DownloadResult` 永远不创建，显示为"未下载"
- **修复**: 移除 SQL 层过滤，在业务循环内处理无 URL 情况，标记为 `skipped`

### Feature: 单条重试下载
- **需求**: task-result 页面，已通过人工审核但下载状态为"未下载"/"失败"/"跳过"的记录可逐条重试下载
- **设计**: 新增 `POST /{instance_id}/results/{result_id}/retry-download` 端点，同步执行单条 PDF 下载，创建/更新 `DownloadResult`，不修改实例状态
- **导出兼容**: 导出模块读取 `DownloadResult.pdf_path`，单条下载成功后导出时自动包含该 PDF 及 Excel 中 PDF 文件列路径
- **按钮**: 每条记录操作列新增"下载"按钮，与原有"PDF 下载"按钮并存：前者是单条重试（下载完成后可见），后者是批量发起（下载前可见）

### 经验 3: 前端 accept 属性与后端验证应保持同步
- **问题**: 前端 `accept=".xlsx"` 与后端 `endswith(".xlsx")` 均在两处维护
- **修复**: 扩展后缀时需同时更新前端 accept + 提示文字 + 后端验证
- **教训**: 文件类型白名单应优先考虑用后端验证作为唯一权威源，前端仅做辅助提示
