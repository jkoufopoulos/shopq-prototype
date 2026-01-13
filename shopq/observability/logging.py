from __future__ import annotations

import logging
import os
from typing import Final

_HANDLER_ATTACHED: bool = False
_FORMAT: Final[str] = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def _resolve_level() -> int:
    level_name = os.getenv("SHOPQ_LOG_LEVEL", "INFO").upper()
    return getattr(logging, level_name, logging.INFO)


def get_logger(name: str) -> logging.Logger:
    """Return a module logger configured with a single stream handler."""
    global _HANDLER_ATTACHED

    level = _resolve_level()

    if not _HANDLER_ATTACHED:
        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(_FORMAT, datefmt="%Y-%m-%d %H:%M:%S"))
        root = logging.getLogger()
        root.addHandler(handler)
        root.setLevel(level)
        _HANDLER_ATTACHED = True
    else:
        logging.getLogger().setLevel(level)

    logger = logging.getLogger(name)
    logger.setLevel(level)
    return logger
