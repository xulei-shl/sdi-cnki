"""JEV（TypeSafe System One）相关性评分服务。

与 LLM 提示词判定（`app/services/llm_provider.py`）是两条独立链路：
- 端点形状不同：JEV 是 `POST /v1/systemone`，body 为 `state` + `questions`，
  不是 OpenAI 的 `messages`；故独立成模块而非塞进 chat/completions 客户端；
- 判定口径不同：JEV 返回**概率**（noul / score），由本模块按固定公式折算，
  阈值与档位描述写死在代码里，不随提示词漂移。

综合分口径与参考实现（`docs/jev-docs/我的每日文章jev相关性判断`）完全一致：
    relevance_score = round(noul_prob × (relevance_level / 4) × 100) / 100

本模块除「读取 JEV 配置」外均为纯逻辑，不依赖 DB 结构 / 队列 / 调度，
便于后续主流程（web）迁移时整段复用。
"""

from __future__ import annotations

import asyncio
import math
import random
from dataclasses import dataclass
from typing import Any

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.llm_config import LlmConfig
from app.utils.crypto import decrypt_api_key
from app.utils.logging import get_logger

logger = get_logger("jev_provider")

JEV_DEFAULT_API_URL = "https://api.typesafe.ai/v1/systemone"
JEV_DEFAULT_MODEL = "jev-latest"
JEV_CONFIG_TYPE = "jev"

# 单条候选送 JEV 的文本上限：控制 token 成本，同时收敛提示注入面
MAX_ITEM_CHARS = 800

# 0–4 五档描述。措辞与参考实现逐字一致，保证跨项目同一量表可比。
RELEVANCE_LEVELS = [
    "完全不相关，与用户主题无任何关联",
    "边缘相关，仅涉及相邻领域或间接关联",
    "中度相关，涉及用户主题的部分方面",
    "高度相关，直接讨论用户关注的核心主题",
    "完全匹配，深入讨论用户核心主题且包含关键词",
]
MAX_LEVEL = len(RELEVANCE_LEVELS) - 1

RELEVANCE_LEVEL_LABELS = ["完全不相关", "边缘相关", "中度相关", "高度相关", "完全匹配"]

# 单次请求超时（秒）与最大重试次数（总尝试 = retries + 1）
JEV_REQUEST_TIMEOUT_SEC = 30
JEV_MAX_RETRIES = 2

# 指数退避基准 / 单次上限
JEV_RETRY_BASE_DELAY_SEC = 1.0
JEV_RETRY_MAX_DELAY_SEC = 30.0

# 除 5xx 外额外可重试：429 限流 / 529 过载 / 408 超时
JEV_RETRYABLE_STATUS = frozenset({408, 429, 529})


class JevNotConfiguredError(Exception):
    """未配置可用的 JEV 配置（缺少密钥、配置停用或解密失败）。"""


@dataclass(frozen=True)
class ResolvedJevConfig:
    api_url: str
    api_key: str
    model: str


def normalize_jev_api_url(base_url: str) -> str:
    """把配置的 base_url 归一为 System One endpoint。

    管理员可能填 `https://api.typesafe.ai`（少写路径）、`.../v1` 或完整
    `.../v1/systemone`；这里统一补齐，避免调用时才 404。
    """
    trimmed = (base_url or "").strip().rstrip("/")
    if not trimmed:
        return JEV_DEFAULT_API_URL
    if trimmed.endswith("/systemone"):
        return trimmed
    if trimmed.endswith("/v1"):
        return f"{trimmed}/systemone"
    return f"{trimmed}/v1/systemone"


def _clamp(value: float, low: float, high: float) -> float:
    return min(high, max(low, value))


def calculate_relevance(noul: float, level: float) -> float:
    """noul 概率作为门控，档位作为程度，二者相乘并保留两位小数。"""
    normalized = _clamp(level, 0, MAX_LEVEL) / MAX_LEVEL
    return round(_clamp(noul, 0.0, 1.0) * normalized * 100) / 100


