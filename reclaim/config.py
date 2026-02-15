"""Centralized configuration for the Reclaim backend.

Re-exports everything from reclaim.infrastructure.settings so existing imports
continue to work, then adds typed constants for database, pipeline, LLM,
rate-limiting, and API settings.  Environment variable overrides use safe
defaults so the app starts without extra env configuration.

Env vars use RECLAIM_* as primary with SHOPQ_* fallback for backward compat.
"""

from __future__ import annotations

import os

from reclaim.infrastructure.settings import *  # noqa: F401, F403  — re-export existing


def _env(new_key: str, old_key: str, default: str) -> str:
    """Read env var with RECLAIM_* primary and SHOPQ_* fallback."""
    return os.getenv(new_key, os.getenv(old_key, default))


# --- App ---
APP_VERSION: str = "1.0.0"

# --- Extraction Pipeline ---
PIPELINE_MIN_BODY_CHARS: int = 100
PIPELINE_BODY_TRUNCATION: int = 4000
PIPELINE_DATE_WINDOW_DAYS: int = 180
PIPELINE_DEFAULT_RETURN_DAYS: int = 30
PIPELINE_ORDER_NUM_MIN_LEN: int = 3
PIPELINE_ORDER_NUM_MAX_LEN: int = 40

# --- LLM ---
LLM_TIMEOUT_SECONDS: int = int(_env("RECLAIM_LLM_TIMEOUT", "SHOPQ_LLM_TIMEOUT", "30"))
LLM_MAX_RETRIES: int = int(_env("RECLAIM_LLM_MAX_RETRIES", "SHOPQ_LLM_MAX_RETRIES", "3"))
LLM_MAX_WORKERS: int = int(_env("RECLAIM_LLM_MAX_WORKERS", "SHOPQ_LLM_MAX_WORKERS", "4"))

# --- Rate Limiting ---
RATE_LIMIT_RPM: int = 60
RATE_LIMIT_RPH: int = 1000
RATE_LIMIT_EMAILS_PM: int = 100
RATE_LIMIT_EMAILS_PH: int = 2000
RATE_LIMIT_MAX_IPS: int = 10000

# --- API ---
API_LIST_LIMIT_DEFAULT: int = 100
API_LIST_LIMIT_MAX: int = 500
API_BATCH_SIZE_MAX: int = 500
API_EXPIRING_THRESHOLD_DAYS: int = 7

# --- LLM Budget ---
LLM_USER_DAILY_LIMIT: int = 500
LLM_GLOBAL_DAILY_LIMIT: int = 10000

# --- Extension ---
CHROME_EXTENSION_ID: str = _env(
    "RECLAIM_CHROME_EXTENSION_ID", "SHOPQ_CHROME_EXTENSION_ID",
    "aagmmkcefeaaffcnfgdfhnfokhnajhbb",
)
CHROME_EXTENSION_ORIGIN: str = f"chrome-extension://{CHROME_EXTENSION_ID}"
