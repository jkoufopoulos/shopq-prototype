"""
Pattern-based email classification rules.

Concept: High-confidence pattern overrides for email classification.
These are deterministic rules that don't require LLM inference.

Principle P1: This is the ONE home for pattern-based classification logic.
Principle P2: No side effects - pure transformation functions.
Principle P3: Typed inputs/outputs for compile-time safety.
"""

import re
from dataclasses import dataclass

from mailq.observability.confidence import DETECTOR_CONFIDENCE

# Pattern confidence values (referenced from centralized confidence module)
PATTERN_CONFIDENCE = {
    "otp": DETECTOR_CONFIDENCE["otp"]["type_conf"],  # 0.98
    "delivery": DETECTOR_CONFIDENCE["receipt"]["type_conf"],  # 0.92
    "receipt": DETECTOR_CONFIDENCE["receipt"]["type_conf"],  # 0.92
    "newsletter_promo": 0.92,  # Same as receipt
    "event": 0.90,
    "bill_deadline": DETECTOR_CONFIDENCE["bank_notification"]["attention_conf"],  # 0.94
    "message": 0.92,
}


@dataclass
class EmailLabel:
    """Email classification label with metadata."""

    email_type: str
    importance: str
    client_label: str | None = None
    temporal_start: str | None = None
    temporal_end: str | None = None
    confidence: float = 0.0
    reasoning: str = ""


def apply_pattern_overrides(
    subject: str,
    snippet: str,
    from_email: str,  # noqa: ARG001 - kept for API compatibility
    label: EmailLabel,
    received_date: str | None = None,
) -> EmailLabel:
    """
    Apply high-confidence pattern-based label corrections.

    Args:
        subject: Email subject line
        snippet: Email snippet/preview text
        from_email: Sender email address
        label: Initial classification label to potentially override
        received_date: Email received date (for temporal pattern extraction)

    Returns:
        EmailLabel with pattern overrides applied

    Side Effects: None (pure function)

    Pattern Rules (from GDS labeling requirements):
    - OTP / verification codes → notification, critical, everything-else, no temporal
    - Receipts / order confirmations → receipt type, receipts label
    - Delivery notifications → extract temporal window from received_date
    - Newsletters/promos → routine importance, everything-else
    - Events → time_sensitive default (critical if imminent)
    - Bills/deadlines → action-required label
    - Messages (1:1 human) → messages label
    """
    text = f"{subject.lower()} {snippet.lower()}"
    original_reasoning = label.reasoning

    # Rule 1: OTP / Verification codes
    otp_patterns = [
        r"verification code",
        r"verify.*(email|identity|account)",
        r"one.?time.*(code|password|pass)",
        r"\bOTP\b",
        r"authentication code",
        r"security code",
        r"login code",
        r"confirm.*(email|identity)",
    ]
    if any(re.search(pattern, text, re.IGNORECASE) for pattern in otp_patterns):
        return EmailLabel(
            email_type="notification",
            importance="critical",
            client_label="everything-else",
            temporal_start=None,
            temporal_end=None,
            confidence=PATTERN_CONFIDENCE["otp"],
            reasoning=f"Pattern: OTP detected | Original: {original_reasoning}",
        )

    # Rule 2: Delivery notifications with temporal window extraction
    delivery_patterns = [
        r"out for delivery",
        r"arriving today",
        r"delivered today",
        r"delivery.*today",
    ]
    if (
        any(re.search(pattern, text, re.IGNORECASE) for pattern in delivery_patterns)
        and received_date
    ):
        # Parse received_date to extract date portion
        # Format: "Sat, 24 May 2025 12:23:37 +0000 (UTC)"
        from datetime import datetime

        try:
            # Parse the email date
            date_obj = datetime.strptime(received_date.split(" (")[0], "%a, %d %b %Y %H:%M:%S %z")
            date_str = date_obj.strftime("%Y-%m-%d")

            # Standard delivery window: 9am - 9pm
            temporal_start = f"{date_str}T09:00:00"
            temporal_end = f"{date_str}T21:00:00"

            return EmailLabel(
                email_type=label.email_type,
                importance="time_sensitive",  # Delivery is time-sensitive
                client_label=label.client_label or "receipts",
                temporal_start=temporal_start,
                temporal_end=temporal_end,
                confidence=PATTERN_CONFIDENCE["delivery"],
                reasoning=f"Pattern: Delivery (temporal) | Original: {original_reasoning}",
            )
        except (ValueError, IndexError):
            # If date parsing fails, keep original temporal data
            pass

    # Rule 3: Receipts / Order confirmations
    receipt_patterns = [
        r"receipt",
        r"order (confirmation|confirmed)",
        r"purchase confirmation",
        r"payment (received|confirmed)",
        r"invoice",
        r"your order from",
        r"order.*shipped",
    ]
    if any(re.search(pattern, text, re.IGNORECASE) for pattern in receipt_patterns):
        return EmailLabel(
            email_type="receipt",
            importance=label.importance,  # Keep existing importance
            client_label="receipts",
            temporal_start=label.temporal_start,
            temporal_end=label.temporal_end,
            confidence=PATTERN_CONFIDENCE["receipt"],
            reasoning=f"Pattern: Receipt detected | Original: {original_reasoning}",
        )

    # Rule 3: Newsletters, promos, marketing → routine + everything-else
    if label.email_type in ["newsletter", "promotion", "promo"]:
        return EmailLabel(
            email_type=label.email_type,
            importance="routine",
            client_label="everything-else",
            temporal_start=label.temporal_start,
            temporal_end=label.temporal_end,
            confidence=PATTERN_CONFIDENCE["newsletter_promo"],
            reasoning=f"Pattern: Newsletter/promo → routine | Original: {original_reasoning}",
        )

    # Rule 4: Events → default time_sensitive (unless critical indicators)
    if label.email_type == "event":
        critical_indicators = [
            r"\btoday\b",
            r"\bnow\b",
            r"\bimminent\b",
            r"\burgent\b",
            r"in \d+ (hour|min)",
        ]
        is_critical = any(re.search(p, text, re.IGNORECASE) for p in critical_indicators)

        return EmailLabel(
            email_type="event",
            importance="critical" if is_critical else "time_sensitive",
            client_label=label.client_label,
            temporal_start=label.temporal_start,
            temporal_end=label.temporal_end,
            confidence=PATTERN_CONFIDENCE["event"],
            reasoning=f"Pattern: Event importance adjusted | Original: {original_reasoning}",
        )

    # Rule 5: Bills / Deadlines → action-required
    bill_patterns = [
        r"bill.*due",
        r"payment.*due",
        r"expires? (soon|today|tomorrow)",
        r"deadline",
        r"submit by",
        r"renew (now|soon|by)",
    ]
    if any(re.search(pattern, text, re.IGNORECASE) for pattern in bill_patterns):
        return EmailLabel(
            email_type=label.email_type,
            importance=label.importance,
            client_label="action-required",
            temporal_start=label.temporal_start,
            temporal_end=label.temporal_end,
            confidence=PATTERN_CONFIDENCE["bill_deadline"],
            reasoning=f"Pattern: Bill/deadline → action-required | Original: {original_reasoning}",
        )

    # Rule 6: Message type → messages label
    if label.email_type == "message":
        return EmailLabel(
            email_type="message",
            importance=label.importance,
            client_label="messages",
            temporal_start=label.temporal_start,
            temporal_end=label.temporal_end,
            confidence=PATTERN_CONFIDENCE["message"],
            reasoning=f"Pattern: Message type → messages label | Original: {original_reasoning}",
        )

    # No pattern match - return original label
    return label
