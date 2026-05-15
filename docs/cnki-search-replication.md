# CNKI 爬虫模块复刻说明

> 本文档记录 `docs/` 下的参考代码（cnki-search、pdf-download）向 `backend/app/services/` 的复刻过程和关键信息，供后期检查和维护。

---

## 复刻总原则

| 模块 | 复刻方式 | 网页元素操作代码 |
|---|---|---|
| **CNKI 搜索** (`services/cnki/`) | **重构合并** | 所有 CSS 选择器、JS evaluate、重试/等待模式 100%匹配原型，但代码结构从 6 个 mixin 合并为 1 个类，依赖的外部 `src.utils.playwright_page` 函数在本地 `playwright_helpers.py` 中逐一定义 |
| **PDF 下载** (`services/pdf_downloader_src/`) | **原样复制** | 所有 `page.locator()`、`.click()`、`.fill()`、`.expect_download()` 等 DOM 操作完全来自参考代码，未改一行 |

**注意**：因 CNKI 搜索原型依赖 `src.utils.playwright_page` 等外部包（不在项目内），无法直接复制 .py 文件，只能逐函数还原。PDF 下载无外部依赖，可以原样复制。

---

## 1. 文件对照表

| 原型文件 (docs/cnki-search/scripts/) | 复刻目标 (backend/app/services/cnki/) | 复刻策略 |
|---|---|---|
| `browser.py` | `browser.py` | 直接移植，适配项目路径 |
| `exceptions.py` | `exceptions.py` | 直接移植，精简无用异常 |
| *缺失* | `playwright_helpers.py` | **新增**：复刻 `src.utils.playwright_page` 的 6 个核心辅助函数 |
| `cnki_form_ops.py` | `interactor.py` (`_fill_advanced_search_form` 及其依赖) | 合并为一个类 |
| `cnki_navigation_ops.py` | `interactor.py` (`_goto_next_results_page`, `_wait_for_results_changed` 等) | 合并 |
| `cnki_selection_ops.py` | `interactor.py` (`_select_batch`, `_select_rows_on_current_page` 等) | 合并 |
| `cnki_export_ops.py` | `interactor.py` (`_export_batch`, `_open_custom_export_page`, 个人登录) | 合并 |
| `cnki_page_ops.py` | `interactor.py` (`_wait_for_results_ready`, 对话框/验证码处理) | 合并 |
| `cnki_progress_ops.py` | *未复刻* | V1 暂不需要断点续跑，进度由 DB 状态管理 |
| `export_processor.py` | `services/excel_parser.py` | 独立文件，含分段表头清理 + 17 列映射 |
| `result_parser.py` | *未复刻* | V1 不需要实时解析结果页，走 Excel 导出解析路径 |
| `config.py` | `app/config.py` (Settings) | 项目已有配置类 |
| `cli.py` | `app/worker/cnki_worker.py` | Worker 入口 |
| `progress_store.py` | *未复刻* | V1 暂不需要 |

---

## 2. 原型依赖的外部模块复刻

原型大量调用 `src.utils.playwright_page`，这些函数在 `playwright_helpers.py` 中逐一定义：

| 函数 | 原型签名 | 文件位置 | 关键行为 |
|---|---|---|---|
| `click_first_available` | `(page, selectors, timeout_ms) -> bool` | `playwright_helpers.py:16` | 遍历选择器列表，点击第一个可见元素 |
| `disable_checkbox` | `(page, selector, logger, verify_unchecked)` | `playwright_helpers.py:52` | 取消勾选复选框，失败时 JS `evaluate` 兜底 |
| `enable_checkbox` | `(page, selector, logger)` | `playwright_helpers.py:87` | 勾选复选框，JS 兜底含 `input`/`change`/`click` 事件 |
| `first_visible_locator` | `(page, selectors, timeout_ms) -> Locator\|None` | `playwright_helpers.py:120` | 返回第一个可见元素的 Locator |
| `set_input_value` | `(locator, value)` | `playwright_helpers.py:138` | 设置输入框值，`fill()` 失败则回退 JS |
| `wait_for_any_selector` | `(page, selectors, timeout_seconds, poll_interval, wait_timeout_ms)` | `playwright_helpers.py:149` | 轮询直到任一选择器匹配可见元素 |
| `ensure_checkbox_checked` | `(page, checkbox, selector, action_timeout_ms)` | `playwright_helpers.py:172` | 稳定勾选复选框，`scroll_into_view` + `check(force)` + JS `evaluate` 三级兜底 |

---

## 3. 关键 CSS 选择器映射（运营变更时需同步）

