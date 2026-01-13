"""
Noise Elevation: Hybrid Importance Detection System

Rescues important emails incorrectly filtered to noise using two layers:
- Phase 1: Keyword guardrails (deterministic, zero cost, instant)
- Phase 2: Editor LLM (contextual, feature-flagged, reviews noise bucket)

Integration Point: After T1TemporalDecayStage, before EntityStage

Principle Alignment:
- P1: Single conceptual home for all elevation logic
- P2: Side effects explicitly documented (LLM calls, section mutations)
- P3: Typed dataclasses for all contracts
- P4: Explicit pipeline dependency on t1_temporal_decay
- P5: Progressive enhancement (keywords first, LLM optional)
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from shopq.observability.logging import get_logger

logger = get_logger(__name__)

# =============================================================================
# CONFIGURATION
# =============================================================================

# Feature flag for Editor LLM (Phase 2)
NOISE_ELEVATION_LLM_ENABLED = os.getenv("SHOPQ_NOISE_ELEVATION_LLM", "false").lower() == "true"

# Maximum emails to review with Editor LLM (cost control)
NOISE_ELEVATION_MAX_EMAILS = int(os.getenv("SHOPQ_NOISE_ELEVATION_MAX_EMAILS", "30"))

# Maximum elevations per digest (prevent over-elevation)
NOISE_ELEVATION_MAX_ELEVATIONS = int(os.getenv("SHOPQ_NOISE_ELEVATION_MAX", "3"))

# Minimum confidence for LLM elevation
NOISE_ELEVATION_CONFIDENCE_THRESHOLD = float(os.getenv("SHOPQ_NOISE_ELEVATION_CONFIDENCE", "0.85"))

# =============================================================================
# PHASE 1: KEYWORD TAXONOMY (DETERMINISTIC)
# =============================================================================

NOISE_ELEVATION_SIGNALS: dict[str, dict[str, Any]] = {
    # -------------------------------------------------------------------------
    # CRITICAL: Immediate attention required
    # -------------------------------------------------------------------------
    "state_reversal": {
        "boost_to": "critical",
        "keywords": [
            "cancelled",
            "canceled",
            "cancellation",
            "refund",
            "refunded",
            "refunding",
            "returned",
            "return initiated",
            "return approved",
            "failed",
            "failure",
            "declined",
            "rejected",
            "reversed",
            "reversal",
            "voided",
            "void",
            "dispute",
            "disputed",
            "chargeback",
        ],
        "reason": "State reversal detected (cancellation/refund/failure)",
    },
    "security": {
        "boost_to": "critical",
        "keywords": [
            "fraud",
            "fraudulent",
            "unauthorized",
            "unauthorised",
            "suspicious",
            "suspicious activity",
            "compromised",
            "breach",
            "data breach",
            "locked",
            "account locked",
            "verify your identity",
            "unusual activity",
            "unusual sign-in",
            "sign-in attempt",
            "login attempt",
            "security alert",
        ],
        "reason": "Security alert requires immediate attention",
    },
    "financial_risk": {
        "boost_to": "critical",
        "keywords": [
            "overdraft",
            "overdrawn",
            "insufficient funds",
            "nsf",
            "payment failed",
            "payment declined",
            "card declined",
            "past due",
            "overdue",
            "collection",
            "sent to collections",
            "final notice",
            "account suspended",
            "service interruption",
            "service terminated",
        ],
        "reason": "Financial risk requires attention",
    },
    # -------------------------------------------------------------------------
    # TIME_SENSITIVE: Urgent but not emergency
    # -------------------------------------------------------------------------
    "deadline_urgent": {
        "boost_to": "time_sensitive",
        "keywords": [
            "expires today",
            "expiring today",
            "expires tonight",
            "expiring tonight",
            "expires tomorrow",
            "expiring tomorrow",
            "last day",
            "last chance",
            "ending soon",
            "ends today",
            "ends tonight",
            "hours left",
            "hour left",
            "act now",
            "immediate action",
            "respond by today",
            "reply by today",
            "deadline today",
            "due today",
            "final reminder",
        ],
        "reason": "Time-sensitive deadline",
    },
    "event_today": {
        "boost_to": "time_sensitive",
        "keywords": [
            "starts in",
            "starting in",
            "begins in",
            "beginning in",
            "happening today",
            "today at",
            "tonight at",
            "this evening at",
            "this morning at",
            "this afternoon at",
            "in 1 hour",
            "in 2 hours",
            "in 30 minutes",
            "don't forget today",
            "reminder: today",
            "happening now",
            "starting now",
        ],
        "reason": "Event happening today",
    },
    # -------------------------------------------------------------------------
    # WORTH_KNOWING: Notable but not urgent
    # -------------------------------------------------------------------------
    "human_reply": {
        "boost_to": "worth_knowing",
        "subject_prefix": ["Re:", "RE:", "re:"],
        "keywords": [
            "replied to your",
            "responded to your",
            "answered your",
            "left a comment",
            "mentioned you",
            "@mentioned",
        ],
        "type_filter": ["message"],  # Only boost if type is message
        "reason": "Human replied to your message",
    },
}

# Amount threshold for high-value detection (Phase 1 regex-based)
HIGH_VALUE_THRESHOLD_USD = float(os.getenv("SHOPQ_HIGH_VALUE_THRESHOLD", "500"))


@dataclass
class ElevationResult:
    """Result of elevation check for a single email."""

    email_id: str
    elevated: bool
    original_section: str
    new_section: str | None = None
    reason: str | None = None
    signal_type: str | None = None
    confidence: float = 1.0  # 1.0 for keywords (deterministic), <1.0 for LLM


def extract_dollar_amount(text: str) -> float | None:
    """
    Extract dollar amount from text.

    Patterns:
        - $1,234.56
        - $1234.56
        - $1,234
        - $1234
        - 1,234.56 USD

    Returns:
        Float amount or None if no match
    """
    # Pattern: $X,XXX.XX or $X,XXX or $XXX.XX or $XXX
    patterns = [
        r"\$\s*([\d,]+\.?\d*)",  # $1,234.56 or $1234
        r"([\d,]+\.?\d*)\s*(?:USD|usd)",  # 1,234.56 USD
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                amount_str = match.group(1).replace(",", "")
                return float(amount_str)
            except (ValueError, IndexError):
                continue

    return None


def check_keyword_elevation(
    email: dict[str, Any],
    current_section: str,
) -> ElevationResult:
    """
    Check if email should be elevated based on keyword signals.

    Phase 1: Deterministic, zero cost, instant.

    Args:
        email: Email dict with subject, snippet, type
        current_section: Current T1 section assignment

    Returns:
        ElevationResult with elevation decision

    Side Effects: None (pure function)
    """
    email_id = email.get("id", email.get("thread_id", "unknown"))
    subject = email.get("subject", "")
    snippet = email.get("snippet", "")
    email_type = email.get("type", "")

    text = f"{subject} {snippet}".lower()

    # Only elevate from noise (don't demote already-elevated emails)
    if current_section != "noise":
        return ElevationResult(
            email_id=email_id,
            elevated=False,
            original_section=current_section,
        )

    # Check each signal category in priority order
    priority_order = [
        "security",  # Safety first
        "financial_risk",  # Money at stake
        "state_reversal",  # Unexpected changes
        "deadline_urgent",  # Time pressure
        "event_today",  # Temporal proximity
        "human_reply",  # Social signal
    ]

    for signal_type in priority_order:
        config = NOISE_ELEVATION_SIGNALS[signal_type]

        # Check type filter (e.g., human_reply only for messages)
        type_filter = config.get("type_filter")
        if type_filter and email_type not in type_filter:
            continue

        # Check subject prefix (e.g., "Re:" for replies)
        subject_prefixes = config.get("subject_prefix", [])
        if subject_prefixes and any(subject.startswith(prefix) for prefix in subject_prefixes):
            return ElevationResult(
                email_id=email_id,
                elevated=True,
                original_section=current_section,
                new_section=config["boost_to"],
                reason=config["reason"],
                signal_type=signal_type,
                confidence=1.0,
            )

        # Check keywords
        keywords = config.get("keywords", [])
        for keyword in keywords:
            if keyword in text:
                return ElevationResult(
                    email_id=email_id,
                    elevated=True,
                    original_section=current_section,
                    new_section=config["boost_to"],
                    reason=f"{config['reason']} (matched: '{keyword}')",
                    signal_type=signal_type,
                    confidence=1.0,
                )

    # Check high-value amount (Phase 1 regex-based)
    amount = extract_dollar_amount(f"{subject} {snippet}")
    if amount and amount >= HIGH_VALUE_THRESHOLD_USD:
        return ElevationResult(
            email_id=email_id,
            elevated=True,
            original_section=current_section,
            new_section="critical",
            reason=f"High-value transaction: ${amount:,.2f}",
            signal_type="high_value",
            confidence=1.0,
        )

    # No elevation signal found
    return ElevationResult(
        email_id=email_id,
        elevated=False,
        original_section=current_section,
    )


# =============================================================================
# PHASE 2: EDITOR LLM (CONTEXTUAL)
# =============================================================================


@dataclass
class LLMElevation:
    """Structured output from Editor LLM."""

    email_id: str
    target_section: str  # "critical" | "time_sensitive" | "worth_knowing"
    reason: str
    confidence: float


def build_editor_llm_prompt(
    noise_emails: list[dict[str, Any]],
    now: datetime,
) -> str:
    """
    Build prompt for Editor LLM to review noise bucket.

    Args:
        noise_emails: List of emails classified as noise
        now: Current datetime for temporal context

    Returns:
        Formatted prompt string
    """
    from shopq.utils.redaction import sanitize_for_prompt

    date_str = now.strftime("%A, %B %d, %Y at %I:%M %p")

    emails_section = ""
    for i, email in enumerate(noise_emails[:NOISE_ELEVATION_MAX_EMAILS], 1):
        email_id = email.get("id", email.get("thread_id", "unknown"))
        subject = sanitize_for_prompt(email.get("subject", ""), 150)
        sender = sanitize_for_prompt(email.get("from", "").split("<")[0].strip().strip('"'), 50)
        snippet = sanitize_for_prompt(email.get("snippet", "")[:200], 200)
        email_type = email.get("type", "unknown")

        emails_section += f"""
{i}. ID: {email_id}
   Type: {email_type}
   From: {sender}
   Subject: {subject}
   Preview: {snippet}
