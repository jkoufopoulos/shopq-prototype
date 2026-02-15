"""Checkpoint persistence stub.

TODO: Implement durable digest checkpointing (e.g. to SQLite or GCS).
Currently a no-op so that reclaim.shared.pipeline can import without crashing.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from reclaim.observability.logging import get_logger

if TYPE_CHECKING:
    from reclaim.storage.models import Digest

logger = get_logger(__name__)


def checkpoint_digest(digest: Digest) -> None:
    """Persist a digest checkpoint. Currently a no-op stub."""
    logger.debug("checkpoint_digest called (no-op): %s items", len(digest.items))
