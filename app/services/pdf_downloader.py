"""PDF 下载统一调度入口。

按优先级依次尝试哲舍科 → 万方 → CNKI，每步校验文件名是否匹配。
"""

from __future__ import annotations

import time
from pathlib import Path

from .pdf_downloader_src.zhesheke import zhesheke_download
from .pdf_downloader_src.wanfang import wanfang_download
from .pdf_downloader_src.cnki import cnki_download
from .keyword_normalizer import is_match


def download_pdf(
    article_title: str,
    original_url: str,
    output_dir: str | Path,
    page=None,
    max_retries_round2: int = 1,
) -> str | None:
    """三来源依次尝试下载，成功校验后返回路径。

    Args:
        article_title: 文章题名（用于搜索和校验）
        original_url: CNKI 原文链接（CNKI 来源时直接导航）
        output_dir: PDF 保存目录
        page: 外部浏览器页面（None 时自建）
        max_retries_round2: 第二轮重试次数

    Returns:
        PDF 路径，全部失败返回 None
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    out_str = str(output_dir)

    skipped: list[tuple[str, str]] = []

    # ── Round 1: 依次尝试三个来源 ──
    for source_name, download_func, kwargs in [
        ("zhesheke", zhesheke_download, {"keyword": article_title, "output_dir": out_str, "page": page}),
        ("wanfang", wanfang_download, {"keyword": article_title, "output_dir": out_str, "page": page}),
        ("cnki", cnki_download, {"keyword": article_title, "output_dir": out_str, "page": page, "reuse_session": True}),
    ]:
        print(f"\n{'='*50}")
        print(f"[{source_name}] 尝试下载: {article_title[:50]}...")
        try:
            result = download_func(**kwargs)
            if result and result != "CAPTCHA_TIMEOUT":
                if is_match(article_title, result):
                    print(f"[{source_name}] ✅ 文件名匹配: {Path(result).name}")
                    return result
                else:
                    print(f"[{source_name}] ⚠️ 文件名不匹配，删除: {Path(result).name}")
                    Path(result).unlink(missing_ok=True)
            elif result == "CAPTCHA_TIMEOUT":
                skipped.append((source_name, "CAPTCHA_TIMEOUT"))
                continue
        except Exception as e:
            print(f"[{source_name}] ❌ 异常: {e}")
            skipped.append((source_name, str(e)[:100]))
            continue

    # ── Round 2: 重试 skipped 的来源 ──
    if skipped and max_retries_round2 > 0:
        print(f"\n{'='*50}")
        print(f"[Round 2] 重试 {len(skipped)} 个来源...")
        time.sleep(3)
        for source_name, _ in skipped:
            print(f"\n[Round 2/{source_name}] 重试...")
            kwargs_map = {
                "zhesheke": {"keyword": article_title, "output_dir": out_str, "page": page},
                "wanfang": {"keyword": article_title, "output_dir": out_str, "page": page},
                "cnki": {"keyword": article_title, "output_dir": out_str, "page": page, "reuse_session": True},
            }
            func_map = {
                "zhesheke": zhesheke_download,
                "wanfang": wanfang_download,
                "cnki": cnki_download,
            }
            try:
                result = func_map[source_name](**kwargs_map[source_name])
                if result and result != "CAPTCHA_TIMEOUT" and is_match(article_title, result):
                    print(f"[Round 2/{source_name}] ✅ 成功")
                    return result
            except Exception:
                pass

    print(f"\n{'='*50}")
    print(f"[PDF] ❌ 三来源全部失败: {article_title[:50]}...")
    return None
