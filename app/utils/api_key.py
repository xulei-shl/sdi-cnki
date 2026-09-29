from __future__ import annotations

import secrets

import bcrypt

API_KEY_PREFIX = "sk-"
# 明文前缀长度：用于按前缀定位候选行，再逐个做 bcrypt 校验
PREFIX_LENGTH = 12


def generate_api_key() -> tuple[str, str, str]:
    """生成 API Key，返回 (明文, 前缀, 哈希)。明文仅此一次可获取。"""
    raw = API_KEY_PREFIX + secrets.token_urlsafe(32)
    return raw, raw[:PREFIX_LENGTH], hash_api_key(raw)


def hash_api_key(raw: str) -> str:
    return bcrypt.hashpw(raw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_api_key(raw: str, key_hash: str) -> bool:
    try:
        return bcrypt.checkpw(raw.encode("utf-8"), key_hash.encode("utf-8"))
    except ValueError:
        return False
