# 经验教训

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