def level_label(level: float) -> str:
    idx = int(_clamp(round(level), 0, MAX_LEVEL))
    return RELEVANCE_LEVEL_LABELS[idx]


def build_candidate_text(title: str | None, keywords: str | None, abstract: str | None) -> str:
    """候选文本：题名 + 关键词 + 摘要，固定截断。"""
    parts = []
    if title:
        parts.append(f"题名：{title}")
    if keywords:
        parts.append(f"关键词：{keywords}")
    if abstract:
        parts.append(f"摘要：{abstract}")
    return " ".join(parts)[:MAX_ITEM_CHARS]


def build_jev_request(
    topic: str,
    items: list[dict[str, Any]],
    model: str = JEV_DEFAULT_MODEL,
) -> dict:
    """构建一次批量打分请求。

    采用「一批候选共享 state」的批量口径（同参考实现的精排模块）：50~100 篇若
    逐篇调用需要 50~100 次请求，按批只需 3~5 次。每篇问一对 noul+score，
    批级再问一个 choice 作为「本批是否至少有一条真正涉及该主题」的显式弃权信号。
    """
    results = [
        {"index": index, "content": item["text"]}
        for index, item in enumerate(items)
    ]
    state = {"request": topic, "results": results}

    questions: dict[str, Any] = {}
    for index in range(len(items)):
        questions[f"r{index}"] = {
            "type": "noul",
            "instructions": (
                f"根据 `request` 中的检索主题，判断 `results[{index}]` 这条文献是否与该主题相关。"
            ),
            "criteria": {
                "true": "文献直接研究或紧密关联用户所关注的主题",
                "false": "文献与用户所关注的主题无关，仅表面词汇相似但实质不同",
            },
        }
        questions[f"s{index}"] = {
            "type": "score",
            "instructions": f"评估 `results[{index}]` 这条文献与 `request` 检索主题的相关程度。",
            "criteria": RELEVANCE_LEVELS,
        }
    questions["has_match"] = {
        "type": "choice",
        "instructions": "`results` 中是否至少有一条文献真正涉及 `request` 的主题？",
        "criteria": {
            "yes": "至少有一条文献真正讨论用户查询的主题",
            "no": "所有文献都只共享词面或与查询主题无关",
        },
    }

    return {"state": state, "model": model, "questions": questions}


def _answer_number(answers: dict, question_id: str, answer_type: str, field: str) -> float | None:
    answer = answers.get(question_id)
    if not isinstance(answer, dict):
        return None
    if answer_type and answer.get("type") != answer_type:
        return None
    value = answer.get(field)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if math.isfinite(value) else None


def parse_jev_answers(
    answers: Any,
    items: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], bool | None]:
    """解析一批答案，逐条产出评分。

    严格校验：`noul` / `score` 任一缺失、类型不符或非有限数，该条**不产分**
    （调用方按「未评分」处理），绝不用 0 兜底——0 是「打了低分」，
    两者语义不同，混淆会直接误导下游筛选。
    """
    if not isinstance(answers, dict):
        return [], None

    scores: list[dict[str, Any]] = []
    for index, item in enumerate(items):
        noul = _answer_number(answers, f"r{index}", "noul", "noul")
        level = _answer_number(answers, f"s{index}", "score", "score")
        if noul is None or level is None:
            continue

        clamped_noul = _clamp(noul, 0.0, 1.0)
        clamped_level = _clamp(level, 0.0, float(MAX_LEVEL))
        confidence = _answer_number(answers, f"s{index}", "score", "confidence")
        scores.append(
            {
                "task_result_id": item["task_result_id"],
                "relevance_score": calculate_relevance(clamped_noul, clamped_level),
                "relevance_level": int(round(clamped_level)),
                "noul_prob": round(clamped_noul, 4),
                "level_confidence": round(confidence, 4) if confidence is not None else None,
            }
        )

    has_match: bool | None = None
    choice_answer = answers.get("has_match")
    if isinstance(choice_answer, dict) and choice_answer.get("type") == "choice":
        if choice_answer.get("choice") == "yes":
            has_match = True
        elif choice_answer.get("choice") == "no":
            has_match = False
    return scores, has_match


