"""Storage - models and caching (database removed in stateless migration)"""

from __future__ import annotations


class BaseRepository:
    """Stub — database repositories removed in stateless migration."""

    def __init__(self, table_name: str) -> None:
        raise NotImplementedError(
            "BaseRepository requires a database, which was removed in the stateless migration. "
            "All data is now stored in chrome.storage.local on the client side."
        )


__all__ = ["BaseRepository"]