"""

    prompt = f"""You are an editorial assistant reviewing emails classified as routine/noise.

Current date/time: {date_str}

Your job: Flag any emails that are ACTUALLY IMPORTANT and explain WHY in one sentence.

## ALWAYS Elevate (Critical)
- Security/fraud alerts (unauthorized access, suspicious activity)
- Large financial amounts (>$500 payments, refunds, or purchases)
- State reversals (cancellations, refunds, failures after purchases)
- Payment failures, overdrafts, card declines

## ALWAYS Elevate (Time-Sensitive)
- Events happening TODAY or TOMORROW
- Replies from real humans (not automated notifications)
- Expiring offers/deadlines within 24-48 hours
- Deliveries arriving today

## NEVER Elevate
- Normal receipts under $100
- Routine newsletters (unless time-sensitive content)
- Promotional emails and marketing
- Standard delivery confirmations (ordered, shipped, delivered)
- Automated notifications without actionable content

## Output Format

For EACH email you recommend elevating, respond with EXACTLY this format:
```
ELEVATE: <email_id>
SECTION: <critical|time_sensitive|worth_knowing>
CONFIDENCE: <0.0-1.0>
REASON: <one sentence explaining why>
```

If NO emails should be elevated, respond with exactly:
```
NONE
```

## Emails to Review ({len(noise_emails)} total)
{emails_section}

