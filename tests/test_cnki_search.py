"""CNKI search test — parameterized CLI.

Usage:
  # 普通检索 (basic mode)
  python test_cnki_search.py --query 新青年 --max-export 10
  python test_cnki_search.py --headed --core-only --query 新青年 --max-export 10
  python test_cnki_search.py --year-from 2024 --year-to 2025 --query 新青年 --max-export 20
  python test_cnki_search.py --date-range year --query 新青年 --max-export 10
  python test_cnki_search.py --synonym-extend --query 新青年 --max-export 10
  python test_cnki_search.py --query 新青年 --max-export 10 --year-from 2024       # only start year
  python test_cnki_search.py --query 新青年 --max-export 10 --year-to 2023         # only end year
  python test_cnki_search.py --batch                                        # run all basic combos

  # 专业检索 (professional mode)
  python test_cnki_search.py --professional --group-a '阅读推广' --group-b 'AI' --max-export 10
  python test_cnki_search.py --professional --group-a 阅读推广 全民阅读 --group-b AI LLM 大模型 --max-export 10
  python test_cnki_search.py --batch-professional                            # run all pro combos
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.services.cnki.browser import CnkiBrowser
from app.services.cnki.interactor import CnkiInteractor
from app.services.cnki.professional_interactor import ProfessionalCnkiInteractor

OUTPUT_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "data", "exports", "test_search",
)


def run_test(headless: bool, params: dict) -> dict:
    print(f"\n{'='*70}")
    print(f"  Params: {json.dumps(params, ensure_ascii=False)}")
    print(f"{'='*70}")
    start = time.time()

    with CnkiBrowser(headless=headless) as browser:
        interactor = CnkiInteractor(browser, output_dir=OUTPUT_DIR)
        result = interactor.execute_search(params)

    elapsed = time.time() - start
    print(f"  OK  exported={result['exported']}  total={result['total']}  "
          f"file={os.path.basename(result['final_file'])}  elapsed={elapsed:.0f}s")
    return result


def run_professional_test(headless: bool, params: dict) -> dict:
    print(f"\n{'='*70}")
    print(f"  [PROFESSIONAL] Params: {json.dumps(params, ensure_ascii=False)}")
    print(f"{'='*70}")
    start = time.time()

    with CnkiBrowser(headless=headless) as browser:
        interactor = ProfessionalCnkiInteractor(browser, output_dir=OUTPUT_DIR)
        result = interactor.execute_search(params)

    elapsed = time.time() - start
    print(f"  OK  exported={result['exported']}  total={result['total']}  "
          f"file={os.path.basename(result['final_file'])}  elapsed={elapsed:.0f}s")
    return result


BATCH_COMBOS: list[dict] = [
    {"query": "新青年", "max_export": 10},
    {"query": "新青年", "max_export": 10, "core_only": True},
    {"query": "新青年", "max_export": 10, "year_from": 2024, "year_to": 2025},
    {"query": "新青年", "max_export": 10, "date_range": "year"},
    {"query": "新青年", "max_export": 10, "synonym_extend": True},
    {"query": "新青年", "max_export": 10, "year_from": 2024},
    {"query": "新青年", "max_export": 10, "year_to": 2023},
]


PROFESSIONAL_COMBOS: list[dict] = [
    {"search_mode": "professional", "query_group_a": ["阅读推广", "全民阅读"], "query_group_b": ["AI", "大模型"], "max_export": 10},
    {"search_mode": "professional", "query_group_a": ["新青年", "五四运动"], "query_group_b": ["人工智能", "数字化"], "max_export": 10, "core_only": True},
    {"search_mode": "professional", "query_group_a": ["生成式AI", "AIGC"], "query_group_b": ["出版", "图书馆"], "max_export": 10, "year_from": 2023, "year_to": 2025},
    {"search_mode": "professional", "query_group_a": ["阅读服务", "智慧阅读"], "query_group_b": ["LLM", "多模态"], "max_export": 10, "synonym_extend": True},
    {"search_mode": "professional", "query_group_a": ["科技期刊", "学术期刊"], "query_group_b": ["开放获取", "OA"], "max_export": 10, "date_range": "year"},
    {"search_mode": "professional", "query_group_a": ["知识服务"], "query_group_b": ["AI", "大语言模型"], "max_export": 10, "core_only": True, "year_from": 2024},
    {"search_mode": "professional", "query_group_a": ["数字经济"], "max_export": 10},
    {"search_mode": "professional", "query_group_b": ["数字化转型"], "max_export": 10},
    {"search_mode": "professional", "query_group_a": ["人工智能", "机器学习"], "max_export": 10, "synonym_extend": True},
    {"search_mode": "professional", "query_group_b": ["出版融合", "媒体融合"], "max_export": 10, "core_only": True},
    {"search_mode": "professional", "query_group_a": ["阅读推广"], "query_group_b": ["AI"], "au_group": ["刘慈欣", "王晋康"], "max_export": 10},
    {"search_mode": "professional", "query_group_a": ["数字经济"], "au_group": ["张教授"], "max_export": 10},
    {"search_mode": "professional", "query_group_a": ["阅读推广"], "fu_group": ["国家社科基金", "教育部人文社科"], "max_export": 10},
    {"search_mode": "professional", "query_group_a": ["图书馆"], "query_group_b": ["数字化"], "au_group": ["刘教授"], "fu_group": ["国家自然科学基金"], "max_export": 10},
    {"search_mode": "professional", "fu_group": ["国家社科基金"], "max_export": 10},
    {"search_mode": "professional", "au_group": ["刘慈欣"], "fu_group": ["国家出版基金"], "max_export": 10},
]


def run_batch(headless: bool):
    passed = 0
    failed = 0
    for params in BATCH_COMBOS:
        try:
            run_test(headless=headless, params=params)
            passed += 1
        except Exception as e:
            print(f"  FAIL  {json.dumps(params, ensure_ascii=False)}  error={e}")
            failed += 1
    print(f"\n{'='*70}")
    print(f"  Batch complete: {passed} passed, {failed} failed")


def run_batch_professional(headless: bool):
    passed = 0
    failed = 0
    for params in PROFESSIONAL_COMBOS:
        try:
            run_professional_test(headless=headless, params=params)
            passed += 1
        except Exception as e:
            print(f"  FAIL  {json.dumps(params, ensure_ascii=False)}  error={e}")
            failed += 1
    print(f"\n{'='*70}")
    print(f"  Professional batch complete: {passed} passed, {failed} failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CNKI search test")
    parser.add_argument("--query", default="新青年", help="Search query")
    parser.add_argument("--max-export", type=int, default=10, help="Max records to export")
    parser.add_argument("--headed", action="store_true", help="Run with visible browser")
    parser.add_argument("--headless", action="store_true", help="Force headless mode")
    parser.add_argument("--core-only", action="store_true", help="Core journals only")
    parser.add_argument("--synonym-extend", action="store_true", help="Synonym extension")
    parser.add_argument("--include-no-fulltext", action="store_true", help="Include records without full text")
    parser.add_argument("--year-from", type=int, help="Start year (e.g. 2024)")
    parser.add_argument("--year-to", type=int, help="End year (e.g. 2025)")
    parser.add_argument("--date-range", choices=["week", "month", "half-year", "year", "ytd", "last-year"],
                        help="Update time range (mutually exclusive with year-from/year-to)")
    parser.add_argument("--professional", action="store_true", help="Professional search mode")
    parser.add_argument("--group-a", nargs="*", default=[], help="Group A keywords (professional mode)")
    parser.add_argument("--group-b", nargs="*", default=[], help="Group B keywords (professional mode)")
    parser.add_argument("--group-au", nargs="*", default=[], help="Author names (professional mode, optional)")
    parser.add_argument("--group-fu", nargs="*", default=[], help="Fund names (professional mode, optional)")
    parser.add_argument("--batch", action="store_true", help="Run all predefined basic combos")
    parser.add_argument("--batch-professional", action="store_true", help="Run all predefined professional combos")
    args = parser.parse_args()

    headless = True
    if args.headed:
        headless = False
    if args.headless:
        headless = True

    if args.batch:
        run_batch(headless=headless)
        sys.exit(0)

    if args.batch_professional:
        run_batch_professional(headless=headless)
        sys.exit(0)

    if args.professional:
        if not args.group_a and not args.group_b:
            parser.error("专业检索需要 --group-a 和/或 --group-b")
        params: dict = {
            "search_mode": "professional",
            "query_group_a": args.group_a,
            "query_group_b": args.group_b,
            "max_export": args.max_export,
            "core_only": args.core_only,
            "synonym_extend": args.synonym_extend,
            "include_no_fulltext": args.include_no_fulltext,
        }
        if args.group_au:
            params["au_group"] = args.group_au
        if args.group_fu:
            params["fu_group"] = args.group_fu
        if args.date_range:
            params["date_range"] = args.date_range
        if args.year_from is not None:
            params["year_from"] = args.year_from
        if args.year_to is not None:
            params["year_to"] = args.year_to
        run_professional_test(headless=headless, params=params)
        sys.exit(0)

    params: dict = {
        "query": args.query,
        "max_export": args.max_export,
        "core_only": args.core_only,
        "synonym_extend": args.synonym_extend,
        "include_no_fulltext": args.include_no_fulltext,
    }
    if args.date_range:
        params["date_range"] = args.date_range
    if args.year_from is not None:
        params["year_from"] = args.year_from
    if args.year_to is not None:
        params["year_to"] = args.year_to

    run_test(headless=headless, params=params)
