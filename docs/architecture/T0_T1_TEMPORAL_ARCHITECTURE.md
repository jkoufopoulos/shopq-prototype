# T0→T1 Temporal Architecture

**Status:** ACTIVE in production (as of Nov 2025)
**Last Updated:** Nov 30, 2025
**Owner:** ShopQ Core Team

> **Canonical Reference**: See [T0_T1_IMPORTANCE_CLASSIFICATION.md](../features/T0_T1_IMPORTANCE_CLASSIFICATION.md) for the definitive T0/T1 terminology and rules.

## Overview

ShopQ uses a **two-stage temporal classification system** to separate **intrinsic email properties** (T0) from **time-based relevance** (T1).

## Terminology Clarification

**T0 = Importance Values** (intrinsic, observer-independent):
- `critical` - Real-world risk if ignored (fraud, security, OTPs)
- `time_sensitive` - Has deadline or event
- `routine` - No urgency

**T1 = Digest Sections** (time-adjusted, observer-dependent):
- `critical` / `today` - Within 24h or security alerts
- `coming_up` - Events 1-7 days out
- `worth_knowing` - Informational, >7 days
- `everything_else` - Receipts, newsletters
- `skip` - Expired/irrelevant

**Key Insight**: T0 is about IMPORTANCE, T1 is about DIGEST SECTIONS. Don't conflate them.

## Why T0→T1 Separation?

### The Problem
Email relevance changes over time:
- An event invitation is "important" when received, but becomes "irrelevant" after the event passes
- A delivery notification is "urgent" today, but becomes "archived" tomorrow
- An OTP code is "critical" for 10 minutes, then becomes "noise"

### The Solution
Separate WHAT an email IS (T0 importance) from WHERE to show it (T1 section):

```
T0 (Importance)             T1 (Digest Section)
├─ critical      ──────────→ critical (OTPs skip digest entirely)
├─ time_sensitive ─────────→ today | coming_up | worth_knowing (by time distance)
└─ routine       ──────────→ everything_else | skip (by relevance)
```

## Architecture Flow

```
┌─────────────────────────────────────────────────────────────┐
│ Email: "Invitation: Dinner @ Fri Nov 21, 2025 6:30pm"      │
│ Received: Nov 10, 2025                                      │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 1: Extract Temporal Context                           │
│ Output: temporal_ctx = {                                    │
│   "event_time": datetime(2025, 11, 21, 18, 30)             │
│ }                                                            │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 2: Assign T0 Section (Intrinsic)                      │
│ Function: assign_section_t0(email, temporal_ctx)            │
│                                                              │
│ Logic:                                                       │
│ - Has event_time? → This IS an event                        │
│ - Subject contains "invitation"? → T0 = "today"             │
│                                                              │
│ Key: NO comparison to current time (now)                    │
│ Output: T0 section = "today"                                │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ Stage 3: Apply Temporal Decay (T0 → T1)                     │
│ Function: apply_temporal_decay(T0, temporal_ctx, now)       │
│                                                              │
│ Logic:                                                       │
│ - T0 = "today"                                               │
│ - event_time = Nov 21                                        │
│ - now = Nov 10                                               │
│ - days_until = 11 days                                       │
│ - 11 days > 7 days → T1 = "coming_up"                        │
│                                                              │
│ Key: DOES compare to current time                           │
│ Output: T1 section = "coming_up"                            │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ Digest: Email appears in "Coming Up" section                │
└─────────────────────────────────────────────────────────────┘
```

## Key Principles

### 1. T0 = Intrinsic Importance (What It IS)

**File:** `shopq/classification/memory_classifier.py`
**Output:** `importance` field in classification result

**Values:**
- `critical` - Security alerts, OTPs, fraud warnings
- `time_sensitive` - Events, deadlines, deliveries
- `routine` - Newsletters, receipts, confirmations

**Rules:**
- ✅ CAN use email content to identify type (event, delivery, receipt)
- ❌ CANNOT use current time (no "is this happening soon?" logic)
- ✅ Returns intrinsic importance based on WHAT the email is

**Examples:**
```python
# Event with event_time → "time_sensitive" (it HAS a deadline)
# Receipt with purchase_date → "routine" (it IS informational)
# Fraud alert → "critical" (it REQUIRES attention)
```

