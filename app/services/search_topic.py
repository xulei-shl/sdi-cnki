"""检索条件 → 定题描述文本。

LLM 分析（提示词尾部注入）与 JEV 相关性评分（`user_topics` / `request` 维度）
必须看到**同一份**定题描述，否则两条判定链路的口径会漂移，因此共用本模块。

本模块为纯函数，不依赖 DB / 队列 / LLM，可独立测试。
"""

from __future__ import annotations

import json

DATE_RANGE_LABELS = {
    "week": "最近一周",
    "month": "最近一个月",
    "half-year": "最近半年",
    "year": "最近一年",
    "ytd": "今年以来",
    "last-year": "去年全年",
}


def normalize_search_params(search_params: dict | str | None) -> dict:
    """把 execution_params 里的 search_params 规整成 dict（可能是 JSON 字符串）。"""
    if not search_params:
        return {}
    if isinstance(search_params, str):
        try:
            search_params = json.loads(search_params)
        except ValueError:
            return {}
    return search_params if isinstance(search_params, dict) else {}


def format_search_conditions(search_params: dict | str | None) -> str:
    """把检索条件渲染为中文定题描述；无有效条件时返回兜底文案。"""
    params = normalize_search_params(search_params)
    parts: list[str] = []
    search_mode = params.get("search_mode", "basic")

    if search_mode == "professional":
        group_a = params.get("query_group_a") or []
        group_b = params.get("query_group_b") or []
        if group_a and group_b:
            parts.append(f"主题A关键词组：{'、'.join(group_a)}")
            parts.append(f"主题B关键词组：{'、'.join(group_b)}")
        elif group_a:
            parts.append(f"主题关键词组：{'、'.join(group_a)}")
        elif group_b:
            parts.append(f"主题关键词组：{'、'.join(group_b)}")
        au = params.get("au_group") or []
        if au:
            parts.append(f"作者：{'、'.join(au)}")
        fu = params.get("fu_group") or []
        if fu:
            parts.append(f"基金：{'、'.join(fu)}")
    else:
        queries = params.get("queries") or []
        if queries:
            parts.append(f"检索关键词：{'、'.join(queries)}")

    year_from = params.get("year_from")
    year_to = params.get("year_to")
    if year_from and year_to:
        parts.append(f"出版年份：{year_from}—{year_to}")
    elif year_from:
        parts.append(f"出版年份：{year_from}年起")
    elif year_to:
        parts.append(f"出版年份：{year_to}年止")

    date_range = params.get("date_range")
    if date_range:
        parts.append(f"更新时间：{DATE_RANGE_LABELS.get(date_range, date_range)}")

    if params.get("core_only"):
        parts.append("来源范围：仅核心期刊")

    if not parts:
        return "未指定检索条件"

    return "\n".join(parts)