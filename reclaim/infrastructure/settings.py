"""

from __future__ import annotations

Application-wide settings and environment configuration
"""

import os
from pathlib import Path

# Project paths
PROJECT_ROOT = Path(__file__).parent.parent.parent
RECLAIM_ROOT = Path(__file__).parent.parent

# Environment (RECLAIM_ENV with SHOPQ_ENV fallback)
ENV = os.getenv("RECLAIM_ENV", os.getenv("SHOPQ_ENV", "development"))
DEBUG = ENV == "development"

# API Configuration
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")


# Google Cloud / Gemini
GOOGLE_CLOUD_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT", "shopq-467118")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-001")  # Vertex AI model
GEMINI_LOCATION = os.getenv("GEMINI_LOCATION", "us-central1")
GEMINI_MAX_TOKENS = int(os.getenv("GEMINI_MAX_TOKENS", "1024"))
GEMINI_TEMPERATURE = float(os.getenv("GEMINI_TEMPERATURE", "1.0"))

# OpenAI (optional)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Feature Flags
USE_RULES_ENGINE = os.getenv("USE_RULES_ENGINE", "true").lower() == "true"
USE_AI_CLASSIFIER = os.getenv("USE_AI_CLASSIFIER", "true").lower() == "true"
AUTO_LABEL = os.getenv("AUTO_LABEL", "false").lower() == "true"

# Classification Settings (matches extension config.js)
MAX_EMAILS_PER_BATCH = 50
BATCH_SIZE = 50
CLASSIFICATION_TIMEOUT = 30

# Cost Tracking (matches extension config.js)
DAILY_SPEND_CAP_USD = 0.50

# Cost per tier (matches extension config.js)
TIER_COSTS = {
    "T0": 0.0,  # Rules (free)
    "T1": 0.0,  # Local model (free)
    "T2_LITE": 0.0001,  # Gemini Flash
    "T3": 0.001,  # Full model
}

# Cache Settings (matches extension config.js)
CACHE_EXPIRY_HOURS = 24
CACHE_EXPIRY_MS = 24 * 60 * 60 * 1000  # 24 hours in milliseconds
CACHE_MAX_ENTRIES = 10000

# Logging
LOG_FILE = RECLAIM_ROOT / "logs" / "reclaim.log"

# Model Version (matches extension config.js)
MODEL_VERSION = "v2025-10-05"

# API URL (matches extension config.js)
RECLAIM_API_URL = "https://reclaim-api-142227390702.us-central1.run.app"


def is_production() -> bool:
    """Check if running in production"""
    return ENV == "production"


def is_development() -> bool:
    """Check if running in development"""
    return ENV == "development"


def get_env(key: str, default: str | None = None) -> str | None:
    """Get environment variable with fallback"""
    return os.getenv(key, default)
