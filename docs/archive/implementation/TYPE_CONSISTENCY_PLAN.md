# Type Consistency Integration Plan

**Status**: Ready for Implementation ✅
**Goal**: Eliminate type drift (calendar invites → notification) via deterministic type mapper + LLM fallback
**Timeline**: 3-5 days
**Aligns with**: CLASSIFICATION_REFACTOR_PLAN.md Phase B0/P2, GPT-5 Temporal Framework, gds-1.0 contracts

---

## Executive Summary

This plan adds **global deterministic type rules** to ensure consistent type assignment (especially `type=event` for calendar invitations) for ALL users from day 1, while preserving the existing rules-first + LLM fallback architecture.

### Key Innovation

**Type Mapper = Shared Intelligence** (not user-specific learning)

- ✅ Works immediately for new users (no learning required)
- ✅ Ensures calendar invites are consistently typed as "event"
- ✅ Complements existing RulesEngine (user-specific learning)
- ✅ No new LLM calls (deterministic rules only)
- ✅ Aligns with GPT-5's type normalization recommendations

---

## Current State (Type Assignment Today)

```python
# shopq/memory_classifier.py::classify()

# Step 1: Try rules first
rule_result = self.rules.classify(...)  # User-specific rules DB
# ❌ New users: empty rules → skip
# ❌ Existing users: may have learned wrong type

# Step 2: Use LLM
semantic_result = self.llm_classifier.classify(...)
# ⚠️ Gemini sometimes returns type=notification for calendar invites
# ⚠️ Inconsistent across users and over time

# Step 3: Map to Gmail labels
mapping = map_to_gmail_labels(semantic_result)
```

**Problem**: Calendar notification from `calendar-notification@google.com` may get:
- User A: `type=event` (correct, if Gemini gets it right)
- User B: `type=notification` (wrong, if Gemini drifts)
- Same user, different days: inconsistent

---

## Proposed Architecture (Type Mapper Integration)

```python
# shopq/memory_classifier.py::classify() (ENHANCED)

# Step 0: Check global deterministic type rules (NEW)
type_hint = type_mapper.get_deterministic_type({
    "sender_domain": extract_domain(from_field),
    "subject": subject,
    "snippet": snippet,
})

# Step 1: Try user-specific rules
if type_hint:
    # Use deterministic type, skip LLM for type dimension
    semantic_result = self.llm_classifier.classify_with_type_hint(
        subject, snippet, from_field, type_hint=type_hint
    )
    # ✅ type=event locked in, LLM only classifies domains/attention
else:
    rule_result = self.rules.classify(...)

    if rule_result["source"] == "rule":
        semantic_result = self._rule_to_semantic(rule_result, from_field)
    else:
        # Step 2: Use LLM for everything
        semantic_result = self.llm_classifier.classify(...)

        # Step 2.5: Post-LLM type correction (NEW)
        semantic_result = type_mapper.correct_type_if_needed(
            semantic_result, from_field, subject, snippet
        )

# Step 3: Map to Gmail labels (unchanged)
mapping = map_to_gmail_labels(semantic_result)
```

---

## Type Mapper Design (Global Deterministic Rules)

### Principles

1. **High precision, low coverage** - Only match when >95% confident
2. **Not user-specific** - Same rules for all users (shared intelligence)
3. **Fast** - No LLM calls, no DB queries (in-memory pattern matching)
4. **Versioned** - Rules stored in config file under version control
5. **Testable** - Every rule has test cases in gds-1.0

### Rule Schema

