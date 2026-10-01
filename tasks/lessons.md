# 经验教训

## 2026-10-01: 可选增值环节失败，不得丢弃已产出的业务成果

### Bug: 超时回收只改队列行，不回退业务对象，实例永久悬在中间态
- **现象**: `jev` 评分期间 worker 进程崩溃/重启，队列行被 `reclaim_stale_running` 标记为 `failed`，但实例仍停在 `search_completed`（对外映射 `running`），调用方永远轮询不到终态。
- **根因**: `reconcile_failed_task` 只在 `BaseWorker._process_wrapper` 的**执行中抛错**路径上被调用；而 `reclaim_stale_running`（进程崩溃/重启的兜底路径）只改队列行，不碰业务对象。两条失败路径没有收敛到同一处。
- **教训**: 业务对象的中间态回收**必须覆盖所有失败路径**，不能只挂在异常捕获上。凡是新增队列类型或新的兜底回收机制，都要检查「非正常退出」这条路是否同样能回到终态。
- **附带**: 该缺陷对 `cnki` / `llm` 队列同样存在（它们的中间态也只由异常路径回收），修复一并生效。
- **验证方式**: `tests/test_jev_scoring.py::test_reclaim_stale_jev_row_also_finalizes_instance` 钉死该不变量；先写测试复现（实例停在 `search_completed`），修复后通过。

### Bug: alembic 在一次 upgrade 内缓存 Inspector，导致索引被静默跳过
- **现象**: 010 迁移跑完后，`jev_scores` 的两个索引建好了，但 `task_instances.relevance_status` 与 `llm_configs.config_type` 的索引**没有建**，且迁移**不报任何错**。
- **根因**: alembic 在一次 `upgrade` 中缓存了 `Inspector`。索引存在性判断复用缓存的 `get_indexes()`，拿到的是 `add_column` **之前**的结果，于是「索引不存在」被误判为「已存在」而跳过。
- **教训**: 缺索引属于**静默失败**——开发期数据量小看不出来，只在数据量上来后显现为慢查询，因此格外危险。迁移中的存在性判断（`_create_index_if_missing` 一类）必须**每次重新取 inspector**，不能复用变量；且索引创建不能放在「建表」分支内，否则表已由 `create_all` 建好时会连带跳过既有表上新加列的索引。
- **验证方式**: 在真实库副本上跑 `upgrade` → 检查 `PRAGMA index_list` → 重复 `upgrade`（幂等）→ `downgrade` → 再 `upgrade`，逐步核对。

### 约定: 检索成功后的增值环节（JEV 评分）失败，作业仍为 succeeded
- **背景**: 开放接口在 CNKI 检索入库后新增 JEV 相关性判断，**默认执行**。若沿用 recovery 的「API 作业失败一律回收到 `failed`」口径，一次 JEV 故障（未配置 / 限流 / 模型异常）会让调用方**既拿不到文献也拿不到分数**，把一次成功且不可再生的 CNKI 检索彻底丢弃。
- **规则**: 跑在「已有业务成果产出之后」的环节，其失败只能降级自身状态，**不得改变作业终态**。`app/worker/recovery.py` 的 `_reconcile_jev` 是该模块唯一刻意偏离统一口径的分支，代码中已注明理由。判断依据是「失败时业务对象是否已有产出」——`cnki`/`llm` 失败时没有，`jev` 失败时有。
- **配套**: 「没打上分」与「打了低分」必须可区分。未评分一律 `relevance_score=null`（**不是 0**），且**不返回 `relevance_failed` 之类布尔标志**——那类内部状态字段会诱发大模型误判为「文献质量低劣」或「整体执行失败」（见 `docs/api-agent友好升级/skills_api_evaluation_report.md` §2.3）。失败只在 `relevance.state` / `relevance.error` / `counts.relevance.failed` 三处汇总呈现。

### 约定: 「先判终态再排队」的顺序不能反
- **规则**: 检索完成后**不能**立刻置 `completed` 再入队评分任务。否则调用方会在评分仍在跑时就看到 `succeeded`，取到一批 `relevance_score=null` 的记录。正确做法是停在 `search_completed`（对外已映射为 `running`），由评分 worker 收尾时才置终态。
- **同源教训**: 2026-09-30「重跑分析把已完成实例打回审核中」是同一类问题的镜像——终态判定不能由多处各自赋值。两者都指向：**实例状态的推进点必须唯一**。

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
