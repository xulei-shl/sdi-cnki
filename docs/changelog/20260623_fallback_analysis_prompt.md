# 开发变更记录
- **日期**: 2026-06-23
- **对应设计文档**: docs/design/fallback_analysis_prompt_20260623.md

## 1. 变更摘要

实现兜底分析提示词（Fallback Analysis Prompt）机制：当任务实例运行时未指定 `prompt_template_id`，自动加载 admin 在「系统提示词模板」页面标记为 `fallback_analysis` 类型的提示词，并动态拼接本次检索条件，构成完整分析提示词发送给 LLM。

## 2. 文件清单

### 后端
- `app/models/prompt_template.py`: 新增 `prompt_type` 字段（`general` | `fallback_analysis`）
- `alembic/versions/006_add_prompt_type.py`: 数据库迁移，添加 prompt_type 列+索引
- `app/routers/prompt_templates.py`: Schema 增加 prompt_type，CRUD 校验 fallback 唯一性
- `app/worker/llm_worker.py`:
  - `_load_prompt_template` 增加 fallback 查询逻辑
  - 新增 `_format_search_conditions` 格式化检索条件
  - `_build_messages` 移除硬编码默认提示词

### 前端
- `src/types/index.ts`: `PromptTemplate` 接口增加 `prompt_type`
- `src/pages/system/prompt-template/index.tsx`: 表格增加「类型」列，编辑对话框增加类型选择 Radio

## 3. 后续变更 (2026-06-23)
- `app/worker/llm_worker.py`: `_load_prompt_template` 增加 `{{search_conditions}}` 占位符替换逻辑，不存在占位符时仍回退至末尾追加
- `src/pages/system/prompt-template/index.tsx`: 兜底模板说明文案同步更新，告知用户可使用 `{{search_conditions}}` 占位符，并修复 JSX 花括号转义问题

## 4. 测试结果
- [x] Alembic migration 执行成功（005 → 006）
- [ ] 单元测试待补充
- [ ] 核心路径验证待补充