```yaml
# config/type_mapper_rules.yaml

version: "1.0"
last_updated: "2025-11-10"

# Type: event (calendar invitations, reservations, bookings)
event:
  # Sender domain patterns (exact or wildcard)
  sender_domains:
    - "calendar-notification@google.com"
    - "noreply@calendar.google.com"
    - "*@calendar.google.com"
    - "invite@*.ics"
    - "events@eventbrite.com"
    - "no-reply@calendar.yahoo.com"

  # Subject regex patterns (case-insensitive)
  subject_patterns:
    - "Notification: .* @ (Mon|Tue|Wed|Thu|Fri|Sat|Sun)"
    - "Updated invitation:"
    - "Invitation:.*has invited you"
    - "^Accepted:.*"
    - "^Canceled:.*"
    - "Event reminder:"

  # Body/snippet phrases (exact match, case-insensitive)
  body_phrases:
    - "Join with Google Meet"
    - "Join Zoom Meeting"
    - "Add to Calendar"
    - "RSVP:"
    - "Organizer:"
    - "When:"
    - "Where:"

  # Attachment indicators
  attachment_extensions:
    - ".ics"
    - ".vcs"

  # Confidence for rule match
  confidence: 0.98

# Type: receipt (transaction confirmations)
receipt:
  sender_domains:
    - "auto-confirm@amazon.com"
    - "ship-confirm@amazon.com"
    - "payments-noreply@google.com"
    - "merchant@paypal.com"

  subject_patterns:
    - "Order Confirmation"
    - "Receipt for"
    - "Payment confirmation"
    - "Transaction receipt"

  body_phrases:
    - "Order #"
    - "Receipt #"
    - "Transaction ID"
    - "Total paid"

  confidence: 0.95

# Type: notification (shipping, status updates)
notification:
  # Only add if sender is ambiguous (Amazon sends both receipts and notifications)
  # Most notifications should fall through to LLM
  sender_domains:
    - "shipment-tracking@amazon.com"
    - "auto-notify@amazon.com"

  subject_patterns:
    - "Your package has shipped"
    - "Shipment notification"
    - "Delivery update"

  confidence: 0.90
```

### Implementation: type_mapper.py

```python
# shopq/type_mapper.py (NEW)

from __future__ import annotations

import re
from typing import Optional
import yaml
from pathlib import Path

from shopq.logging import get_logger

logger = get_logger(__name__)

class TypeMapper:
    """
    Global deterministic type assignment rules.

    Ensures consistent type classification across all users for known patterns
    (e.g., calendar invitations, receipts from major vendors).

    Not user-specific - these are universal truths about email types.
    """

    def __init__(self, rules_path: str | None = None):
        if rules_path is None:
            rules_path = Path(__file__).parent.parent / "config" / "type_mapper_rules.yaml"

        self.rules = self._load_rules(rules_path)
        logger.info(f"Type mapper initialized with {len(self.rules)} type categories")

    def _load_rules(self, rules_path: str) -> dict:
        """Load type rules from YAML config."""
        try:
            with open(rules_path, 'r') as f:
                config = yaml.safe_load(f)

            # Remove metadata, return only type rules
            rules = {k: v for k, v in config.items()
                    if k not in ['version', 'last_updated']}

            logger.info(f"Loaded type mapper rules version {config.get('version', 'unknown')}")
            return rules
        except Exception as e:
            logger.warning(f"Failed to load type mapper rules: {e}, using empty ruleset")
            return {}

    def get_deterministic_type(
        self,
        sender_domain: str,
        subject: str,
        snippet: str,
        has_ics_attachment: bool = False
    ) -> Optional[dict]:
        """
        Get deterministic type if email matches known patterns.

        Returns:
            {
                "type": "event",
                "confidence": 0.98,
                "matched_rule": "sender_domain: calendar-notification@google.com"
            }
            or None if no match
        """

        sender_domain = sender_domain.lower()
        subject_lower = subject.lower()
        snippet_lower = snippet.lower()

        for type_name, type_rules in self.rules.items():
            matched_rule = None

            # Check sender domains
            for domain_pattern in type_rules.get('sender_domains', []):
                if self._matches_domain(sender_domain, domain_pattern):
                    matched_rule = f"sender_domain: {domain_pattern}"
                    break

            # Check subject patterns
            if not matched_rule:
                for pattern in type_rules.get('subject_patterns', []):
                    if re.search(pattern, subject_lower, re.IGNORECASE):
                        matched_rule = f"subject_pattern: {pattern}"
                        break

            # Check body phrases
            if not matched_rule:
                for phrase in type_rules.get('body_phrases', []):
                    if phrase.lower() in snippet_lower:
                        matched_rule = f"body_phrase: {phrase}"
                        break

            # Check attachments
            if not matched_rule and has_ics_attachment:
                for ext in type_rules.get('attachment_extensions', []):
                    if ext == '.ics':
                        matched_rule = f"attachment: {ext}"
                        break

            # If any rule matched, return this type
            if matched_rule:
                confidence = type_rules.get('confidence', 0.95)
                logger.info(f"Type mapper: {type_name} (matched: {matched_rule})")

                return {
                    "type": type_name,
                    "confidence": confidence,
                    "matched_rule": matched_rule,
                    "decider": "type_mapper"
                }

        # No deterministic match
        return None

    def correct_type_if_needed(
        self,
        classification: dict,
        sender_domain: str,
        subject: str,
        snippet: str
    ) -> dict:
        """
        Post-LLM type correction for known drift cases.

        If LLM misclassified (e.g., type=notification for calendar invite),
        fix it and log the correction.

        Returns: Modified classification dict
        """

        # Only correct if LLM returned notification/other ambiguous types
        if classification["type"] not in ["notification", "uncategorized", "message"]:
            return classification  # Don't override clear types (receipt, event, etc.)

        # Check if this should actually be a different type
        deterministic = self.get_deterministic_type(
            sender_domain, subject, snippet, has_ics_attachment=False
        )

        if deterministic and deterministic["type"] != classification["type"]:
            old_type = classification["type"]
            logger.warning(
                f"Type corrected: {old_type} → {deterministic['type']} "
                f"(matched: {deterministic['matched_rule']})"
            )

            classification["type"] = deterministic["type"]
            classification["type_conf"] = deterministic["confidence"]
            classification["decider"] = "type_corrector"
            classification["reason"] = (
                f"{classification.get('reason', '')} "
                f"[corrected from {old_type}: {deterministic['matched_rule']}]"
            )

        return classification

    def _matches_domain(self, email_domain: str, pattern: str) -> bool:
        """
        Match email domain against pattern (supports wildcards).

        Examples:
            email_domain="calendar-notification@google.com"
            pattern="calendar-notification@google.com" → True (exact)
            pattern="*@google.com" → True (wildcard)
            pattern="*@calendar.google.com" → False (subdomain mismatch)
        """

        if pattern == email_domain:
            return True  # Exact match

        if '*' in pattern:
            # Convert wildcard pattern to regex
            regex_pattern = pattern.replace('.', r'\.').replace('*', '.*')
            return bool(re.match(f"^{regex_pattern}$", email_domain))

        return False


# Singleton instance (loaded once at startup)
_type_mapper_instance = None

def get_type_mapper() -> TypeMapper:
    """Get singleton TypeMapper instance."""
    global _type_mapper_instance
    if _type_mapper_instance is None:
        _type_mapper_instance = TypeMapper()
    return _type_mapper_instance
```

