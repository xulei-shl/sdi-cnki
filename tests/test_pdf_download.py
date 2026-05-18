"""PDF 下载测试 — 多来源优先级调度。

按优先级依次测试哲舍科 → 万方 → CNKI 的 PDF 下载能力。

Usage:
  python test_pdf_download.py --title 新青年
  python test_pdf_download.py --headed --title 新青年 --max-retries 0
  python test_pdf_download.py --title 新青年 --source cnki
  python test_pdf_download.py --batch
  python test_pdf_download.py --batch --headed --json results.json
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.pdf_downloader import download_pdf
from app.services.pdf_downloader_src.zhesheke import zhesheke_download
from app.services.pdf_downloader_src.wanfang import wanfang_download
from app.services.pdf_downloader_src.cnki import cnki_download
from app.services.keyword_normalizer import is_match

OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "data", "pdfs", "test_download",
)

SOURCE_NAMES = {"zhesheke", "wanfang", "cnki"}


def run_single_source(
    source_name: str,
    title: str,
    output_dir: str,
    max_retries: int,
    page=None,
) -> dict:
    func_map = {
        "zhesheke": zhesheke_download,
        "wanfang": wanfang_download,
        "cnki": cnki_download,
    }
    kw_map = {
        "zhesheke": {"keyword": title, "output_dir": output_dir, "page": page},
        "wanfang": {"keyword": title, "output_dir": output_dir, "page": page},
        "cnki": {"keyword": title, "output_dir": output_dir, "page": page, "reuse_session": True},
    }
    if source_name == "zhesheke":
        kw_map["zhesheke"]["max_retries"] = max_retries

    print(f"\n  [{source_name}] 单独下载...")
    start = time.time()
    try:
        result = func_map[source_name](**kw_map[source_name])
    except Exception as e:
        result = None
        print(f"  [{source_name}] ❌ 异常: {e}")
    elapsed = time.time() - start

    matched = False
    if result and result != "CAPTCHA_TIMEOUT":
        matched = is_match(title, result)

    status = "✅" if (result and result != "CAPTCHA_TIMEOUT" and matched) else \
             "⚠️" if result == "CAPTCHA_TIMEOUT" else "❌"
    print(f"  [{source_name}] {status} result={result}  matched={matched}  elapsed={elapsed:.0f}s")

    return {
        "source": source_name,
        "title": title,
        "result": str(result) if result else None,
        "matched": matched,
        "elapsed": round(elapsed),
        "status": "ok" if (result and result != "CAPTCHA_TIMEOUT" and matched) else
                  "captcha" if result == "CAPTCHA_TIMEOUT" else "fail",
    }


def run_orchestrated(
    title: str,
    output_dir: str,
    max_retries: int,
    page=None,
) -> dict:
    print(f"\n{'='*70}")
    print(f"  Orchestrated download: {title[:60]}")
    print(f"{'='*70}")
    start = time.time()

    pdf_path = download_pdf(
        article_title=title,
        output_dir=output_dir,
        page=page,
        max_retries_round2=max_retries,
    )

    elapsed = time.time() - start
    status = "✅" if pdf_path else "❌"
    print(f"  {status} elapsed={elapsed:.0f}s  pdf={pdf_path}")

    return {
        "mode": "orchestrated",
        "title": title,
        "result": str(pdf_path) if pdf_path else None,
        "elapsed": round(elapsed),
        "status": "ok" if pdf_path else "fail",
    }


def run_test(
    title: str,
    output_dir: str,
    max_retries: int,
    sources: list[str] | None = None,
    page=None,
) -> list[dict]:
    os.makedirs(output_dir, exist_ok=True)
    results = []

    if sources:
        for src in sources:
            r = run_single_source(src, title, output_dir, max_retries, page)
            results.append(r)
    else:
        r = run_orchestrated(title, output_dir, max_retries, page)
        results.append(r)

    return results


BATCH_TITLES = [
    "新青年",
    "人工智能赋能教育",
    "数字经济与高质量发展",
    "乡村振兴战略研究",
]


def run_batch(
    headless: bool,
    output_dir: str,
    max_retries: int,
    sources: list[str] | None = None,
) -> list[dict]:
    all_results = []
    passed = 0
    failed = 0
    for title in BATCH_TITLES:
        try:
            results = run_test(
                title=title,
                output_dir=output_dir,
                max_retries=max_retries,
                sources=sources,
            )
            all_results.extend(results)
            if any(r["status"] == "ok" for r in results):
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"\n  FAIL  title={title}  error={e}")
            failed += 1
    print(f"\n{'='*70}")
    print(f"  Batch complete: {passed} passed, {failed} failed")
    return all_results


def summarize(results: list[dict]):
    if not results:
        return
    print(f"\n{'='*70}")
    print(f"  Summary ({len(results)} runs)")
    print(f"{'='*70}")
    for r in results:
        icon = {"ok": "✅", "captcha": "⚠️", "fail": "❌"}.get(r["status"], "❓")
        label = r.get("source", r.get("mode", "?"))
        print(f"  {icon} [{label}] {r['title'][:50]:50s}  "
              f"{r['elapsed']:4d}s  {r.get('result','')[:60] or '-'}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="PDF download test")
    parser.add_argument("--title", default="基于虚拟仪器可过程监控反馈的油料化验实验系统构建", help="Article title to search")
    parser.add_argument("--source", action="append", choices=list(SOURCE_NAMES),
                        help="Specific source(s) to test (repeatable, default: orchestrated)")
    parser.add_argument("--headed", action="store_true", help="Show browser")
    parser.add_argument("--headless", action="store_true", help="Force headless mode")
    parser.add_argument("--output-dir", default=OUTPUT_DIR, help="PDF output directory")
    parser.add_argument("--max-retries", type=int, default=1,
                        help="Round 2 / zhesheke max retries (default: 1)")
    parser.add_argument("--json", help="Save results to JSON file")
    parser.add_argument("--batch", action="store_true", help="Run all predefined titles")
    args = parser.parse_args()

    headless = True
    if args.headed:
        headless = False
    if args.headless:
        headless = True

    if args.batch:
        results = run_batch(
            headless=headless,
            output_dir=args.output_dir,
            max_retries=args.max_retries,
            sources=args.source,
        )
    else:
        results = run_test(
            title=args.title,
            output_dir=args.output_dir,
            max_retries=args.max_retries,
            sources=args.source,
        )

    summarize(results)

    if args.json:
        os.makedirs(os.path.dirname(args.json) or ".", exist_ok=True)
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)
        print(f"\n  Results saved to {args.json}")
