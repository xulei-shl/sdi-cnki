from __future__ import annotations

import unicodedata
import re


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = re.sub(r"[\[\]【】{}《》「」『』()（）〔〕]", "", text)
    text = re.sub(r"[，、。．,\.:：;；！!？?·・…—～~‾̀̈&×\u00b7\u3000\s]+", "", text)
    text = text.lower()
    return text
