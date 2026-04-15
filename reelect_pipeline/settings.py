from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from config import load_env


@dataclass(frozen=True)
class PipelineSettings:
    instagram_username: str
    max_workers: int
    llm_base_url: str
    llm_model: str
    llm_api_key: str
    llm_concurrency: int
    llm_native_video: bool
    llm_thinking_budget: int
    llm_max_tokens_visual: int
    llm_max_tokens_metadata: int
    cron_schedule: str
    lang: str


def load_pipeline_settings(env_path: str | Path = ".env") -> PipelineSettings:
    data = load_env(str(env_path))
    return PipelineSettings(
        instagram_username=data.get("INSTAGRAM_USERNAME", ""),
        max_workers=int(data.get("MAX_WORKERS", "3")),
        llm_base_url=data.get("LLM_BASE_URL", ""),
        llm_model=data.get("LLM_MODEL", ""),
        llm_api_key=data.get("LLM_API_KEY", ""),
        llm_concurrency=int(data.get("LLM_CONCURRENCY", "1")),
        llm_native_video=data.get("LLM_NATIVE_VIDEO", "false").lower() == "true",
        llm_thinking_budget=int(data.get("LLM_THINKING_BUDGET", "512")),
        llm_max_tokens_visual=int(data.get("LLM_MAX_TOKENS_VISUAL", "4096")),
        llm_max_tokens_metadata=int(data.get("LLM_MAX_TOKENS_METADATA", "8192")),
        cron_schedule=data.get("CRON_SCHEDULE", "0 * * * *"),
        lang=data.get("LANG", "en"),
    )

