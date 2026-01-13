"""Rules management endpoints for MailQ API.

Provides CRUD endpoints for classification rules:
- GET /api/rules - List all rules
- POST /api/rules - Create new rule
- PUT /api/rules/{rule_id} - Update rule
- DELETE /api/rules/{rule_id} - Delete rule
- GET /api/rules/stats - Get rule statistics

Note: Pending rules are available via /api/feedback/pending-rules
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from mailq.api.middleware.auth import require_admin_auth
from mailq.api.models import RuleCreate, RuleUpdate
from mailq.api.utils import get_client_ip
from mailq.classification.rules_manager import (
    add_rule,
    delete_rule,
    get_rule_stats,
    get_rules,
    update_rule,
)
from mailq.observability.telemetry import log_event
from mailq.utils.redaction import redact

router = APIRouter(prefix="/api", tags=["rules"])


@router.get("/rules")
async def list_rules() -> dict[str, Any]:
    """GET /api/rules - List all rules.

    Side Effects:
        - Reads from rules table in mailq.db
        - Logs telemetry events
    """
    try:
        rules = get_rules()
        log_event("api.rules.success", count=len(rules))
        return {"rules": rules, "count": len(rules)}
    except Exception as e:
        log_event("api.rules.error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.post("/rules")
async def create_rule(
    request: Request,
    rule: RuleCreate,
    _authenticated: bool = Depends(require_admin_auth),
) -> dict[str, Any]:
    """POST /api/rules - Create new rule (requires authentication).

    Side Effects:
        - Writes to rules table in mailq.db via add_rule()
        - Logs audit event via log_event()
    """
    try:
        rule_id = add_rule(
            pattern_type=rule.pattern_type,
            pattern=rule.pattern,
            category=rule.category,
            confidence=rule.confidence,
        )

        log_event(
            "api.rules.created",
            rule_id=rule_id,
            pattern=redact(rule.pattern),
            category=redact(rule.category),
            client_ip=get_client_ip(request),
        )

        return {
            "id": rule_id,
            "status": "created",
            "rule": {
                "pattern_type": rule.pattern_type,
                "pattern": rule.pattern,
                "category": rule.category,
                "confidence": rule.confidence,
            },
        }
    except Exception as e:
        log_event("api.rules.create_error", error=str(e))
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.put("/rules/{rule_id}")
async def modify_rule(
    request: Request,
    rule_id: int,
    rule: RuleUpdate,
    _authenticated: bool = Depends(require_admin_auth),
) -> dict[str, Any]:
    """PUT /api/rules/:id - Update rule (requires authentication).

    Side Effects:
        - Updates rules table in mailq.db via update_rule()
        - Logs audit event via log_event()
    """
    try:
        updates = rule.model_dump(exclude_none=True)

        if not updates:
            raise HTTPException(status_code=400, detail="No fields to update")

        success = update_rule(rule_id, **updates)

        if success:
            log_event(
                "api.rules.updated",
                rule_id=rule_id,
                updated_fields=list(updates.keys()),
                client_ip=get_client_ip(request),
            )
            return {"status": "updated", "rule_id": rule_id}
        raise HTTPException(status_code=404, detail="Rule not found")

    except HTTPException:
        raise
    except Exception as e:
        log_event("api.rules.update_error", error=str(e), rule_id=rule_id)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.delete("/rules/{rule_id}")
async def remove_rule(
    request: Request,
    rule_id: int,
    _authenticated: bool = Depends(require_admin_auth),
) -> dict[str, Any]:
    """DELETE /api/rules/:id - Delete rule (requires authentication).

    Side Effects:
        - Deletes from rules table in mailq.db via delete_rule()
        - Logs audit event via log_event()
    """
    try:
        success = delete_rule(rule_id)

        if success:
            log_event(
                "api.rules.deleted",
                rule_id=rule_id,
                client_ip=get_client_ip(request),
            )
            return {"status": "deleted", "rule_id": rule_id}
        raise HTTPException(status_code=404, detail="Rule not found")

    except HTTPException:
        raise
    except Exception as e:
        log_event("api.rules.delete_error", error=str(e), rule_id=rule_id)
        raise HTTPException(status_code=500, detail=str(e)) from e


@router.get("/rules/stats")
async def rules_statistics() -> dict[str, Any]:
    """GET /api/rules/stats - Get rule statistics.

    Side Effects:
        - Reads from rules table in mailq.db
        - Logs telemetry events
    """
    try:
        stats = get_rule_stats()
        log_event("api.rules.stats", total=stats.get("total_rules"))
        return stats
    except Exception as e:
        log_event("api.rules.stats_error", error=str(e))
        raise HTTPException(status_code=500, detail=str(e)) from e
