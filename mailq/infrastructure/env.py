"""
Centralized environment variable loader for MailQ.

All scripts MUST import and call ensure_env_loaded() before accessing env vars.

Side Effects:
    - Loads .env file from project root
    - Validates required environment variables
    - Fails fast with clear error messages

Usage:
    from mailq.infrastructure.env import ensure_env_loaded, get_required_env

    ensure_env_loaded()
    api_key = get_required_env("ANTHROPIC_API_KEY")
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

_ENV_LOADED = False


def ensure_env_loaded(env_path: Path | None = None) -> None:
    """
    Ensure .env file is loaded exactly once.

    Args:
        env_path: Optional path to .env file. If None, searches for project root.

    Side Effects:
        - Loads environment variables from .env file
        - Sets module-level flag to prevent double-loading

    Raises:
        FileNotFoundError: If .env file not found and required vars missing
    """
    global _ENV_LOADED
    if _ENV_LOADED:
        return

    if env_path is None:
        # Find project root (contains .env)
        current = Path(__file__).parent
        while current != current.parent:
            env_candidate = current / ".env"
            if env_candidate.exists():
                env_path = env_candidate
                break
            current = current.parent

    if env_path and env_path.exists():
        load_dotenv(env_path)
        _ENV_LOADED = True
    else:
        # Try loading from current directory as fallback
        load_dotenv()
        _ENV_LOADED = True


def get_required_env(key: str, error_msg: str | None = None) -> str:
    """
    Get required environment variable or fail with clear error.

    Args:
        key: Environment variable name
        error_msg: Optional custom error message

    Returns:
        Environment variable value

    Raises:
        SystemExit: If environment variable not set
    """
    ensure_env_loaded()
    value = os.getenv(key)
    if not value:
        if error_msg:
            print(f"❌ {error_msg}", file=sys.stderr)
        else:
            print(f"❌ {key} not found in environment", file=sys.stderr)
            print("   1. Ensure .env file exists in project root", file=sys.stderr)
            print("   2. Copy .env.example to .env if needed", file=sys.stderr)
            print(f"   3. Add {key} to .env file", file=sys.stderr)
            print("   4. NEVER use 'export' commands with real API keys", file=sys.stderr)
        sys.exit(1)
    return value


def get_optional_env(key: str, default: str = "") -> str:
    """
    Get optional environment variable with default value.

    Args:
        key: Environment variable name
        default: Default value if not set

    Returns:
        Environment variable value or default
    """
    ensure_env_loaded()
    return os.getenv(key, default)
