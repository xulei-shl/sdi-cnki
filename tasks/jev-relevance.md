# 开放接口 JEV 相关性判断（2026-10-01）

## 背景

开放接口 v1 原先只返回 CNKI 元数据，不含任何相关性判断。主流程（web）虽在检索后有一步 LLM 提示词判定，但：

- 提示词随模板漂移，判定口径不可控、不可复现；
- 结果格式无契约（`is_relevant` / `is_target_topic` 两个键名并存，前端只认后者）；
- API 调用方拿不到定题结论，无法直接用于初筛。

需求：API 支持相关性判断，**由参数决定是否执行，默认执行**；判定引擎不用提示词，改为新增 JEV（TypeSafe）逻辑；同时为后续主流程 web 迁移预留设计空间。

## 设计要点（已实施）

- **新增 `relevance` 参数**：`{"enabled": true, "topic": null}`，默认启用。`topic` 留空时由服务端从检索条件派生，与网页端提示词口径共用 `app/services/search_topic.py`。
- **JEV 判定**：`app/services/jev_provider.py`。批量口径（20 篇/批），每篇问 `noul`（二值门控）+ `score`（0–4 五档），折算 `relevance_score = round(noul × (档位/4) × 100)/100`，与参考实现（`docs/jev-docs`）逐字对齐。
- **新增 `jev` 队列**：`app/worker/jev_worker.py`，并发 3，独立于网页 `llm` 队列。
- **复用 `search_completed`**：不新增实例状态。检索完成后停在 `search_completed`（对外 `running`），评分 worker 收尾才置 `completed`，避免调用方提前看到 `succeeded`。
- **失败绝不阻断文献交付**（本次最重要的约束，用户明确要求）：
  - 未配置 JEV → `relevance.state=unavailable`，作业仍 `succeeded`；
  - 全部批次失败 → `state=failed`，作业仍 `succeeded`；
  - 部分失败 → `state=partial`；
  - 评分超时（1800s）→ 作业仍 `succeeded`；
  - `recovery.py` 的 `jev` 分支同样落到 `completed`（唯一刻意偏离统一口径处，已注明理由）。
- **两条失败路径收敛**：`reclaim_stale_running`（进程崩溃兜底）补调 `reconcile_failed_task`，否则评分进程重启后实例会永久卡在 `search_completed`。
- **未评分 = `null`，不是 0**，且不暴露失败布尔标志（防幻觉）。
- **数据层**：新增 `jev_scores` 表（不复用 `llm_analysis_results`——后者有 `unique` 约束且被网页端 `json_extract` 直接过滤）；`llm_configs` 加 `config_type` 区分 `llm` / `jev`。
- **结果接口增强**：`fields=core` 由 6 扩到 8 字段（加相关性分）；新增 `sort=relevance` 与 `min_relevance`。
- **在途配额覆盖评分阶段**：`_inflight_job_ids` 增查 `jev` 队列行。

## 已完成

- [x] `search_topic.py` / `progress.py` 两处抽取（消除重复定义）
- [x] `jev_provider.py` / `jev_worker.py` / `jev_score` 模型 / 迁移 010
- [x] `cnki_worker` 入队、`main.py` + `worker_runner.py` 注册、`recovery.py` 兜底
- [x] `crud.py` 的 `reclaim_stale_running` 补调 `reconcile_failed_task`（崩溃路径兜底）
- [x] `openapi_v1.py` 全部接口增强
- [x] `llm_configs` 路由 + 前端 `config_type`（管理员可创建 JEV 配置）
- [x] `tests/test_jev_scoring.py`（24 项）+ `test_openapi_v1.py` 更新
- [x] 文档 3.4 / 4.5 / 4.6 / 5.1 / 9 / 10 节 + changelog + lessons

## 验证结果

- 全量 `pytest`：**64 passed**。既有 3 failed / 1 error 与 `test_integration.py` 在改动前即失败，已用 `git stash` 反向确认。
- `npx tsc -b` 通过。`vite build` 因 `@tailwindcss/typography` 未安装失败（改动前既有问题）。
- 迁移 `upgrade` / 重复 `upgrade` / `downgrade` / 再 `upgrade` 均在真实库副本上逐步核对通过。
- **未验证**：无真实 TypeSafe 密钥，端到端未跑通。重试与 `Retry-After` 已用 mock 单测覆盖，真实限流行为待实测；文档中「评分典型增加 20~60 秒」为估算值，已在文档第 9 节标注。

## 待办

### P0 — 部署前

- [ ] 管理员在「大模型管理」新建一条**类型为 JEV** 的配置（端点 `https://api.typesafe.ai/v1/systemone`、模型 `jev-latest`、填 TypeSafe API Key），并点「测试连接」验证。
- [ ] 生产库执行 `alembic upgrade head`。
- [ ] `python -m compileall -f app` 后重启（20260929 changelog 记录过陈旧 `.pyc` 事故）。
- [ ] 用真实 Key 提交一次 50 条作业做端到端验证：核对 `counts.relevance`、抽样比分、`fields=core&limit=10` 响应体积仍 < 3KB。

### P1 — 主流程（web）迁移到 JEV

准备工作已就位（`jev_provider` 不依赖本项目表结构、`run_jev_scoring` 按 `source` 分支、`execution_params.relevance` 快照语义与 `prompt_template_id` 一致），但**尚未实施**：

- [ ] `MetaTask` 增加相关性开关与定题描述字段；
- [ ] `cnki_worker` 的 web 分支在入队 `llm_analysis` 的同时入队 `jev_scoring`；
- [ ] `src/pages/task-result/*` 展示相关性分（表格列 + 详情面板 + 筛选）；
- [ ] 导出列（`app/services/export_service.py`）补相关性字段；
- [ ] **并行跑一段时间，用同一批文献对比 LLM 与 JEV 的判定差异**，再决定切换时点与是否保留双链路。
- [ ] 切换时需处理既有 `is_relevant` / `is_target_topic` 双键名并存的历史包袱（前端只认后者）。

## 备注

`docs/api-agent友好升级/面向Agent友好的API设计与评估通用框架.md` 的 4 项原则在本次均已落地：字段裁剪（`fields=core` 含分）、消费双轨（`format=json_file` 含分）、语义纯净（剥离失败布尔标志）、懒生成（JSON 文件仍按需缓存）。