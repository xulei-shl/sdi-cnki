"""CNKI advanced search test — parameterized CLI.

Usage:
  python test_cnki_search.py --query 新青年 --max-export 10
  python test_cnki_search.py --headed --core-only --query 新青年 --max-export 10
  python test_cnki_search.py --year-from 2024 --year-to 2025 --query 新青年 --max-export 20
  python test_cnki_search.py --date-range year --query 新青年 --max-export 10
  python test_cnki_search.py --synonym-extend --query 新青年 --max-export 10
  python test_cnki_search.py --query 新青年 --max-export 10 --year-from 2024       # only start year
  python test_cnki_search.py --query 新青年 --max-export 10 --year-to 2023         # only end year
  python test_cnki_search.py --batch                                        # run all combos
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


BATCH_COMBOS: list[dict] = [
    {"query": "新青年", "max_export": 10},
    {"query": "新青年", "max_export": 10, "core_only": True},
    {"query": "新青年", "max_export": 10, "year_from": 2024, "year_to": 2025},
    {"query": "新青年", "max_export": 10, "date_range": "year"},
    {"query": "新青年", "max_export": 10, "synonym_extend": True},
    {"query": "新青年", "max_export": 10, "year_from": 2024},
    {"query": "新青年", "max_export": 10, "year_to": 2023},
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
    parser.add_argument("--batch", action="store_true", help="Run all predefined parameter combinations")
    args = parser.parse_args()

    headless = True
    if args.headed:
        headless = False
    if args.headless:
        headless = True

    if args.batch:
        run_batch(headless=headless)
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
