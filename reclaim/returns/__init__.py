"""
Reclaim Returns module - Return Watch tracking and alerts.
"""

from reclaim.returns.extractor import (
    ReturnableReceiptExtractor,
    extract_return_card,
)
from reclaim.returns.field_extractor import ReturnFieldExtractor
from reclaim.returns.filters import MerchantDomainFilter
from reclaim.returns.models import (
    ReturnCard,
    ReturnCardCreate,
    ReturnCardUpdate,
    ReturnConfidence,
    ReturnStatus,
)
from reclaim.returns.returnability_classifier import (
    ReceiptType,
    ReturnabilityClassifier,
    ReturnabilityResult,
)
from reclaim.returns.types import ExtractedFields, ExtractionResult, ExtractionStage, FilterResult

__all__ = [
    # Models
    "ReturnCard",
    "ReturnCardCreate",
    "ReturnCardUpdate",
    "ReturnConfidence",
    "ReturnStatus",
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