**Rationale:**
- Testable without mocking time
- Provides ground truth for GDS evaluation
- Can be labeled by humans without considering when they're viewing it

### 2. T1 = Time-Based Digest Sections (Where to Show It)

**File:** `shopq/digest/temporal.py`
**Function:** `apply_temporal_decay(t0_importance, temporal_ctx, now)`

**Input:** T0 importance (`critical`, `time_sensitive`, `routine`)
**Output:** T1 digest section (`critical`, `today`, `coming_up`, `worth_knowing`, `everything_else`, `skip`)

**Rules:**
- ✅ MUST use `now` parameter for time comparisons
- ✅ Takes T0 importance as input (NOT section)
- ✅ Returns digest section based on relevance timing

**Decay Rules:**
```python
# OTPs are critical (T0) but skip digest (T1) - they expire too fast
if email.type == "otp":
    return "skip"

# Security alerts stay critical
if t0_importance == "critical" and email.type != "otp":
    return "critical"

# Events/deadlines decay based on time distance
if t0_importance == "time_sensitive" and event_time:
    hours_until = (event_time - now).total_seconds() / 3600

    if hours_until < -1:       # >1h in past
        return "skip"           # Expired
    elif hours_until <= 24:    # Within 24h
        return "today"          # Happening soon
    elif days_until <= 7:      # 1-7 days out
        return "coming_up"      # Future event
    else:                      # >7 days out
        return "worth_knowing"  # Too far to prioritize

# Routine emails go to everything_else
if t0_importance == "routine":
    return "everything_else"
```

**Rationale:**
- Shows emails at the right time
- Hides expired content
- Surfaces upcoming events as they approach

## Implementation Details

### Pipeline Stages

**Located:** `shopq/digest/digest_stages_v2.py`

```python
pipeline = DigestPipeline([
    # Stage 1: Classification (T0 importance from LLM/rules)
    # - Output: email["importance"] = "critical" | "time_sensitive" | "routine"
    # - Source: memory_classifier.py

    # Stage 2: Extract temporal entities
    TemporalContextExtractionStage(),
    # - Output: temporal_ctx = {event_time, delivery_date, ...}

    # Stage 3: Assign T0 sections (intrinsic, based on email properties)
    SectionAssignmentT0Stage(),
    # - Uses: email["importance"], email["type"], temporal_ctx
    # - Output: context.section_assignments_t0[email_id]

    # Stage 4: Apply temporal decay (T0 → T1)
    TemporalDecayStage(),
    # - Uses: t0_sections, temporal_ctx, now
    # - Output: context.section_assignments[email_id] (T1 sections)

    # Remaining stages use T1 sections for rendering
    ...
])
```

### Temporal Context Structure

```python
temporal_ctx = {
    "event_time": datetime | None,      # When event starts
    "event_end_time": datetime | None,  # When event ends
    "delivery_date": datetime | None,   # When package delivered/arriving
    "purchase_date": datetime | None,   # When purchase was made
    "expiration_date": datetime | None, # When something expires
}
```