---

Now review these emails. Be SELECTIVE - only elevate truly important items.
Maximum {NOISE_ELEVATION_MAX_ELEVATIONS} elevations allowed.
"""

    return prompt  # noqa: RET504


def parse_editor_llm_response(response_text: str) -> list[LLMElevation]:
    """
    Parse Editor LLM response into structured elevations.

    Args:
        response_text: Raw LLM response

    Returns:
        List of LLMElevation objects
    """
    elevations: list[LLMElevation] = []

    if "NONE" in response_text.strip():
        return elevations

    # Parse each ELEVATE block
    # Pattern: ELEVATE: <id>\nSECTION: <section>\nCONFIDENCE: <conf>\nREASON: <reason>
    pattern = (
        r"ELEVATE:\s*(\S+)\s*\n\s*SECTION:\s*(\w+)\s*\n\s*"
        r"CONFIDENCE:\s*([\d.]+)\s*\n\s*REASON:\s*(.+?)(?=\nELEVATE:|$)"
    )

    matches = re.findall(pattern, response_text, re.IGNORECASE | re.DOTALL)

    for match in matches:
        email_id, section, confidence_str, reason = match

        try:
            confidence = float(confidence_str)
        except ValueError:
            confidence = 0.8  # Default if parsing fails

        # Normalize section
        section = section.lower()
        if section not in {"critical", "time_sensitive", "worth_knowing"}:
            section = "worth_knowing"  # Safe default

        elevations.append(
            LLMElevation(
                email_id=email_id.strip(),
                target_section=section,
                reason=reason.strip(),
                confidence=confidence,
            )
        )

    return elevations


def call_editor_llm(
    noise_emails: list[dict[str, Any]],
    now: datetime,
) -> list[LLMElevation]:
    """
    Call Editor LLM to review noise bucket.

    Args:
        noise_emails: List of noise-classified emails
        now: Current datetime

    Returns:
        List of elevation recommendations

    Side Effects:
        - Calls Gemini Flash API (~$0.003 for 30 emails)
        - Logs LLM response and parsed results
    """
    if not noise_emails:
        return []

    try:
        import vertexai
        from vertexai.generative_models import GenerativeModel

        # Initialize Vertex AI
        project = os.getenv("GOOGLE_CLOUD_PROJECT", "mailq-467118")
        location = os.getenv("GEMINI_LOCATION", "us-central1")
        vertexai.init(project=project, location=location)

        model_name = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
        model = GenerativeModel(model_name)

        # Build and send prompt
        prompt = build_editor_llm_prompt(noise_emails, now)

        logger.info(f"Editor LLM: Reviewing {len(noise_emails)} noise emails")
        response = model.generate_content(prompt)
        response_text = response.text.strip()

        # Parse response
        elevations = parse_editor_llm_response(response_text)

        # Filter by confidence threshold
        elevations = [e for e in elevations if e.confidence >= NOISE_ELEVATION_CONFIDENCE_THRESHOLD]

        # Enforce max elevations quota
        elevations = elevations[:NOISE_ELEVATION_MAX_ELEVATIONS]

        logger.info(f"Editor LLM: {len(elevations)} emails recommended for elevation")
        for e in elevations:
            logger.info(f"  → {e.email_id}: {e.target_section} ({e.confidence:.2f}) - {e.reason}")

        return elevations

    except Exception as e:
        logger.exception(f"Editor LLM failed: {e}")
        return []


# =============================================================================
# PIPELINE STAGE
# =============================================================================


@dataclass
class NoiseElevationStage:
    """
    Hybrid noise elevation: Keywords (Phase 1) + Editor LLM (Phase 2).

    Rescues important emails incorrectly filtered to noise using:
    1. Keyword guardrails: Deterministic, zero cost, catches ~50% of cases
    2. Editor LLM: Contextual, feature-flagged, catches remaining ~50%

    Dependencies: t1_temporal_decay

    Side Effects: (P2)
        - Modifies context.section_assignments (elevates noise → featured)
        - Populates context.elevation_reasons (for transparency/debugging)
        - Optionally calls Gemini Flash API (Phase 2, ~$0.003/digest)
        - Logs all elevation decisions with reasons
    """

    name: str = "noise_elevation"
    depends_on: list[str] = field(default_factory=lambda: ["t1_temporal_decay"])

    def process(self, context: Any) -> Any:
        """
        Apply hybrid noise elevation.

        Pipeline:
        1. Collect all noise-classified emails
        2. Run keyword elevation (Phase 1) - all noise emails
        3. Run Editor LLM (Phase 2) - remaining noise emails (if enabled)
        4. Apply elevations to context.section_assignments

        Side Effects:
            - Mutates context.section_assignments
            - Populates context.elevation_reasons dict
            - Logs elevation decisions

        Returns:
            StageResult with elevation counts
        """
        from shopq.digest.digest_pipeline import StageResult

        # Initialize elevation_reasons if not present
        if not hasattr(context, "elevation_reasons"):
            context.elevation_reasons = {}

        # Use filtered_emails
        emails_to_process = context.filtered_emails if context.filtered_emails else context.emails
        emails_by_id = {
            email.get("id", email.get("thread_id", "unknown")): email for email in emails_to_process
        }

        # Collect noise emails
        noise_emails = []
        for email_id, section in context.section_assignments.items():
            if section == "noise" and email_id in emails_by_id:
                noise_emails.append(emails_by_id[email_id])

        if not noise_emails:
            logger.info("Noise elevation: No noise emails to process")
            return StageResult(
                success=True,
                stage_name=self.name,
                items_processed=0,
                items_output=0,
                metadata={"phase1_elevated": 0, "phase2_elevated": 0},
            )

        logger.info(f"Noise elevation: Processing {len(noise_emails)} noise emails")

        # =================================================================
        # PHASE 1: Keyword Elevation (Deterministic)
        # =================================================================
        phase1_elevated = 0
        remaining_noise = []

        for email in noise_emails:
            email_id = email.get("id", email.get("thread_id", "unknown"))
            current_section = context.section_assignments.get(email_id, "noise")

            result = check_keyword_elevation(email, current_section)

            if result.elevated:
                context.section_assignments[email_id] = result.new_section
                context.elevation_reasons[email_id] = {
                    "phase": "keyword",
                    "signal_type": result.signal_type,
                    "reason": result.reason,
                    "confidence": result.confidence,
                    "original_section": result.original_section,
                    "new_section": result.new_section,
                }
                phase1_elevated += 1
                logger.info(
                    f"Phase 1 elevated: {email_id} | noise → {result.new_section} | "
                    f"{result.signal_type}: {result.reason}"
                )
            else:
                remaining_noise.append(email)

        # =================================================================
        # PHASE 2: Editor LLM (Feature-Flagged)
        # =================================================================
        phase2_elevated = 0

        if NOISE_ELEVATION_LLM_ENABLED and remaining_noise:
            logger.info(
                f"Phase 2: Editor LLM reviewing {len(remaining_noise)} remaining noise emails"
            )

            llm_elevations = call_editor_llm(remaining_noise, context.now)

            for elevation in llm_elevations:
                if elevation.email_id in context.section_assignments:
                    original_section = context.section_assignments[elevation.email_id]
                    context.section_assignments[elevation.email_id] = elevation.target_section
                    context.elevation_reasons[elevation.email_id] = {
                        "phase": "editor_llm",
                        "signal_type": "contextual_anomaly",
                        "reason": elevation.reason,
                        "confidence": elevation.confidence,
                        "original_section": original_section,
                        "new_section": elevation.target_section,
                    }
                    phase2_elevated += 1
                    logger.info(
                        f"Phase 2 elevated: {elevation.email_id} | "
                        f"noise → {elevation.target_section} | "
                        f"({elevation.confidence:.2f}) {elevation.reason}"
                    )
        elif not NOISE_ELEVATION_LLM_ENABLED:
            logger.debug("Phase 2 disabled (SHOPQ_NOISE_ELEVATION_LLM=false)")

        total_elevated = phase1_elevated + phase2_elevated
        logger.info(
            f"Noise elevation complete: {total_elevated} elevated "
            f"(Phase 1: {phase1_elevated}, Phase 2: {phase2_elevated})"
        )

        return StageResult(
            success=True,
            stage_name=self.name,
            items_processed=len(noise_emails),
            items_output=total_elevated,
            metadata={
                "noise_count": len(noise_emails),
                "phase1_elevated": phase1_elevated,
                "phase2_elevated": phase2_elevated,
                "total_elevated": total_elevated,
                "llm_enabled": NOISE_ELEVATION_LLM_ENABLED,
            },
        )
