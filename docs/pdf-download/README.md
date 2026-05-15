# 学术论文 PDF 下载脚本

本项目包含两个用于从不同学术网站下载 PDF 文献的脚本：

- `scripts/wanfang_pdf_download.py`：从万方数据下载 PDF
- `scripts/zhesheke_pdf_download.py`：从哲社科下载 PDF

两个脚本功能相同，命令行参数也相同，仅调用的目标网站不同。

## 功能

- 使用 Camoufox 反检测技术（同步版）模拟浏览器行为
- 自动处理关键词中的特殊字符（如中文引号）
- 支持命令行参数输入关键词
- 自动创建保存目录并下载 PDF 文件

## 依赖

- Python 3.x
- camoufox
- keyword_processor（本项目提供）

## 安装依赖

```bash
pip install camoufox
```

keyword_processor 模块已包含在项目中，无需额外安装。

## 使用方法

### 万方 PDF 下载

```bash
python scripts/wanfang_pdf_download.py "您的检索关键词"
```

### 哲社科 PDF 下载

```bash
python scripts/zhesheke_pdf_download.py "您的检索关键词" [重试次数]
```

- 重试次数：可选参数，默认为 1 次，例如 `2` 表示最多重试 2 次

## 示例

```bash
python scripts/wanfang_pdf_download.py "AI4S背景下的知识创新服务应用模式、平台系统与微服务设计研究"
python scripts/zhesheke_pdf_download.py "五年后的图书馆：清华大学图书馆"十五五"努力方向" 2
```

## 输出

下载的 PDF 文件将保存到以下目录：

- 万方：`temps/scholar-pdf/wanfang/`
- 哲社科：`temps/scholar-pdf/zhesheke/`

---

*注：两个脚本的核心逻辑相同，仅目标网站和部分细节处理有所不同。具体的爬取逻辑请参考各脚本源码。*