from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mailq.observability.logging import get_logger

logger = get_logger(__name__)


class BridgeShadowLogger:
    """Writes bridge vs pattern comparisons to logs/bridge_mode/*.jsonl."""

    def __init__(self, log_dir: Path | str = "logs/bridge_mode"):
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)

    def log(self, session_id: str, payload: dict[str, Any]) -> None:
        path = self.log_dir / f"{session_id}.jsonl"
        try:
            with path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(payload, ensure_ascii=False) + "\n")
        except Exception as exc:
            logger.error("Failed to write bridge shadow log %s: %s", path, exc)
