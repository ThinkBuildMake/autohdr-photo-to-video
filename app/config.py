"""Settings read from environment variables. Values are never logged."""

import os
from dataclasses import dataclass
from functools import lru_cache

CONFIG_VARIABLES = (
    "OPENROUTER_API_KEY",
    "OPENROUTER_BASE_URL",
    "VIDEO_MODEL",
    "VIDEO_MODEL_FALLBACK",
    "VIDEO_RESOLUTIONS",
    "ENHANCE_MODEL",
    "ENHANCE_MODEL_FALLBACK",
    "QUALITY_CHECK_MODEL",
    "PLANNER_MODEL",
    "BYOK_MODELS",
    "BUCKET_ENDPOINT",
    "BUCKET_NAME",
    "BUCKET_ACCESS_KEY_ID",
    "BUCKET_SECRET_ACCESS_KEY",
    "BUCKET_REGION",
    "DATABASE_PATH",
    "DEMO_PASSPHRASE",
    "FAKE_PROVIDERS",
    "CHECK_MAX_AI_SCORE",
    "CHECK_MIN_MATCH_SCORE",
    "CHECK_FRAMES_PER_SECOND",
    "LABEL_IMAGE_LONG_SIDE",
    "SHOTS_IN_FLIGHT",
    "PORT",
)


def _text(name: str, default: str = "") -> str:
    return os.environ.get(name, default)


def _int(name: str, default: int) -> int:
    raw = os.environ.get(name, "").strip()
    return int(raw) if raw else default


def _float(name: str, default: float) -> float:
    raw = os.environ.get(name, "").strip()
    return float(raw) if raw else default


def _flag(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


@dataclass(frozen=True)
class Settings:
    OPENROUTER_API_KEY: str
    OPENROUTER_BASE_URL: str
    VIDEO_MODEL: str
    VIDEO_MODEL_FALLBACK: str
    VIDEO_RESOLUTIONS: str
    ENHANCE_MODEL: str
    ENHANCE_MODEL_FALLBACK: str
    QUALITY_CHECK_MODEL: str
    PLANNER_MODEL: str
    BYOK_MODELS: str
    BUCKET_ENDPOINT: str
    BUCKET_NAME: str
    BUCKET_ACCESS_KEY_ID: str
    BUCKET_SECRET_ACCESS_KEY: str
    BUCKET_REGION: str
    DATABASE_PATH: str
    DEMO_PASSPHRASE: str
    FAKE_PROVIDERS: bool
    CHECK_MAX_AI_SCORE: float
    CHECK_MIN_MATCH_SCORE: float
    CHECK_FRAMES_PER_SECOND: int
    LABEL_IMAGE_LONG_SIDE: int
    SHOTS_IN_FLIGHT: int
    PORT: int

    def __repr__(self) -> str:
        return "Settings(...)"


def load_settings() -> Settings:
    return Settings(
        OPENROUTER_API_KEY=_text("OPENROUTER_API_KEY"),
        OPENROUTER_BASE_URL=_text("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
        VIDEO_MODEL=_text("VIDEO_MODEL", "google/veo-3.1"),
        VIDEO_MODEL_FALLBACK=_text("VIDEO_MODEL_FALLBACK", "bytedance/seedance-2.0"),
        VIDEO_RESOLUTIONS=_text(
            "VIDEO_RESOLUTIONS", "google/veo-3.1=1080p,bytedance/seedance-2.0=1080p"
        ),
        ENHANCE_MODEL=_text("ENHANCE_MODEL", "google/gemini-nano-banana-2.1"),
        ENHANCE_MODEL_FALLBACK=_text("ENHANCE_MODEL_FALLBACK", "google/gemini-3.1-flash-image"),
        QUALITY_CHECK_MODEL=_text("QUALITY_CHECK_MODEL", "google/gemini-3.8-flash"),
        PLANNER_MODEL=_text("PLANNER_MODEL", "anthropic/claude-sonnet-5.5"),
        BYOK_MODELS=_text("BYOK_MODELS", "google/veo-3.1"),
        BUCKET_ENDPOINT=_text("BUCKET_ENDPOINT", "https://t3.storageapi.dev"),
        BUCKET_NAME=_text("BUCKET_NAME"),
        BUCKET_ACCESS_KEY_ID=_text("BUCKET_ACCESS_KEY_ID"),
        BUCKET_SECRET_ACCESS_KEY=_text("BUCKET_SECRET_ACCESS_KEY"),
        BUCKET_REGION=_text("BUCKET_REGION", "auto"),
        DATABASE_PATH=_text("DATABASE_PATH", "./data/app.db") or "./data/app.db",
        DEMO_PASSPHRASE=_text("DEMO_PASSPHRASE"),
        FAKE_PROVIDERS=_flag("FAKE_PROVIDERS"),
        CHECK_MAX_AI_SCORE=_float("CHECK_MAX_AI_SCORE", 0.5),
        CHECK_MIN_MATCH_SCORE=_float("CHECK_MIN_MATCH_SCORE", 0.5),
        CHECK_FRAMES_PER_SECOND=_int("CHECK_FRAMES_PER_SECOND", 6),
        LABEL_IMAGE_LONG_SIDE=_int("LABEL_IMAGE_LONG_SIDE", 768),
        SHOTS_IN_FLIGHT=_int("SHOTS_IN_FLIGHT", 8),
        PORT=_int("PORT", 8000),
    )


@lru_cache
def get_settings() -> Settings:
    return load_settings()


def reset_settings() -> None:
    get_settings.cache_clear()
