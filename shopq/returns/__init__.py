"""
ShopQ Returns module - Return Watch tracking and alerts.
"""

from shopq.returns.extractor import (
    ExtractionResult,
    ExtractionStage,
    ReturnableReceiptExtractor,
    extract_return_card,
)
from shopq.returns.field_extractor import ExtractedFields, ReturnFieldExtractor
from shopq.returns.filters import FilterResult, MerchantDomainFilter
from shopq.returns.models import (
    ReturnCard,
    ReturnCardCreate,
    ReturnCardUpdate,
    ReturnConfidence,
    ReturnStatus,
)
from shopq.returns.repository import ReturnCardRepository
from shopq.returns.returnability_classifier import (
    ReceiptType,
    ReturnabilityClassifier,
    ReturnabilityResult,
)

__all__ = [
    # Models
    "ReturnCard",
    "ReturnCardCreate",
    "ReturnCardUpdate",
    "ReturnConfidence",
    "ReturnStatus",
    # Repository
    "ReturnCardRepository",
    # Filters
    "FilterResult",
    "MerchantDomainFilter",
    # Classifier
    "ReceiptType",
    "ReturnabilityClassifier",
    "ReturnabilityResult",
    # Field Extractor
    "ExtractedFields",
    "ReturnFieldExtractor",
    # Extractor (main pipeline)
    "ExtractionResult",
    "ExtractionStage",
    "ReturnableReceiptExtractor",
    "extract_return_card",
]