---

## Integration Points

### 1. Memory Classifier (Main Orchestrator)

```python
# shopq/memory_classifier.py (MODIFY)

from shopq.type_mapper import get_type_mapper

class MemoryClassifier:
    def __init__(self, category_manager=None):
        # ... existing init ...
        self.type_mapper = get_type_mapper()  # NEW

    def classify(self, subject, snippet, from_field, user_id="default", user_prefs=None):
        """Enhanced with type mapper integration."""

        sender_domain = extract_domain(from_field)  # Helper function

        # PHASE 0: Check global deterministic type rules (NEW)
        type_hint = self.type_mapper.get_deterministic_type(
            sender_domain, subject, snippet
        )

        if type_hint:
            # Type is deterministic - use it directly
            logger.info(f"Type mapper hit: {type_hint['type']} ({type_hint['matched_rule']})")

            # Still call LLM for domains/attention, but pass type hint
            semantic_result = self.llm_classifier.classify(
                subject, snippet, from_field,
                type_override={
                    "type": type_hint["type"],
                    "type_conf": type_hint["confidence"],
                    "decider": "type_mapper"
                }
            )
        else:
            # PHASE 1: Try user-specific rules
            rule_result = self.rules.classify(subject, snippet, from_field, user_id)

            if rule_result["source"] == "rule":
                semantic_result = self._rule_to_semantic(rule_result, from_field)
            else:
                # PHASE 2: Use LLM for everything
                semantic_result = self.llm_classifier.classify(
                    subject, snippet, from_field
                )

                # PHASE 2.5: Post-LLM type correction (NEW)
                semantic_result = self.type_mapper.correct_type_if_needed(
                    semantic_result, sender_domain, subject, snippet
                )

        # PHASE 3: Map to Gmail labels (unchanged)
        mapping = map_to_gmail_labels(semantic_result, user_prefs)
        semantic_result["gmail_labels"] = mapping["labels"]
        semantic_result["gmail_labels_conf"] = mapping["labels_conf"]

        # PHASE 4: Learning (unchanged, but skip if type was deterministic)
        if (
            self.enable_learning
            and semantic_result["decider"] not in ["type_mapper", "type_corrector"]
            and semantic_result["type_conf"] >= LEARNING_MIN_CONFIDENCE
        ):
            self.rules.learn_from_classification(...)

        return semantic_result
```

