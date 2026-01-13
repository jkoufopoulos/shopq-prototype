"""ShopQ Return Watch - Track return windows on online purchases"""

from __future__ import annotations

__version__ = "1.0.0"

# Lazy imports for returns module
def __getattr__(name: str):
    """
    Lazy imports to avoid loading heavy dependencies when only importing lightweight modules.
    """
    if name in ("ReturnCard", "ReturnCardCreate", "ReturnCardUpdate", "ReturnCardRepository"):
        from shopq.returns import models, repository
        if name == "ReturnCard":
            return models.ReturnCard
        if name == "ReturnCardCreate":
            return models.ReturnCardCreate
        if name == "ReturnCardUpdate":
            return models.ReturnCardUpdate
        if name == "ReturnCardRepository":
            return repository.ReturnCardRepository

    if name in ("ReturnConfidence", "ReturnStatus"):
        from shopq.returns import models
        if name == "ReturnConfidence":
            return models.ReturnConfidence
        if name == "ReturnStatus":
            return models.ReturnStatus

    if name == "ReturnableReceiptExtractor":
        from shopq.returns.extractor import ReturnableReceiptExtractor
        return ReturnableReceiptExtractor

    msg = f"module {__name__!r} has no attribute {name!r}"
    raise AttributeError(msg)


__all__ = [
    "ReturnCard",
    "ReturnCardCreate",
    "ReturnCardUpdate",
    "ReturnCardRepository",
    "ReturnConfidence",
    "ReturnStatus",
    "ReturnableReceiptExtractor",
]
