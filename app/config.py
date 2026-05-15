from __future__ import annotations

import os
from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    app_name: str = "CNKI 学术定题服务系统"
    debug: bool = False

    database_url: str = "sqlite+aiosqlite:///./data/cnki_service.db"

    jwt_secret_key: str = "change-me-to-a-random-secret-key"
    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 7

    aes_encryption_key: str = "change-me-to-32-char-key!!!!!"

    cnki_username: str = ""
    cnki_password: str = ""

    worker_cnki_concurrency: int = 1
    worker_llm_concurrency: int = 5
    worker_download_concurrency: int = 1
    worker_export_concurrency: int = 2

    sse_heartbeat_interval: int = 15

    data_dir: str = str(Path(__file__).resolve().parent.parent / "data")

    @property
    def uploads_dir(self) -> str:
        return os.path.join(self.data_dir, "uploads")

    @property
    def downloads_dir(self) -> str:
        return os.path.join(self.data_dir, "downloads")

    @property
    def exports_dir(self) -> str:
        return os.path.join(self.data_dir, "exports")

    @property
    def cookies_dir(self) -> str:
        return os.path.join(self.data_dir, "cookies")

    @property
    def database_path(self) -> str:
        db_url = self.database_url
        if db_url.startswith("sqlite+aiosqlite:///"):
            path = db_url.replace("sqlite+aiosqlite:///", "")
            return os.path.join(os.path.dirname(os.path.dirname(__file__)), path)
        if db_url.startswith("sqlite:///"):
            path = db_url.replace("sqlite:///", "")
            return os.path.join(os.path.dirname(os.path.dirname(__file__)), path)
        return ""

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