### 3.1 高级检索表单

| 操作 | 选择器 | 所在方法 | 备注 |
|---|---|---|---|
| 取消英文扩展 | `input[data-id='EN'][name='onlyChecked']` | `_fill_advanced_search_form` |  |
| 勾选同义词扩展 | `input[data-id='TY'][name='onlyChecked']` | `_fill_advanced_search_form` |  |
| 添加条件行 | `#gradetxt a.add-group` → `.add-group` → `a.add-group` | `_ensure_advanced_condition_rows` | 三段降级 |
| 逻辑下拉选择 | `.sort.logical` 触发 → `.sort.logical .sort-list a[value='OR']` | `_set_advanced_condition` |  |
| 字段下拉选择 | `.sort.reopt` 触发 → `.sort.reopt .sort-list a[title='主题']` | `_set_advanced_condition` | 按 `title` 属性精确匹配 |
| 查询词输入 | `.input-box > input[type='text']` | `_set_advanced_condition` |  |
| 年份输入 | `input[placeholder='起始年']` / `input[placeholder='结束年']` | `_set_year_input_value` | **见下方 JS 段落** |
| 更新时间下拉 | `.tit-dropdown-box` → `.sort-default` → `.sort-list a` | `_set_date_range_dropdown` | 按文本过滤 |
| 仅看有全文 | `#onlyfulltext` | `_fill_advanced_search_form` | 取消勾选 = 包含无全文 |
| 核心来源 | `input[name='all']` 取消 → `input[key='...'][value='...']` 勾选 | `_fill_advanced_search_form` | 7 种核心需逐次勾选 |
| 提交检索 | `input.btn-search` → `div.search` → `.btn-search` | `_submit_search` | 三段降级 |

### 3.2 结果页

| 操作 | 选择器 | 所在方法 | 备注 |
|---|---|---|---|
| 等待就绪 | `.result-table-list tbody tr` 计数 > 0 | `_wait_for_results_ready` | 也检测 `#ModuleSearchResult .no-content` 和 `.pagerTitleCell` |
| 设每页条数 | `#perPageDiv .sort-default` → `#perPageDiv .sort-list li[data-val='50'] a` | `_set_results_per_page` |  |
| 翻页 | `#PageNext` → `#Page_next_top` → `a#Page_next_top` → `.pages a` | `_find_next_page_link` | 四段降级，`.pages a` 需过滤文本"下一页" |
| 当前页码 | `.countPageMark` | `_results_summary_page` |  |
| 总条数 | `.pagerTitleCell` | `_parse_summary` | 正则提取 `[\d,]+` |
| 全选 | `#selectCheckAll1` | `_select_rows_on_current_page` |  |
| 逐行勾选 | `.result-table-list tbody input.cbItem` | `_select_rows_on_current_page` | `nth(index)` 定位 |
| 清除选中 | `.checkcount a` 过滤 has_text="清除" | `_clear_selected_results` |  |
| 对话框关闭 | `.layui-layer-dialog` → `.layui-layer-btn0` | `_dismiss_dialog_if_present` |  |

### 3.3 导出

| 操作 | 选择器 | 所在方法 | 备注 |
|---|---|---|---|
| 打开导出菜单 | 文本匹配 `a:has-text("导出与分析")` → `a:has-text("导出文献")` | `_click_link_by_text` |  |
| 自定义导出 | `a[exporttype='selfDefine']` | `_open_custom_export_page` | 打开新页面 |
| 导出页就绪 | `.export-sidebar-a` / `#litoexcel` / `#litotxt` 等 | `wait_for_any_selector` | 7 个选择器轮询 |
| 全选导出项 | 文本匹配 `a:has-text("全选")` | `_click_link_by_text` |  |
| Excel 导出 | `#litoexcel` | `_export_batch` | 触发下载 |
| 切换 GB/T 格式 | `a[displaymode='GBTREFER']` → `li.current a[displaymode='GBTREFER']` | `_export_batch` |  |
| TXT 导出 | `#litotxt` | `_export_batch` | 触发下载 |
| 个人登录弹框检测 | `.ecp-account-login .ecp_userName` / `.ecp-passwordBox .ecp_passWord` / `button.ECP_UserLOgin` | `_is_personal_login_visible` |  |
| 个人登录填写 | `input.ecp_userName` / `input.ecp_passWord` / `#agreement` / `button.ECP_UserLOgin` | `_login_personal_account` |  |

### 3.4 验证码

