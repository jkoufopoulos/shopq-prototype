"""

from __future__ import annotations

API Endpoints for Span-Aware Entity Linker

Provides HTTP endpoints for testing and debugging the entity linking system.
"""

from typing import Any

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from shopq.classification.linker import Entity as LinkerEntity
from shopq.classification.linker import SpanAwareEntityLinker

router = APIRouter(prefix="/api/linker", tags=["linker"])


class EntityInput(BaseModel):
    """Entity input for linking"""

    name: str
    url: str
    normalized_name: str | None = None
    entity_type: str = "generic"
    priority: int = 0


class ResolveSpansRequest(BaseModel):
    """Request body for resolve-spans endpoint"""

    text: str
    entities: list[EntityInput]
    fuzzy_threshold: float = 0.85
    enable_fallback: bool = False


class ResolveSpansResponse(BaseModel):
    """Response from resolve-spans endpoint"""

    html_text: str
    spans: list[dict]
    fallback_links: list[dict]
    html_valid: bool
    stats: dict


@router.post("/resolve-spans", response_model=ResolveSpansResponse)
async def resolve_spans(request: ResolveSpansRequest) -> ResolveSpansResponse:
    """
    Resolve entity spans in text and inject links.

    Example request:
    ```json
    {
        "text": "Bank of America sent you a refund.",
        "entities": [
            {
                "name": "Bank of America",
                "url": "https://mail.google.com/mail/u/0/#inbox/123"
            }
        ]
    }
    ```

    Returns:
    - html_text: Text with HTML anchor tags
    - spans: List of detected spans with positions and confidence
    - fallback_links: Entities that couldn't be linked
    - html_valid: Whether HTML is well-formed
    - stats: Matching statistics
    """
    # Convert input entities to linker format
    linker_entities = [
        LinkerEntity(
            name=e.name,
            normalized_name=e.normalized_name or e.name.lower(),
            url=e.url,
            entity_type=e.entity_type,
            priority=e.priority,
        )
        for e in request.entities
    ]

    # Create linker
    linker = SpanAwareEntityLinker(
        fuzzy_threshold=request.fuzzy_threshold,
        fallback_mode="append" if request.enable_fallback else "none",
    )

    # Link entities
    result = linker.link_entities(
        request.text, linker_entities, enable_fallback=request.enable_fallback
    )

    return ResolveSpansResponse(**result)


# Storage for debug samples
_debug_samples: dict[str, dict] = {}


@router.post("/debug/save-sample")
async def save_debug_sample(
    sample_id: str,
    text: str,
    entities: list[EntityInput],
    rendered: str | None = None,
) -> dict[str, Any]:
    """
    Save a sample for debugging.

    Used to store specific cases that can be reviewed later.
    """
    _debug_samples[sample_id] = {
        "text": text,
        "entities": [e.dict() for e in entities],
        "rendered": rendered,
    }

    return {"status": "saved", "sample_id": sample_id}


@router.get("/debug/{sample_id}")
async def get_debug_sample(sample_id: str) -> dict[str, Any]:
    """
    Retrieve a saved debug sample and re-run linking.

    Returns:
    - Original text and entities
    - Current linking result
    - HTML validation status
    - Span details
    """
    if sample_id not in _debug_samples:
        raise HTTPException(status_code=404, detail=f"Sample {sample_id} not found")

    sample = _debug_samples[sample_id]

    # Re-run linking
    request = ResolveSpansRequest(
        text=sample["text"], entities=[EntityInput(**e) for e in sample["entities"]]
    )

    result = await resolve_spans(request)

    return {
        "sample_id": sample_id,
        "text": sample["text"],
        "entities": sample["entities"],
        "rendered": result.html_text,
        "spans": result.spans,
        "html_valid": result.html_valid,
        "stats": result.stats,
    }


@router.get("/debug/list-samples")
async def list_debug_samples() -> dict[str, Any]:
    """List all saved debug samples"""
    return {
        "samples": [
            {
                "sample_id": sample_id,
                "text_preview": data["text"][:100],
                "entity_count": len(data["entities"]),
            }
            for sample_id, data in _debug_samples.items()
        ]
    }


@router.post("/test")
async def test_linker(
    text: str = "Bank of America sent you a refund.",
    entity_name: str = "Bank of America",
    entity_url: str = "https://mail.google.com/mail/u/0/#inbox/123",
) -> dict[str, Any]:
    """
    Quick test endpoint for the linker.

    Example: GET /api/linker/test?text=Bank%20of%20America%20sent%20you%20a%20refund
    """
    request = ResolveSpansRequest(
        text=text, entities=[EntityInput(name=entity_name, url=entity_url)]
    )

    result = await resolve_spans(request)

    return {
        "input": {"text": text, "entity": entity_name},
        "output": {
            "html": result.html_text,
            "matched": result.stats["matched_entities"] > 0,
            "spans": result.spans,
        },
    }
