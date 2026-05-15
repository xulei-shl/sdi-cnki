from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.utils.logging import get_logger

logger = get_logger("llm_provider")

RETRY_DELAYS = [3, 6, 10]
MAX_RETRIES_PER_CONFIG = 3


async def call_llm_once(
    api_key: str,
    api_endpoint: str,
    model_name: str,
    messages: list[dict[str, str]],
    timeout: int = 60,
) -> str:
    url = f"{api_endpoint.rstrip('/')}/v1/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model_name, "messages": messages, "stream": False}

    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=payload, headers=headers)
        if resp.status_code != 200:
            raise Exception(f"HTTP {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
        if not content:
            raise Exception("Empty response from LLM")
        return content


async def call_llm_with_retry(
    configs: list[dict[str, Any]],
    messages: list[dict[str, str]],
) -> tuple[str, int, str]:
    """
    Call LLM with retry across multiple configs by priority.
    Returns: (raw_response, used_config_id, model_name)
    """
    errors: list[str] = []
    for config in configs:
        cfg_id = config["id"]
        for attempt in range(MAX_RETRIES_PER_CONFIG):
            try:
                if attempt > 0:
                    delay = RETRY_DELAYS[min(attempt, len(RETRY_DELAYS) - 1)]
                    await asyncio.sleep(delay)
                content = await call_llm_once(
                    api_key=config["api_key"],
                    api_endpoint=config["api_endpoint"],
                    model_name=config["model_name"],
                    messages=messages,
                )
                return content, cfg_id, config["model_name"]
            except Exception as e:
                error = str(e)[:200]
                logger.warning(
                    f"LLM attempt {attempt + 1}/{MAX_RETRIES_PER_CONFIG} "
                    f"failed for config {cfg_id}: {error}"
                )
                errors.append(error)
        logger.warning(f"Config {cfg_id} exhausted, trying next config")

    raise Exception(f"All configs exhausted. Errors: {'; '.join(errors)}")
