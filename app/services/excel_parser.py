from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pandas as pd

CNKI_COLUMN_MAP: dict[str, str] = {
    "Title-题名": "title",
    "Author-作者": "authors",
    "Organ-单位": "organ",
    "Source-文献来源": "source_journal",
    "FirstDuty-第一责任人": "first_duty",
    "Keyword-关键词": "keywords",
    "Summary-摘要": "abstract",
    "PubTime-发表时间": "publish_time",
    "Fund-基金": "fund",
    "Year-年": "publish_year",
    "Volume-卷": "volume",
    "Period-期": "issue",
    "PageCount-页码": "pages",
    "CLC-中图分类号": "clc",
    "ISSN-国际标准刊号": "issn",
    "URL-网址": "original_url",
    "DOI-DOI": "doi",
}

REFERENCE_COLUMN = "参考格式"
HEADER_ROW_PREFIXES = ("SrcDatabase-", "Title-", "Author-")


def parse_excel_to_records(excel_path: str | Path) -> list[dict[str, Any]]:
    df = _read_and_sanitize(excel_path)
    records: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        record = {}
        for cn_col, field in CNKI_COLUMN_MAP.items():
            val = row.get(cn_col, "")
            if pd.isna(val):
                val = ""
            val = str(val).strip()
            if field in ("publish_year",):
                try:
                    val = int(float(val)) if val else None
                except (ValueError, TypeError):
                    val = None
            if field in ("authors", "keywords", "first_duty") and isinstance(val, str):
                val = _clean_separator(val)
            record[field] = val
        ref = row.get(REFERENCE_COLUMN, "")
        if pd.notna(ref):
            record["reference_format"] = str(ref).strip()
        records.append(record)
    return records


def _read_and_sanitize(excel_path: str | Path) -> pd.DataFrame:
    df = pd.read_excel(excel_path, engine="openpyxl", header=None).fillna("")
    current_headers: list[str] = _try_infer_headers(df)
    all_columns: list[str] = list(current_headers)
    rows: list[list[str]] = []
    for row_values in _iter_rows(df):
        if _is_empty(row_values):
            continue
        if _is_header_row(row_values):
            current_headers = [str(v).strip() for v in row_values]
            all_columns = _merge_columns(all_columns, current_headers)
            continue
        if not current_headers:
            continue
        rows.append(row_values)
    if not all_columns:
        return pd.DataFrame()
    result = pd.DataFrame(rows, columns=all_columns[: max(len(r) for r in rows)] if rows else all_columns)
    for col in all_columns:
        if col not in result.columns:
            result[col] = ""
    return result.fillna("")


def _try_infer_headers(df: pd.DataFrame) -> list[str]:
    candidates = [str(c).strip() for c in df.columns.tolist()]
    if all(c.isdigit() for c in candidates if c):
        return []
    return candidates


def _is_header_row(row: list[str]) -> bool:
    return any(cell.startswith(prefix) for cell in row if cell for prefix in HEADER_ROW_PREFIXES)


def _is_empty(row: list[str]) -> bool:
    return not any(str(v).strip() for v in row)


def _iter_rows(df: pd.DataFrame) -> list[list[str]]:
    rows = []
    for tup in df.itertuples(index=False, name=None):
        vals = [str(v).strip() if pd.notna(v) else "" for v in tup]
        while vals and not vals[-1]:
            vals.pop()
        rows.append(vals)
    return rows


def _merge_columns(existing: list[str], new: list[str]) -> list[str]:
    merged = list(existing)
    for h in new:
        h = str(h).strip()
        if h and h not in merged:
            merged.append(h)
    return merged


def _clean_separator(val: str) -> str:
    return re.sub(r"\s*[;,；，]\s*", "; ", val).strip("; ").strip()