| 操作 | 选择器/JS | 所在文件 | 备注 |
|---|---|---|---|
| 检测验证码 | `document.querySelector('#tcaptcha_transform_dy')` + `getBoundingClientRect()` | `browser.py` | 容器可见 + 宽高 > 0 |
| 等待用户处理 | 后台线程 + 轮询 | `browser.py` | 超时 120s，用户可按 Enter 确认 |

---

## 4. 关键 JS evaluate 代码段（运营变更时务必同步）

### 4.1 年份输入 (interactor.py)

```javascript
(element, inputValue) => {
    const normalizedValue = inputValue || '';
    element.removeAttribute('readonly');
    element.focus();
    element.value = normalizedValue;
    element.setAttribute('value', normalizedValue);
    element.setAttribute('txt', normalizedValue);
    element.setAttribute('condition', normalizedValue ? `(${normalizedValue})` : '');
    element.dispatchEvent(new Event('input', { bubbles: true }));
    element.dispatchEvent(new KeyboardEvent('keyup', { bubbles: true, key: '0' }));
    element.dispatchEvent(new Event('change', { bubbles: true }));
    element.dispatchEvent(new Event('blur', { bubbles: true }));
}
```

**说明**：CNKI 站点脚本依赖 `txt` 和 `condition` 属性读值，且必须按 `input` → `keyup` → `change` → `blur` 顺序触发。不可用 Playwright 的 `fill()` 替代。

### 4.2 复选框 JS 兜底 (playwright_helpers.py)

```javascript
// enable_checkbox 兜底
element.checked = true;
element.dispatchEvent(new Event('input', {bubbles: true}));
element.dispatchEvent(new Event('change', {bubbles: true}));
element.dispatchEvent(new Event('click', {bubbles: true}));

// disable_checkbox 兜底
element.checked = false;
element.dispatchEvent(new Event('change', {bubbles: true}));
```

### 4.3 翻页最后尝试 (interactor.py)

```javascript
// 最后一次重试时使用 JS 点击兜底
element.click()
```

---

## 5. 重试与超时参数

| 参数 | 值 | 用途 |
|---|---|---|
| `NEXT_PAGE_MAX_RETRIES` | 3 | 翻页重试次数 |
| `NEXT_PAGE_RETRY_DELAY` | 1s | 翻页重试间隔 |
| 翻页变化等待超时 | 90s | `_wait_for_results_changed` |
| 结果页就绪超时 | 60s | `_wait_for_results_ready` |
| 导出页就绪超时 | 90s | `wait_for_any_selector` |
| 文件下载超时 | 60s | `expect_download(timeout=60000)` |
| 验证码等待 | 120s | `browser.wait_for_captcha_completion` |
| 每页条数 | 50 | `_set_results_per_page` → 50 条/页（确保翻页稳定） |
| 导出批量 | 500 | `EXPORT_BATCH_SIZE` |

---

## 6. 参数约束（重要）

参考原型 `docs/cnki-search/README.md` 的参数定义，以下为 `search_params` 的约束：

| 参数 | search_params 字段 | 约束 |
|---|---|---|
| `--query` | `query` | 必填 |
| `-n` / `--max-export` / `--max-download` | `max_export` | **必填**；取值范围限定 `{50, 100, 150, 200, 250, 300, 350, 400, 450, 500}` |
| `--date-from` / `--date-to` | `year_from` / `year_to` | 与 `date_range` 互斥，不可同时传入 |
| `--date-range` | `date_range` | 可选值：`week` / `month` / `half-year` / `year` / `ytd` / `last-year`；与 `year_from`/`year_to` 互斥 |
| `--synonym-extend` | `synonym_extend` | 布尔值，默认 false |
| `--include-no-fulltext` | `include_no_fulltext` | 布尔值，默认 false（保留"仅看有全文"） |
| `--core` | `core_only` | 布尔值，默认 false（取消"全部期刊"，勾选 7 种核心来源） |

**校验位置**：
- 后端：`routers/meta_tasks.py` → `validate_search_params()` 函数，在 `MetaTaskCreate` / `MetaTaskUpdate` 的 `@model_validator` 中调用
- 前端：`src/views/meta-task/index.vue` → `max_export` 用 `<el-select>` 限定选项；`date_range` 与年份范围通过 `:disabled` + `computed` 互斥，存盘前清除冲突字段

---

## 7. 导出数据处理

CNKI 导出的原始 Excel 文件存在**分段表头**（不同文献类型使用不同字段集合），处理策略与原型一致：

1. 逐行扫描原始导出内容
2. 遇到包含 `SrcDatabase-`、`Title-`、`Author-` 的行视为新表头段
3. 后续数据按当前表头映射
4. 将所有字段做并集合并成统一主表
5. 引文 TXT 按编号 `[1]` `[2]` ... 解析后回填到 `参考格式` 列
6. 多批次最终合并为一个总 Excel

