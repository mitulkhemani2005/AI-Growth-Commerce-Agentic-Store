from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()  # 从项目根目录 .env 文件加载环境变量


def _get_database_url_sync() -> Optional[str]:
    val = os.getenv("DATABASE_URL_SYNC", "").strip()
    return val if val else None


@dataclass(frozen=True)
class Settings:
    # ---------- 数据库 ----------
    database_url_sync: Optional[str] = field(default_factory=_get_database_url_sync)

    # ---------- Ollama 本地模型 ----------
    ollama_api_base: str = os.getenv("OLLAMA_API_BASE", os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).strip()

    # ---------- LLM API Keys (可选) ----------
    gemini_api_key: str = os.getenv("GEMINI_API_KEY", "").strip()
    anthropic_api_key: str = os.getenv("ANTHROPIC_API_KEY", "").strip()
    openai_api_key: str = os.getenv("OPENAI_API_KEY", "").strip()
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "").strip()
    dashscope_api_key: str = os.getenv("DASHSCOPE_API_KEY", "").strip()

    # ---------- 默认模型 ----------
    default_llm_model: str = os.getenv("DEFAULT_LLM_MODEL", "ollama/qwen2.5:7b").strip()

    @property
    def has_any_llm_key(self) -> bool:
        """是否配置了可用的 LLM (包括本地 Ollama 或云端 API Key)。"""
        return bool(
            self.ollama_api_base
            or self.default_llm_model
            or self.gemini_api_key
            or self.anthropic_api_key
            or self.openai_api_key
            or self.deepseek_api_key
            or self.dashscope_api_key
        )


settings = Settings()

