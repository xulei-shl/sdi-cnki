# PDF 多来源下载架构说明

## 下载优先级

单条文章依次尝试三个来源，任一成功即返回，全部失败标记 `skipped`：

```
1. 哲舍科 (ncpssd.org)       → 按题名搜索，点击"全文下载"
2. 万方 (wanfangdata.com.cn) → 按题名搜索，点击"下载"→新标签页→"点击此处"
3. CNKI (original_url)       → 导航原文详情页，点击"PDF下载"
```

失败的文章会再执行一轮完整的三来源重试。

## 文件结构

```
backend/app/services/
├── pdf_downloader.py              ← 统一调度入口
└── pdf_downloader_src/            ← 参考代码（原样复刻，仅改浏览器注入）
    ├── __init__.py
    ├── keyword_processor.py       ← 关键词清洗工具
    ├── zhesheke.py                ← 哲舍科下载（来自 docs/pdf-download/zhesheke_pdf_download.py）
    ├── wanfang.py                 ← 万方下载（来自 docs/pdf-download/wanfang_pdf_download.py）
    └── cnki.py                    ← CNKI下载（来自 docs/pdf-download/cnki_pdf_download.py）
    keyword_normalizer.py      ← PDF文件名与题名匹配校验（来自 docs/pdf-download/keyword_normalizer.py）

backend/app/worker/
└── download_worker.py             ← Worker 进程，批量调度 pdf_downloader
```

## 参考代码的改动

三份参考代码从 `docs/pdf-download/` 原样复制到 `pdf_downloader_src/`，**所有网页元素选择器、时序、后备策略完全保留**，仅做了以下无害修改：

| 改动 | 说明 |
|------|------|
| 函数签名加 `page=None` | 允许外部传入已打开的浏览器页面，避免每个来源都新建 Camoufox |
| 浏览器初始化条件化 | `page` 不为 None 时复用外部浏览器，否则自建 Camoufox |
| 退出清理 | 自建浏览器时关闭页面和浏览器；外部传入时不关闭 |
| `keyword_processor` 导入 | 改为相对导入 `from .keyword_processor` |
| `SESSION_DIR` | CNKI 会话目录改为使用项目配置的 `cookies_dir` |
| 默认输出目录 | 硬编码路径改为基于 `__file__` 计算 |
| `return` → `break` + `result_path` | 避免 return 跳过清理逻辑 |

## 调度逻辑 (`pdf_downloader.py`)

```python
def download_pdf(page, article_title, original_url, output_dir):
    # 1. 哲舍科 — 按题名搜索
    result = zhesheke_download(article_title, output_dir=..., page=page)
    if _validate(article_title, result): return result    # ← 校验文件名

    # 2. 万方 — 按题名搜索
    result = wanfang_download(article_title, output_dir=..., page=page)
    if _validate(article_title, result): return result    # ← 校验文件名

    # 3. CNKI — 导航原文链接
    result = cnki_download(article_title, output_dir=..., reuse_session=False, page=page)
    if _validate(article_title, result): return result    # ← 校验文件名

    return None
```

## 下载后校验

每个来源下载成功后，用 `keyword_normalizer.is_match()` 校验 PDF 文件名是否与题名匹配。校验策略：

| 策略 | 说明 |
|------|------|
| 完全匹配 | 标准化后题名 == 标准化后文件名 |
| 前端匹配 | 题名是文件名的前缀（来源附带了额外信息） |
| 截断匹配 | 文件名是题名的前缀（CNKI 文件名被截断） |
| 公共子串 | 长度 ≥ 20 时公共子串占比 ≥ 50%（中间截断差异） |
| 相似度 | 字符集合重合率 ≥ 阈值（仅 threshold>0 时启用） |

**不匹配时**：删除已下载的 PDF 文件，尝试下一个来源。

## Worker 重试机制 (`download_worker.py`)

```
round 1: 所有文章依次走 哲舍科 → 万方 → CNKI
                ↓
         记录所有 skipped 的文章
                ↓
round 2: skipped 的文章再走一轮完整的三来源（间隔 3 秒）
         round 2 成功 → 覆盖状态为 completed
         仍失败       → 保留 round 1 的 skipped
```

## 失败处理

| 场景 | `download_status` | `error_message` |
|------|-------------------|-----------------|
| 任一来源成功 | `completed` | — |
| 三轮全部失败 | `skipped` | `"All 3 sources failed (zhesheke/wanfang/cnki)"` |
| 异常 | `skipped` | `str(e)[:200]` |

重复数据（`is_duplicate = True`）和未审核数据（`is_passed = False`）不进入下载流程。