def _parse_retry_after_ms(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value) * 1000)
    except ValueError:
        return None


def _retry_delay_sec(attempt: int, retry_after_ms: float | None) -> float:
    """指数退避 + 抖动；上游给了 Retry-After 就听它的（仍受单次上限约束）。"""
    if retry_after_ms is not None:
        return min(retry_after_ms / 1000, JEV_RETRY_MAX_DELAY_SEC)
    backoff = min(JEV_RETRY_BASE_DELAY_SEC * (2 ** (attempt - 1)), JEV_RETRY_MAX_DELAY_SEC)
    return backoff + random.uniform(0, backoff * 0.25)


async def call_jev_api(body: dict, config: ResolvedJevConfig) -> dict:
    """调用 JEV，带超时与重试。

    JEV 在 429/529/5xx 时要求指数退避后重试，否则并发一高就会把限流记成失败。
    """
    last_error = "未知错误"
    for attempt in range(1, JEV_MAX_RETRIES + 2):
        retryable = True
        retry_after_ms: float | None = None
        try:
            async with httpx.AsyncClient(timeout=JEV_REQUEST_TIMEOUT_SEC) as client:
                response = await client.post(
                    config.api_url,
                    headers={
                        "Authorization": f"Bearer {config.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=body,
                )
            if response.status_code == 200:
                return response.json()
            detail = response.text[:200]
            last_error = f"JEV API 错误 {response.status_code}: {detail}"
            retryable = response.status_code >= 500 or response.status_code in JEV_RETRYABLE_STATUS
            retry_after_ms = _parse_retry_after_ms(response.headers.get("retry-after"))
        except httpx.TimeoutException:
            last_error = f"JEV 请求超时（{JEV_REQUEST_TIMEOUT_SEC}s）"
        except httpx.HTTPError as e:
            last_error = f"JEV 网络异常：{str(e)[:200]}"

        if not retryable or attempt > JEV_MAX_RETRIES:
            raise RuntimeError(last_error)
        delay = _retry_delay_sec(attempt, retry_after_ms)
        logger.warning(
            f"JEV 请求失败，{delay:.1f}s 后重试（{attempt}/{JEV_MAX_RETRIES}）: {last_error}"
        )
        await asyncio.sleep(delay)
    raise RuntimeError(last_error)


async def resolve_jev_config(db: AsyncSession) -> ResolvedJevConfig:
    """读取启用的 JEV 配置。

    取 id 最大的一条（后建的覆盖先建的），密钥解密失败视为未配置——宁可明确
    报「未配置」，也不要拿一个必然 401 的空密钥去打上游。
    """
    stmt = (
        select(LlmConfig)
        .where(LlmConfig.config_type == JEV_CONFIG_TYPE, LlmConfig.is_active == True)
        .order_by(LlmConfig.id.desc())
    )
    configs = (await db.execute(stmt)).scalars().all()
    for config in configs:
        if not config.api_key_encrypted:
            continue
        try:
            from app.config import get_settings

            api_key = decrypt_api_key(config.api_key_encrypted, get_settings().aes_encryption_key)
        except Exception as e:
            logger.error(f"JEV 配置 {config.id} 密钥解密失败：{e}")
            continue
        if api_key:
            return ResolvedJevConfig(
                api_url=normalize_jev_api_url(config.api_endpoint),
                api_key=api_key,
                model=config.model_name or JEV_DEFAULT_MODEL,
            )
    raise JevNotConfiguredError(
        "未配置 JEV。请在「大模型管理」中新建一条类型为 JEV 的配置并填入 TypeSafe API Key。"
    )