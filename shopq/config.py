"""Centralized configuration for the Reclaim backend.

Re-exports everything from shopq.infrastructure.settings so existing imports
continue to work, then adds typed constants for database, pipeline, LLM,
rate-limiting, and API settings.  Environment variable overrides use safe
defaults so the app starts without extra env configuration.
"""

from __future__ import annotations

import os

from shopq.infrastructure.settings import *  # noqa: F401, F403  — re-export existing

# --- App ---
APP_VERSION: str = "1.0.0"

# --- Database ---
DB_POOL_SIZE: int = int(os.getenv("SHOPQ_DB_POOL_SIZE", "5"))
DB_POOL_TIMEOUT: float = float(os.getenv("SHOPQ_DB_POOL_TIMEOUT", "5.0"))
DB_CONNECT_TIMEOUT: float = float(os.getenv("SHOPQ_DB_CONNECT_TIMEOUT", "30.0"))
DB_TEMP_CONN_MAX: int = int(os.getenv("SHOPQ_DB_TEMP_CONN_MAX", "10"))
DB_RETRY_MAX: int = int(os.getenv("SHOPQ_DB_RETRY_MAX", "5"))
DB_RETRY_BASE_DELAY: float = float(os.getenv("SHOPQ_DB_RETRY_BASE_DELAY", "0.1"))
DB_RETRY_MAX_DELAY: float = float(os.getenv("SHOPQ_DB_RETRY_MAX_DELAY", "2.0"))
DB_RETRY_JITTER: float = float(os.getenv("SHOPQ_DB_RETRY_JITTER", "0.1"))

# --- Extraction Pipeline ---
PIPELINE_MIN_BODY_CHARS: int = 100
PIPELINE_BODY_TRUNCATION: int = 4000
PIPELINE_DATE_WINDOW_DAYS: int = 180
PIPELINE_DEFAULT_RETURN_DAYS: int = 30
PIPELINE_ORDER_NUM_MIN_LEN: int = 3
PIPELINE_ORDER_NUM_MAX_LEN: int = 40

# --- LLM ---
LLM_TIMEOUT_SECONDS: int = int(os.getenv("SHOPQ_LLM_TIMEOUT", "30"))
LLM_MAX_RETRIES: int = int(os.getenv("SHOPQ_LLM_MAX_RETRIES", "3"))
LLM_MAX_WORKERS: int = int(os.getenv("SHOPQ_LLM_MAX_WORKERS", "4"))

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
