"""PDF 文件名与题名匹配校验逻辑。"""

from __future__ import annotations

import re
from pathlib import Path


def normalize(s: str) -> str:
    s = re.sub(r'[^\u4e00-\u9fff\w]', '', s)
    return s.lower()


def is_match(title: str, pdf_path: str | Path | None) -> bool:
    if not pdf_path or not Path(pdf_path).exists():
        return False
    fname = Path(pdf_path).stem
    tnorm = normalize(title)
    fnorm = normalize(fname)
    if not tnorm or not fnorm:
        return True

    if tnorm == fnorm:
        return True
    if fnorm.startswith(tnorm):
        return True
    if tnorm.startswith(fnorm):
        return True

    if len(tnorm) >= 20 and len(fnorm) >= 20:
        common = sum(1 for a, b in zip(tnorm, fnorm) if a == b)
        if common / max(len(tnorm), len(fnorm)) >= 0.5:
            return True

    return False