**Important:** `temporal_ctx` contains **intrinsic timestamps** (when things happen), not evaluation timestamps (when we're viewing the email).

## Common Confusions

### ❌ "T0 should never use temporal_ctx"

**Wrong.** T0 SHOULD use `temporal_ctx` to identify what the email is:
- Has `event_time`? → It's an event → T0 = "today"
- Has `delivery_date`? → It's a delivery → Check urgency signals
- Has `purchase_date`? → It's a receipt → Check if experiential

T0 just can't use `now` to compare timestamps.

### ❌ "T1 is just filtering expired events"

**Wrong.** T1 does more than filtering:
- **Promotion:** Event in 30 minutes → upgrade to "critical"
- **Demotion:** Event in 10 days → downgrade to "worth_knowing"
- **Filtering:** Event 2 days ago → mark as "skip"

### ❌ "We have two competing temporal systems"

**False.** There are two COMPLEMENTARY layers (by design):
1. **Classification layer** (`classification/temporal.py`) - modulates T0 IMPORTANCE (`critical|time_sensitive|routine`)
2. **Digest layer** (`digest/temporal.py`) - modulates T1 SECTION (`today|coming_up|worth_knowing|skip`)

These are NOT duplicates - they serve different purposes:
- Classification temporal: Adjusts importance BEFORE digest generation
- Digest temporal: Assigns sections based on importance + time distance + content type

**Correct flow:**
```
Email → classify() → importance (T0)
      → extract_temporal_context() → temporal_ctx
      → apply_temporal_decay(importance, temporal_ctx, now) → section (T1)
```

## Files Reference

| File | Purpose | Used By |
|------|---------|---------|
| `classification/memory_classifier.py` | T0 importance classification | Main pipeline |
| `classification/temporal.py` | T0 importance modulation (temporal adjustments) | Classification pipeline |
| `digest/temporal.py` | T1 section assignment + context extraction | Digest pipeline |
| `digest/section_assignment.py` | ⚠️ DEPRECATED | Remove after tests updated |

**Note:** `classification/temporal.py` and `digest/temporal.py` are NOT duplicates:
- `classification/temporal.py` → Adjusts `importance` field (e.g., expired event → routine)
- `digest/temporal.py` → Assigns `section` (e.g., event tomorrow → today section)

## Testing

### T0 Tests (Intrinsic Importance)

```python
def test_event_importance():
    """Event with deadline should be T0 importance=time_sensitive"""
    result = classifier.classify(
        subject="Dinner tonight @ 6pm",
        snippet="You're invited",
        from_field="friend@example.com"
    )

    # NO current time comparison in classification
    assert result["importance"] == "time_sensitive"  # Has a deadline
```

### T1 Tests (Digest Section Assignment)

```python
def test_distant_event_section():
    """Event >7 days out should be in coming_up section, not today"""
    t0_importance = "time_sensitive"
    temporal_ctx = {"event_time": datetime(2025, 11, 21, 18, 30)}
    now = datetime(2025, 11, 10, 10, 0)  # 11 days before event

    t1_section = apply_temporal_decay(t0_importance, temporal_ctx, now)

    assert t1_section == "coming_up"  # Demoted due to time distance
```

## Known Issues & TODOs

### 1. Duplicate Temporal Systems

**Problem:** Both `classification/temporal.py` and `digest/temporal.py` apply temporal decay.

**Solution:** Merge classification temporal INTO digest temporal.

**Tracking:** [Issue #TODO]

### 2. Confusing Naming

**Problem:** `temporal_ctx` is used in both T0 (intrinsic) and T1 (time-based), causing confusion.

**Solution:**
- Rename `temporal_ctx` → `entity_context` (emphasizes WHAT, not WHEN)
- Rename `assign_section_t0()` → `assign_intrinsic_section()`
- Rename `apply_temporal_decay()` → `apply_time_based_adjustment()`

**Tracking:** [Issue #TODO]

### 3. Legacy Code Still Present

**Problem:** `section_assignment.py` combines T0+T1 in one function, but tests still use it.

**Solution:**
- Update tests to use T0+T1 separately
- Mark `section_assignment.py` as deprecated
- Remove after 6 months

**Tracking:** [Issue #TODO]

## Migration Guide

### If You're Writing New Code

✅ **DO:**
- Use `assign_section_t0()` for intrinsic classification
- Use `apply_temporal_decay()` for time-based adjustments
- Keep T0 and T1 separate

❌ **DON'T:**
- Use `assign_section()` from `section_assignment.py` (deprecated)
- Mix intrinsic and time-based logic in one function
- Pass `now` parameter to T0 functions

### If You're Fixing Tests

✅ **DO:**
- Test T0 independently (no time mocking needed)
- Test T1 with different `now` values
- Validate T0→T1 transformations

❌ **DON'T:**
- Test T0 and T1 together (defeats the separation)
- Hard-code time expectations in T0 tests

## References

- **Pipeline Implementation:** `shopq/digest/digest_stages.py` lines 180-290
- **T0 Implementation:** `shopq/digest/section_assignment_t0.py`
- **T1 Implementation:** `shopq/digest/temporal.py` lines 402-586
- **Ground Truth Annotations:** `tests/golden_set/` (T0 labels)
- **Evaluation Scripts:** `scripts/evaluate_t0_accuracy.py`, `scripts/evaluate_t1_timing.py`

## Questions?

Contact: ShopQ Core Team
Last reviewed: Nov 25, 2025
