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

  # 普通检索多关键词（模拟 Worker：合并为一条专业检索式，1 次检索）
  python test_cnki_search.py --query 阅读 远读 细读 --max-export 10        # 多关键词自动走合并路径
  python test_cnki_search.py --basic-multi --query 阅读 远读 细读 --max-export 10
  python test_cnki_search.py --batch-basic-multi                           # run all basic-multi combos

  # 纯逻辑自测（无需浏览器）
  python test_cnki_search.py --self-test
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time

_TEST_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(_TEST_DIR))  # project root (app package)
sys.path.insert(0, _TEST_DIR)

from app.services.cnki.browser import CnkiBrowser
from app.services.cnki.interactor import CnkiInteractor
from app.services.cnki.professional_interactor import ProfessionalCnkiInteractor
from app.worker.cnki_worker import build_professional_search_params

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


def run_basic_professional_test(headless: bool, params: dict) -> dict:
    """Simulate the worker: basic mode -> single professional expression search.

    Mirrors _run_search_sync: all keywords are merged into query_group_a and
    executed ONCE via ProfessionalCnkiInteractor, so the export limit is not
    multiplied by the number of keywords.
    """
    print(f"\n{'='*70}")
    print(f"  [BASIC-MULTI] Params: {json.dumps(params, ensure_ascii=False)}")
    print(f"{'='*70}")
    start = time.time()

    pro_params = build_professional_search_params(params)
    assert pro_params is not None, "empty queries should yield no search"
    print(f"  Built professional params: {json.dumps(pro_params, ensure_ascii=False)}")

    with CnkiBrowser(headless=headless) as browser:
        interactor = ProfessionalCnkiInteractor(browser, output_dir=OUTPUT_DIR)
        result = interactor.execute_search(pro_params)

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


# 普通检索多关键词组合 —— 期望所有关键词合并为一条专业检索式执行（只检索 1 次）
BASIC_MULTI_COMBOS: list[dict] = [
    {"search_mode": "basic", "queries": ["阅读推广", "全民阅读", "数字阅读"], "max_export": 10},
    {"search_mode": "basic", "queries": ["新青年", "五四运动", "新文化运动"], "max_export": 10, "core_only": True},
    {"search_mode": "basic", "queries": ["人工智能", "机器学习", "深度学习"], "max_export": 10, "year_from": 2023, "year_to": 2025},
    {"search_mode": "basic", "queries": ["生成式AI", "AIGC", "大模型"], "max_export": 10, "date_range": "year"},
    {"search_mode": "basic", "queries": ["图书馆", "数字化"], "max_export": 10, "core_only": True, "year_from": 2024},
    {"search_mode": "basic", "queries": ["知识服务"], "max_export": 10, "synonym_extend": True},
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


def run_batch_basic_multi(headless: bool):
    passed = 0
    failed = 0
    for params in BASIC_MULTI_COMBOS:
        try:
            run_basic_professional_test(headless=headless, params=params)
            passed += 1
        except Exception as e:
            print(f"  FAIL  {json.dumps(params, ensure_ascii=False)}  error={e}")
            failed += 1
    print(f"\n{'='*70}")
    print(f"  Basic-multi batch complete: {passed} passed, {failed} failed")


def self_test_basic_to_professional_params() -> None:
    """Pure assertion tests for the basic->professional merge (no browser)."""
    # 1. worker param transformation: multiple keywords -> single group A expression
    pro = build_professional_search_params(
        {"search_mode": "basic", "queries": ["阅读", "远读", "细读"], "max_export": 100}
    )
    assert pro == {
        "search_mode": "professional",
        "query_group_a": ["阅读", "远读", "细读"],
        "query_group_b": [],
        "max_export": 100,
    }, pro

    # 2. legacy single 'query' key backward compat
    pro = build_professional_search_params({"query": "阅读", "max_export": 50})
    assert pro["search_mode"] == "professional"
    assert pro["query_group_a"] == ["阅读"]
    assert pro["query_group_b"] == []
    assert "query" not in pro and "queries" not in pro, pro

    # 3. no keywords -> None (search skipped, no_results)
    assert build_professional_search_params({"queries": [], "max_export": 10}) is None
    assert build_professional_search_params({"max_export": 10}) is None

    # 4. professional mode passes through unchanged, and input is never mutated
    orig = {"search_mode": "professional", "query_group_a": ["A"], "query_group_b": ["B"], "max_export": 10}
    pro = build_professional_search_params(orig)
    assert pro == orig
    assert orig == {"search_mode": "professional", "query_group_a": ["A"], "query_group_b": ["B"], "max_export": 10}

    # 5. merged expression format: SU=(k1 + k2 + ...) OR TKA=(k1 + k2 + ...)
    # `_build_professional_query` is stateless (never uses self), so skip the
    # browser-dependent constructor by creating an uninitialized instance.
    interactor = object.__new__(ProfessionalCnkiInteractor)
    expr = interactor._build_professional_query(group_a=["阅读", "远读", "细读"], group_b=[])
    assert expr == "SU=('阅读' + '远读' + '细读') OR TKA=('阅读' + '远读' + '细读')", expr
    single = interactor._build_professional_query(group_a=["阅读"], group_b=[])
    assert single == "SU=('阅读') OR TKA=('阅读')", single

    print("  OK  basic->professional param transformation & merged expression")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CNKI search test")
    parser.add_argument("--query", nargs="*", default=["新青年"],
                        help="Search keyword(s); multiple values are merged into one professional expression")
    parser.add_argument("--basic-multi", action="store_true",
                        help="Force the basic->professional merge path (default when multiple --query values given)")
    parser.add_argument("--self-test", action="store_true",
                        help="Run pure assertion tests (no browser) and exit")
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
    parser.add_argument("--batch-basic-multi", action="store_true",
                        help="Run all predefined basic-multi (merged professional) combos")
    args = parser.parse_args()

    headless = True
    if args.headed:
        headless = False
    if args.headless:
        headless = True

    if args.self_test:
        self_test_basic_to_professional_params()
        sys.exit(0)

    if args.batch:
        run_batch(headless=headless)
        sys.exit(0)

    if args.batch_professional:
        run_batch_professional(headless=headless)
        sys.exit(0)

    if args.batch_basic_multi:
        run_batch_basic_multi(headless=headless)
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

    # 普通检索多关键词：自动走 Worker 的“合并为一条专业检索式”路径
    if args.basic_multi or len(args.query) > 1:
        params: dict = {
            "search_mode": "basic",
            "queries": args.query,
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
        run_basic_professional_test(headless=headless, params=params)
        sys.exit(0)

    params: dict = {
        "query": args.query[0],
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