### 2. Vertex Gemini Classifier (LLM)

```python
# shopq/vertex_gemini_classifier.py (MODIFY)

class VertexGeminiClassifier:
    def classify(
        self,
        subject: str,
        snippet: str,
        from_field: str,
        email_id: str | None = None,
        normalized_input_digest: str | None = None,
        type_override: dict | None = None  # NEW parameter
    ) -> dict:
        """Classify with optional type override (from type mapper)."""

        if type_override:
            # Type is deterministic - don't ask LLM for type
            # Only classify domains/attention
            prompt = get_classifier_prompt_domains_only(
                from_field, subject, snippet,
                known_type=type_override["type"]
            )

            result = self._call_model(prompt)

            # Merge with type override
            result["type"] = type_override["type"]
            result["type_conf"] = type_override["confidence"]
            result["decider"] = type_override["decider"]

            return result
        else:
            # Normal classification (all dimensions)
            return self._classify_full(subject, snippet, from_field)
```

---

## Alignment with OpenAI GPT-5 Framework

### Type Normalization (GPT-5 Recommendation #4)

✅ **Adopted**: Calendar emails → `type=event` (NOT notification)

```yaml
# GPT-5 Temporal Framework (TYPE_CONSISTENCY_PLAN.md aligns with this)

Type Normalization:
  - Calendar emails → type=event (NOT notification)  ✅ Type mapper enforces this
  - Newsletters/articles → type=newsletter
  - Bills with AutoPay → type=notification
  - Bills with due date, no autopay → type=deadline
```

**Implementation**:
```yaml
# config/type_mapper_rules.yaml

event:
  sender_domains:
    - "calendar-notification@google.com"  # ✅ GPT-5 recommendation
    - "*@calendar.google.com"

  subject_patterns:
    - "Notification: .* @ (Mon|Tue|Wed)"  # ✅ Catches "Notification: Meeting @ Wed"
```

### Stage 1/Stage 2 Contract Alignment

```python
# Stage 1 (Classification) - Type mapper runs here
# Output: Base classification + temporal metadata

{
  "type": "event",  # ✅ Type mapper ensures consistency
  "stored_importance": "routine",  # Stage 1 doesn't know event timing yet
  "temporal": {
    "event_start": "2025-11-21T23:30:00Z",  # Extracted from subject/body
    "event_end": "2025-11-22T00:30:00Z"
  }
}

# Stage 2 (Temporal Decay) - Runs at digest time
# Input: Stage 1 output + current time
# Output: Resolved importance

{
  "resolved_importance": "time_sensitive",  # Event starts in 3 days
  "decay_reason": "temporal_upcoming",
  "explanations": ["Dinner tomorrow at 7pm"]
}
```

**Key Point**: Type mapper ensures `type=event` is set correctly in **Stage 1**, so that **Stage 2** temporal decay rules can properly apply event proximity logic.

---

## Testing Strategy

### 1. gds-1.0 Regression Tests

