"""Categories management endpoints for ShopQ API.

Provides CRUD endpoints for classification categories:
- GET /api/categories - List all categories
- POST /api/categories - Create new category
- GET /api/stats - Get learning statistics
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from fastapi import APIRouter, Depends, HTTPException, Request

from shopq.api.middleware.auth import require_admin_auth
from shopq.api.models import CategoryCreate
from shopq.api.utils import get_client_ip
from shopq.observability.telemetry import log_event
from shopq.utils.redaction import redact

if TYPE_CHECKING:
    from shopq.classification.memory_classifier import MemoryClassifier
    from shopq.digest.category_manager import CategoryManager

router = APIRouter(prefix="/api", tags=["categories"])

# Module-level storage for dependencies injected at startup
_category_manager: CategoryManager | None = None
_classifier: MemoryClassifier | None = None


def set_category_manager(manager: CategoryManager) -> None:
    """Inject the category manager dependency.

    Side Effects:
        - Sets module-level _category_manager variable
    """
    global _category_manager
    _category_manager = manager


def set_classifier(classifier: MemoryClassifier) -> None:
    """Inject the classifier dependency.

    Side Effects:
        - Sets module-level _classifier variable
    """
    global _classifier
    _classifier = classifier


@router.get("/categories")
async def get_categories() -> list[dict[str, Any]]:
    """Get all categories.

    Side Effects:
        - Reads from categories table in shopq.db
        - Logs telemetry events
    """
    if _category_manager is None:
        raise HTTPException(status_code=500, detail="Category manager not initialized")

    try:
        categories = _category_manager.get_categories()
        log_event("api.categories.success", count=len(categories))
        return categories
    except Exception as e:
        log_event("api.categories.error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/categories")
async def create_category(
    request: Request,
    category: CategoryCreate,
    _authenticated: bool = Depends(require_admin_auth),
) -> dict[str, Any]:
    """Create a new category (requires authentication).

    Side Effects:
        - Writes to categories table in shopq.db via category_manager.add_category()
        - Logs audit event via log_event()
    """
    if _category_manager is None:
        raise HTTPException(status_code=500, detail="Category manager not initialized")

    try:
        new_category = _category_manager.add_category(
            name=category.name,
            description=category.description or "",
            color=category.color or "#808080",
        )
        log_event(
            "api.categories.created",
            name=redact(category.name),
            client_ip=get_client_ip(request),
        )
        return new_category
    except Exception as e:
        log_event("api.categories.create_error", error=str(e))
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.get("/stats")
async def get_stats() -> dict[str, Any]:
    """Get learning statistics.

    Side Effects:
        - Reads from rules table in shopq.db
    """
    if _classifier is None:
        raise HTTPException(status_code=500, detail="Classifier not initialized")

    stats = _classifier.get_stats()

    return {
        "total_rules": stats["total_rules"],
        "model_version": stats["model_version"],
        "schema_version": "mvp.v1",
    }
