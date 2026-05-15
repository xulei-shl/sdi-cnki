"""Multi-strategy JSON parser for LLM responses."""

import json
import re


def parse_llm_json(raw_response: str) -> dict:
    """
    4-level strategy to parse LLM response as JSON.

    Returns parsed dict on success.
    Raises ValueError if all 4 strategies fail.
    """
    raw = raw_response.strip()

    # Strategy 1: Direct parse
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        pass

    # Strategy 2: Strip markdown code markers
    try:
        cleaned = re.sub(r"^```json\s*", "", raw, flags=re.MULTILINE)
        cleaned = re.sub(r"\s*```$", "", cleaned, flags=re.MULTILINE)
        cleaned = cleaned.strip()
        return json.loads(cleaned)
    except json.JSONDecodeError:
        pass

    # Strategy 3: Regex extract first complete JSON object
    try:
        match = re.search(r"\{.*\}", raw, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except json.JSONDecodeError:
        pass

    # Strategy 4: Try to fix common issues
    try:
        fixed = raw
        fixed = fixed.replace("'", '"')
        fixed = re.sub(r",\s*}", "}", fixed)
        fixed = re.sub(r",\s*]", "]", fixed)
        fixed = re.sub(r"(?<!\\)\\(?![\"\\/bfnrtu])", "", fixed)
        return json.loads(fixed)
    except json.JSONDecodeError:
        pass

    raise ValueError("JSON parsing failed after all 4 strategies")