```python
# tests/test_type_mapper_gds.py (NEW)

import pytest
from shopq.type_mapper import get_type_mapper

def test_gds_event_consistency():
    """All 56 events in gds-1.0 must be typed as 'event'."""

    gds = load_golden_dataset("tests/golden_set/gds-1.0.csv")
    type_mapper = get_type_mapper()

    event_emails = [e for e in gds if e["email_type"] == "event"]
    assert len(event_emails) == 56, "gds-1.0 should have 56 events"

    failures = []
    for email in event_emails:
        sender_domain = extract_domain(email["from_email"])
        result = type_mapper.get_deterministic_type(
            sender_domain,
            email["subject"],
            email["snippet"]
        )

        # Type mapper should match at least some events
        # (Not all 56 will match rules - that's fine, LLM handles the rest)
        if result:
            if result["type"] != "event":
                failures.append({
                    "subject": email["subject"],
                    "expected": "event",
                    "got": result["type"]
                })

    # At minimum, calendar invites should match
    calendar_events = [
        e for e in event_emails
        if "calendar" in e["from_email"].lower()
    ]

    calendar_matches = sum(
        1 for e in calendar_events
        if type_mapper.get_deterministic_type(
            extract_domain(e["from_email"]),
            e["subject"],
            e["snippet"]
        ) is not None
    )

    assert calendar_matches >= len(calendar_events) * 0.9, \
        "At least 90% of calendar invites should match type mapper rules"


def test_calendar_notification_is_event():
    """Specific test for the known drift case."""

    test_cases = [
        {
            "from": "calendar-notification@google.com",
            "subject": "Notification: Team Sync @ Wed Nov 13, 2pm – 3pm (PST)",
            "snippet": "You have a calendar event...",
            "expected_type": "event"
        },
        {
            "from": "noreply@calendar.google.com",
            "subject": "Updated invitation: Project Review",
            "snippet": "The details of this event have changed...",
            "expected_type": "event"
        },
        {
            "from": "events@eventbrite.com",
            "subject": "Invitation: Tech Conference 2025",
            "snippet": "You're invited to Tech Conference...",
            "expected_type": "event"
        }
    ]

    type_mapper = get_type_mapper()

    for case in test_cases:
        result = type_mapper.get_deterministic_type(
            case["from"],
            case["subject"],
            case["snippet"]
        )

        assert result is not None, f"Should match: {case['subject']}"
        assert result["type"] == case["expected_type"], \
            f"Expected {case['expected_type']}, got {result['type']}"
```

### 2. Type Corrector Tests

```python
# tests/test_type_corrector.py (NEW)

def test_post_llm_correction():
    """Verify type corrector fixes LLM drift."""

    type_mapper = get_type_mapper()

    # Simulate LLM misclassification
    llm_result = {
        "type": "notification",  # ❌ Wrong
        "type_conf": 0.85,
        "decider": "gemini"
    }

    corrected = type_mapper.correct_type_if_needed(
        llm_result,
        sender_domain="calendar-notification@google.com",
        subject="Notification: Meeting @ Wed",
        snippet="You have a calendar event"
    )

    assert corrected["type"] == "event", "Should correct to event"
    assert corrected["decider"] == "type_corrector"
    assert "corrected from notification" in corrected["reason"]
```

### 3. End-to-End Integration Test

```python
# tests/test_memory_classifier_type_mapper.py (NEW)

def test_type_mapper_integration():
    """Full flow: new user gets calendar invite."""

    classifier = MemoryClassifier()

    result = classifier.classify(
        subject="Notification: Team Sync @ Wed Nov 13, 2pm",
        snippet="You have a calendar event: Team Sync...",
        from_field="calendar-notification@google.com",
        user_id="brand_new_user"  # Empty rules DB
    )

    # Type mapper should kick in immediately
    assert result["type"] == "event"
    assert result["type_conf"] >= 0.95
    assert result["decider"] in ["type_mapper", "type_corrector"]

    # Gmail labels should reflect event type
    assert "ShopQ-Events" in result["gmail_labels"]
```

---

## Implementation Timeline (3-5 days)

### Day 1: Foundation
- [ ] Create `config/type_mapper_rules.yaml` with initial rules
  - Event rules (calendar domains, subject patterns)
  - Receipt rules (Amazon, PayPal)
  - Basic notification rules
- [ ] Implement `shopq/type_mapper.py` (TypeMapper class)
- [ ] Unit tests for rule matching (domain wildcards, regex, phrases)

### Day 2: Integration
- [ ] Integrate into `memory_classifier.py`
  - Add Phase 0 (deterministic type check)
  - Add Phase 2.5 (post-LLM correction)
- [ ] Modify `vertex_gemini_classifier.py`
  - Add `type_override` parameter
  - Skip type classification if override provided
- [ ] Add helper: `extract_domain(from_field)` utility

### Day 3: Testing
- [ ] Write gds-1.0 regression tests
  - All 56 events typed correctly
  - Calendar invites match type mapper rules
- [ ] Write type corrector tests
  - Post-LLM correction works
- [ ] End-to-end integration tests
  - New user gets calendar invite → type=event

### Day 4: Validation
- [ ] Run full gds-1.0 dataset through new pipeline
- [ ] Measure type consistency (before/after metrics)
  - Before: X% calendar invites → notification
  - After: 100% calendar invites → event
