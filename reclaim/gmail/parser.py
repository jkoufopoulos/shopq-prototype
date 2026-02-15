"""
Gmail adapter utilities for converting API payloads into domain models.

This module focuses on deterministic parsing and validation while remaining side-effect free.
Observability hooks surface parse failures without exposing PII.
"""

from __future__ import annotations

import base64
import binascii
import json
from collections.abc import Iterable
from hashlib import sha256
from typing import Any

from pydantic import ValidationError

from reclaim.infrastructure.idempotency import email_key
from reclaim.observability.telemetry import counter, log_event
from reclaim.storage.models import ParsedEmail, RawEmail

_TEXT_PLAIN = "text/plain"
_TEXT_HTML = "text/html"


class GmailParsingError(ValueError):
    """Raised when Gmail payload cannot be converted into domain models."""


def _header_lookup(headers: Iterable[dict[str, str]], name: str) -> str | None:
    name_lower = name.lower()
    for header in headers:
        if header.get("name", "").lower() == name_lower:
            return header.get("value")
    return None


def _decode_base64(data: str) -> str:
    """Decode Gmail's URL-safe base64 payloads."""
    padding = "=" * (-len(data) % 4)
    try:
        decoded = base64.urlsafe_b64decode((data + padding).encode("utf-8"))
        return decoded.decode("utf-8", errors="replace")
    except (binascii.Error, UnicodeDecodeError) as exc:
        raise GmailParsingError("failed to decode message body") from exc


def _extract_body(payload: dict[str, Any], lazy: bool = False) -> dict[str, str | None]:
    """
    Extract text and html bodies.

    Args:
        payload: Gmail message payload
        lazy: If True, only extract body if it's a simple inline part (defer large MIME parsing)

    // TODO(clarify): handle nested multiparts beyond first level once requirements confirmed.
    """
    body_text: str | None = None
    body_html: str | None = None

    mime_type = payload.get("mimeType", "")
    data = payload.get("body", {}).get("data")

    # Eager: always parse inline bodies
    if data and mime_type in {_TEXT_PLAIN, _TEXT_HTML}:
        decoded = _decode_base64(data)
        if mime_type == _TEXT_PLAIN:
            body_text = decoded
        else:
            body_html = decoded
        return {"text": body_text, "html": body_html}

    # Lazy mode: skip complex multipart parsing unless needed
    if lazy and payload.get("parts"):
        counter("gmail.lazy_parse.deferred")
        # Return placeholder to signal body needs on-demand parsing
        return {"text": "", "html": None}

    # Eager mode: parse multipart
    if payload.get("parts"):
        for part in payload["parts"]:
            part_mime = part.get("mimeType", "")
            part_data = part.get("body", {}).get("data")
            if not part_data:
                continue
            decoded_part = _decode_base64(part_data)
            if part_mime == _TEXT_PLAIN and body_text is None:
                body_text = decoded_part
            elif part_mime == _TEXT_HTML and body_html is None:
                body_html = decoded_part

    return {"text": body_text, "html": body_html}


def parse_message(message: dict[str, Any]) -> ParsedEmail:
    """
    Convert a Gmail API message into `ParsedEmail`.

    The returned object is fully validated; `GmailParsingError` is raised on failure.
    """
    if not isinstance(message, dict):
        raise GmailParsingError("message must be a dict")

    try:
        message_id = message["id"]
        thread_id = message["threadId"]
        internal_date = str(message.get("internalDate") or "")
        payload = message["payload"]
    except KeyError as exc:
        raise GmailParsingError(f"missing field: {exc}") from exc

    headers = payload.get("headers") or []
    subject = _header_lookup(headers, "Subject") or ""
    from_address = _header_lookup(headers, "From")
    to_address = _header_lookup(headers, "To")

    if not from_address or not to_address:
        raise GmailParsingError("required address headers missing")

    bodies = _extract_body(payload)
    if bodies["text"] is None and bodies["html"] is None:
        raise GmailParsingError("message body missing")

    raw_payload = {
        "message_id": message_id,
        "thread_id": thread_id,
        "received_ts": internal_date,
        "subject": subject,
        "from_address": from_address,
        "to_address": to_address,
        "body": bodies["text"] or bodies["html"] or "",
    }
    try:
        raw_email = RawEmail.model_validate(raw_payload)
    except ValidationError as exc:
        counter("schema_validation_failures")
        redacted = sha256(raw_payload["message_id"].encode()).hexdigest()[:12]
        log_event(
            "gmail.raw_email.validation_failed", errors=exc.errors(), message_id_hash=redacted
        )
        raise GmailParsingError("raw email validation failed") from exc

    parsed_payload = {
        "base": raw_email,
        "body_text": bodies["text"] or "",
        "body_html": bodies["html"],
    }
    try:
        parsed_email = ParsedEmail.model_validate(parsed_payload)
    except ValidationError as exc:
        counter("schema_validation_failures")
        redacted = sha256(raw_email.message_id.encode()).hexdigest()[:12]
        log_event(
            "gmail.parsed_email.validation_failed", errors=exc.errors(), message_id_hash=redacted
        )
        raise GmailParsingError("parsed email validation failed") from exc

    try:
        idempotency_key = email_key(raw_email.message_id, raw_email.received_ts, raw_email.body)
    except ValueError as exc:
        raise GmailParsingError(str(exc)) from exc

    log_event(
        "gmail.parsed",
        message_id_hash=sha256(raw_email.message_id.encode()).hexdigest()[:12],
        thread_id_hash=sha256(raw_email.thread_id.encode()).hexdigest()[:12],
        idempotency_key=idempotency_key,
    )
    counter("gmail.parsed.count")
    return parsed_email


def parse_message_strict(message: dict[str, Any]) -> ParsedEmail:
    """
    Wrapper that emits observability signals on failure.
    """
    try:
        return parse_message(message)
    except GmailParsingError as exc:
        hashed = sha256(str(message.get("id", "")).encode()).hexdigest()[:12]
        log_event(
            "gmail.parse_failed",
            message_id_hash=hashed,
            error=str(exc),
        )
        counter("gmail.parse_failed.count")
        raise
    except Exception as exc:
        snapshot = {
            "id_hash": sha256(str(message.get("id", "")).encode()).hexdigest()[:12],
            "thread_hash": sha256(str(message.get("threadId", "")).encode()).hexdigest()[:12],
        }
        log_event(
            "gmail.parse_unexpected_error",
            snapshot=json.dumps(snapshot),
            error=str(exc),
        )
        counter("gmail.parse_unexpected_error.count")
        raise
