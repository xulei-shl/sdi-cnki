"""CNKI 专业检索式构造纯函数：worker 执行与开放接口回显共用同一口径。

不依赖浏览器/DB，可单测。任何一方改动检索式生成逻辑，另一方自动保持一致，
避免「实际执行的检索式」与「接口回显的检索式」漂移。
"""

from __future__ import annotations


def extract_queries(params: dict) -> list[str]:
    """从 search_params 提取关键词列表（兼容 queries 数组与旧 query 单值）。"""
    queries = params.get("queries")
    if queries and isinstance(queries, list):
        return [q.strip() for q in queries if q.strip()]
    single = params.get("query")
    if single and isinstance(single, str) and single.strip():
        return [single.strip()]
    return []


def build_professional_search_params(params: dict) -> dict | None:
    """将任意检索参数归一化为单次专业检索执行参数；无关键词时返回 None。

    Basic 模式把所有关键词合并为 group A（SU=(k1 + k2 + ...) OR TKA=(k1 + k2 + ...)），
    单次执行，使导出上限（max_export）被严格尊重。professional 模式原样返回。
    """
    pro_params = dict(params)
    if pro_params.get("search_mode") == "professional":
        return pro_params
    queries = extract_queries(pro_params)
    if not queries:
        return None
    pro_params["search_mode"] = "professional"
    pro_params["query_group_a"] = queries
    pro_params["query_group_b"] = []
    pro_params.pop("queries", None)
    pro_params.pop("query", None)
    return pro_params


def build_professional_query(
    group_a: list[str],
    group_b: list[str],
    au_group: list[str] | None = None,
    fu_group: list[str] | None = None,
) -> str | None:
    """构造填入 CNKI 专业检索输入框的布尔表达式；无任何分组时返回 None。"""
    def _quote(kw: str) -> str:
        kw = kw.replace("'", "\\'")
        return f"'{kw}'"

    base = None
    if group_a or group_b:
        a_expr = " + ".join(_quote(kw) for kw in group_a)
        b_expr = " + ".join(_quote(kw) for kw in group_b)
        if group_a and group_b:
            base = (
                f"(SU=({a_expr}) AND SU=({b_expr}))"
                f" OR "
                f"(TKA=({a_expr}) AND TKA=({b_expr}))"
            )
        else:
            expr = a_expr if group_a else b_expr
            base = f"SU=({expr}) OR TKA=({expr})"

    if au_group:
        au_expr = " + ".join(_quote(au) for au in au_group)
        if base:
            base = f"({base}) AND AU=({au_expr})"
        else:
            base = f"AU=({au_expr})"

    if fu_group:
        fu_expr = " + ".join(_quote(fu) for fu in fu_group)
        if base:
            base = f"({base}) AND FU % ({fu_expr})"
        else:
            base = f"FU % ({fu_expr})"

    return base