---

## 8. Worker 运行方式

```bash
# CNKI 检索 Worker（串行，concurrency=1）
cd backend && python worker_runner.py cnki 1

# PDF 下载 Worker（串行，concurrency=1）
cd backend && python worker_runner.py download 1

# LLM 分析 Worker（并行，concurrency=5）
cd backend && python worker_runner.py llm 5
```

CNKI Worker 与 Download Worker 均使用同步 Camoufox，通过 `asyncio.to_thread` / `loop.run_in_executor` 在后台线程池中运行，不阻塞主事件循环。

**注意**：
- `camoufox` 的 sync 版本会 reset asyncio event loop，已在 `browser.py:_reset_asyncio_loop()` 中处理
- 两个浏览器 Worker（cnki、download）共享相同的 Cookie 持久化文件 `data/cookies/cnki_cookies.json`
- 首次使用需先手动登录生成 Cookie，或配置 `.env` 中的 `CNKI_USERNAME` / `CNKI_PASSWORD`

---

## 9. 未复刻的功能（V1 设计上不需要）

以下为原型含有但 V1 阶段**明确不实现**的功能——不是因为遗漏，而是项目需求不包含：

### 9.1 CNKI 搜索原型（`docs/cnki-search/scripts/`）

| 未复刻 | 原因 |
|---|---|
| `cnki_progress_ops.py` 全部（进度存储/断点续跑） | V1 进度由 DB `task_instances.status` 管理，中间失败人工重试即可 |
| `cnki_public_ops.py` 全部（基础搜索/独立翻页/论文详情） | V1 只做"高级检索 → 导出"这一个端到端流程 |
| `result_parser.py` 全部（结果页/详情页 DOM 解析） | V1 不实时解析结果页，走"导出 Excel → 解析 Excel"路径 |
| `cnki_navigation_ops.py`: `_restore_results_position`, `_goto_results_page_by_link`, `_find_resume_target_page_link` | V1 不需要按精确页码跳转恢复，只处理顺序"下一页" |
| `cnki_selection_ops.py`: `_prepare_next_batch_cursor`, `_extract_selected_count` | 断点游标管理，V1 不需要 |
| `cnki_yearly_export_ops.py` 全部（逐年导出模式） | V1 不启动按年全量导出 |
| `cnki_yearly_progress_store.py` 全部 | 同上，逐年配套 |
| `progress_store.py` 全部 | 同上 |
| `config.py` | 项目已有 `app/config.py` 配置类 |
| `cli.py` / `__main__.py` | 项目通过 `worker_runner.py` 启动 |

### 9.2 PDF 下载原型（`docs/pdf-download/`）

未复刻文件的对比：

| 原型文件 | 复刻目标 | 说明 |
|---|---|---|
| `cnki_pdf_download.py` | `pdf_downloader_src/cnki.py` | ✅ 原样复制，元素操作 0 改动 |
| `wanfang_pdf_download.py` | `pdf_downloader_src/wanfang.py` | ✅ 原样复制，元素操作 0 改动 |
| `zhesheke_pdf_download.py` | `pdf_downloader_src/zhesheke.py` | ✅ 原样复制，元素操作 0 改动 |
| `keyword_processor.py` | `pdf_downloader_src/keyword_processor.py` | ✅ 原样复制 |
| `keyword_normalizer.py` | `services/keyword_normalizer.py` | PDF 文件名匹配校验，新写 |
| `README.md` | — | 说明文档，不需复刻 |

三份下载脚本的改动仅限封装层，网页元素操作代码零改动：

| 改动点 | 幅度 |
|---|---|
| 函数签名加 `page=None` 参数 | 非元素操作 |
| 浏览器初始化条件化（`own_browser` 标志判断） | 非元素操作 |
| `import camoufox` 移入 `if own_browser:` 块内 | 非元素操作 |
| 退出清理改为 `finally` 条件执行（外部传入的浏览器不关闭） | 非元素操作 |
| `return` → `break + result_path` 避免跳过 `finally` 清理 | 非元素操作 |
| 默认输出/会话目录改为项目配置路径 | 非元素操作 |
| `main()` 入口保留但项目不走 `__main__` | 非元素操作 |

---

*维护提示：CNKI 页面 DOM 可能随时变化。当爬虫失效时，请使用 `--headless=false` 启动 Worker（由 `CnkiBrowser` 的 headless 参数控制），配合 Playwright Inspector 检查实际 DOM，更新上述选择器映射表。*