- [ ] Check for regressions (other types shouldn't change)

### Day 5: Polish & Deploy
- [ ] Add logging/telemetry for type mapper hits
- [ ] Document in `ARCHITECTURE.md`
- [ ] Update `CLASSIFICATION_REFACTOR_PLAN.md` (Phase B0 complete)
- [ ] Deploy to staging, monitor logs

---

## Acceptance Criteria

### Must Have (Blocking)
- ✅ All calendar invites from `calendar-notification@google.com` → `type=event`
- ✅ Type mapper rules pass gds-1.0 regression (≥90% calendar match rate)
- ✅ No regressions in other types (receipts, promotions, etc.)
- ✅ Works for brand new users (zero rules in DB)
- ✅ Post-LLM corrector fixes known drift cases

### Should Have (High Priority)
- ✅ Logging shows type mapper hit rate (% of emails matched)
- ✅ CI tests enforce type consistency on golden set
- ✅ Documentation updated in ARCHITECTURE.md
- ✅ Config file versioned (v1.0)

### Nice to Have (Future)
- 🔄 Web UI to view/edit type mapper rules
- 🔄 User overrides (per-user type mapper exceptions)
- 🔄 A/B test to measure impact on user satisfaction

---

## Risk Mitigation

### Risk: Type mapper is too aggressive
**Mitigation**: High precision threshold (≥95% confidence), only match obvious cases

### Risk: New users get worse classifications
**Mitigation**: Type mapper is additive (doesn't remove LLM fallback), A/B test before full rollout

### Risk: Rules go stale over time
**Mitigation**: Rules are version-controlled, monthly review against golden set

### Risk: Performance impact
**Mitigation**: Type mapper is in-memory regex (<<1ms), no DB queries or LLM calls

---

## Metrics to Track

### Before/After Comparison

| Metric | Before | After (Target) |
|--------|--------|----------------|
| Calendar invites → event | ~70% | ≥95% |
| Type mapper hit rate | 0% | 15-25% |
| LLM calls for type | 100% | 75-85% |
| New user first-email accuracy | ~85% | ≥90% |

### Ongoing Monitoring

- **Type mapper match rate**: % of emails matched by deterministic rules
- **Type corrector hit rate**: % of LLM results corrected post-hoc
- **Type consistency score**: % of calendar invites typed as event (monthly)
- **False positive rate**: % of non-events incorrectly typed as event

---

## Rollback Plan

1. **Feature flag**: `ENABLE_TYPE_MAPPER=false` in config
2. **Gradual rollout**: 10% → 50% → 100% users
3. **Instant revert**: Remove type mapper calls from memory_classifier.py
4. **No data loss**: Type mapper is stateless (no DB changes)

---

## Future Enhancements (Post-Launch)

### Phase 2: Receipt/Notification Rules
- Add deterministic rules for receipts (Amazon, PayPal, etc.)
- Add notification rules (shipping status, password resets)

### Phase 3: User Overrides
- Allow users to override type mapper rules
- Store in user_prefs table (per-user customization)

### Phase 4: Learning Integration
- Feed type mapper corrections back into prompt examples
- Auto-suggest new rules based on frequent corrections

### Phase 5: Temporal Extraction
- Extend type mapper to extract temporal fields
- Parse event_start from calendar subjects
- Aligns with GPT-5 temporal framework Phase 1

---

## References

- **Classification Refactor Plan**: `CLASSIFICATION_REFACTOR_PLAN.md` (Phase B0, P2)
- **GPT-5 Temporal Framework**: `GPT5_TEMPORAL_POLICY_SUMMARY.md` (Type Normalization #4)
- **Stage 1/Stage 2 Contracts**: `STAGE_1_STAGE_2_CONTRACTS.md`
- **Golden Dataset**: `tests/golden_set/gds-1.0.csv` (56 events for testing)
- **Architecture Diagram**: `ARCHITECTURE.md` (memory_classifier flow)

---

## Decision Log

**2025-11-10**: Created TYPE_CONSISTENCY_PLAN.md
- **Why**: Calendar invites inconsistently typed as notification vs event
- **Approach**: Global deterministic type mapper (not user-specific)
- **Aligns with**: GPT-5 type normalization, gds-1.0 contracts, existing rules-first philosophy

---

**Status**: ✅ **Ready for Implementation**
**Next Action**: Create `config/type_mapper_rules.yaml` + implement `shopq/type_mapper.py`

---

*Generated: 2025-11-10*
*ShopQ Type Consistency Enhancement*
