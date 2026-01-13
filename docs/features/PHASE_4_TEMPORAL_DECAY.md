# Phase 4: Deterministic Temporal Decay

**Status**: ✅ Implemented & Tested (33/33 tests passing)
**Module**: `shopq/temporal_decay.py`
**Tests**: `tests/test_temporal_decay.py`
**Schema**: gds-1.0 (see `tests/golden_set/GDS_SCHEMA_v1.0.md`)

---

## Overview

Phase 4 implements **deterministic temporal decay** — a post-LLM rule system that modulates email importance based on objective time windows, not LLM judgment.

**Key Principle**: "How much this message matters **now**" should be predictable and transparent.

### The Problem This Solves

Without temporal decay:
- ❌ Lunch invitation at 1:30pm appears in "Coming Up" at 2:00pm (expired)
- ❌ Meeting in 30 minutes stays as "routine" (needs escalation)
- ❌ Flight confirmation 2 weeks away clutters "Time-Sensitive" section
- ❌ Users lose trust when digest shows stale events

With temporal decay:
- ✅ Expired events (>1h past end) → downgraded to routine, hidden from digest
- ✅ Imminent events (±1h) → escalated to critical ("Now" section)
- ✅ Upcoming events (≤7d) → escalated to time_sensitive ("Coming Up")
- ✅ Distant events (>7d) → downgraded to routine unless LLM overrode

---

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│ Phase 3: LLM Classification                                  │
│ ↓                                                             │
│ Output: {type: "event", importance: "routine", ...}          │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│ Phase 4: Deterministic Temporal Decay (shopq/temporal_decay)│
│                                                              │
│ Input:  stored_importance, temporal_start, temporal_end     │
│ Rules:  4 deterministic time-based rules (no LLM)           │
│ Output: resolved_importance, decay_reason, was_modified     │
└──────────────────────────────────────────────────────────────┘
                            ↓
┌──────────────────────────────────────────────────────────────┐
│ Digest Rendering                                             │
│ ↓                                                             │
│ • resolved_importance → digest section                       │
│ • should_show_in_digest() → hide expired events             │
│ • Store audit trail: stored vs resolved + reason            │
└──────────────────────────────────────────────────────────────┘
```

---

## The 4 Deterministic Rules

Applied in priority order:

### Rule 1: Expired → Routine
**Condition**: `temporal_end < now - 1 hour`
**Action**: `resolved_importance = "routine"`, hide from digest
**Grace Period**: 1 hour (allows late digests to still show "just-missed" events)

**Examples**:
- Lunch ended 2h ago → routine, archived
- Meeting ended 30 min ago → still shown (within grace period)

### Rule 2: Active Now → Critical
**Condition**: `now - 1h ≤ temporal_start ≤ now + 1h` AND event hasn't ended
**Action**: `resolved_importance = "critical"` (escalate from any stored importance)
**Window**: ±1 hour (starting soon or in progress)

**Examples**:
- Meeting in 30 minutes → critical ("Now" section)
- Lunch starting now → critical
- Deadline due in 45 minutes → critical

### Rule 3: Upcoming ≤7 Days → Time-Sensitive
**Condition**: `now + 1h < temporal_start ≤ now + 7 days`
**Action**: `resolved_importance = max(stored, "time_sensitive")` (escalate routine, preserve critical)
**Window**: 1 hour to 7 days ahead

**Examples**:
- Dinner tomorrow → time_sensitive ("Coming Up" section)
- Bill due Friday (3 days) → time_sensitive
- Flight in 5 days → time_sensitive

### Rule 4: Distant >7 Days → Routine (Unless Critical)
**Condition**: `temporal_start > now + 7 days`
**Action**: `resolved_importance = "routine"` (unless LLM said critical)
**Exception**: Preserve critical for urgent distant events (e.g., flight cancellation notice)

**Examples**:
- Flight in 2 weeks → routine ("Worth Knowing" section)
- Conference in 30 days → routine
- Flight cancellation in 2 weeks → critical (LLM override preserved)

---

## Usage

### Basic Usage

```python
from datetime import datetime, timedelta, timezone
from shopq.temporal_decay import resolve_temporal_importance

# Current time
now = datetime.now(timezone.utc)

# Event starting in 30 minutes (escalate to critical)
result = resolve_temporal_importance(
    email_type="event",
    stored_importance="routine",  # What LLM classified
    temporal_start=now + timedelta(minutes=30),
    temporal_end=now + timedelta(hours=1, minutes=30),
    now=now
)

print(result.resolved_importance)  # "critical"
print(result.decay_reason)         # "temporal_active"
print(result.was_modified)         # True (escalated from routine)
```

### Integration with Digest

```python
from shopq.temporal_decay import (
    resolve_temporal_importance,
    should_show_in_digest,
    get_digest_section
)

# After LLM classification
for email in classified_emails:
    # Apply temporal decay
    decay_result = resolve_temporal_importance(
        email_type=email.type,
        stored_importance=email.importance,
        temporal_start=email.temporal_start,
        temporal_end=email.temporal_end
    )

    # Store both for audit trail
    email.stored_importance = email.importance  # Original LLM decision
    email.resolved_importance = decay_result.resolved_importance
    email.decay_reason = decay_result.decay_reason

    # Decide if should appear in digest
    if should_show_in_digest(
        email.type,
        decay_result.resolved_importance,
        email.temporal_end
    ):
        # Get digest section
        section = get_digest_section(decay_result.resolved_importance)
        email.digest_section = section  # "TODAY", "COMING_UP", "WORTH_KNOWING"
    else:
        # Expired event - hide or archive
        email.digest_section = "ARCHIVED"
```

### Legacy Function Name

For backward compatibility with existing code:

```python
from shopq.temporal_decay import deterministic_temporal_updownrank

importance, reason = deterministic_temporal_updownrank(
    email_type="event",
    stored_importance="routine",
    temporal_start=now + timedelta(minutes=30),
    temporal_end=now + timedelta(hours=1, minutes=30)
)
# Returns: ("critical", "temporal_active")
```

---

## Data Model

### Input Fields (from gds-1.0 schema)

```python
{
    "type": "event|deadline|notification|...",
    "importance": "critical|time_sensitive|routine",
    "temporal_start": "2025-11-10T14:30:00Z",  # ISO 8601 UTC
    "temporal_end": "2025-11-10T15:30:00Z"     # ISO 8601 UTC (None for deadlines)
}
```

### Output Fields (for database/audit)

```python
{
    # Preserve original LLM classification
    "stored_importance": "routine",
    "stored_type": "event",

    # Resolved after temporal decay
    "resolved_importance": "critical",
    "decay_reason": "temporal_active",
    "decayed_at": "2025-11-10T14:00:00Z",
    "was_modified": true,

    # For digest rendering
    "digest_section": "TODAY",
    "show_in_digest": true
}
```

---

## Testing

### Run Tests

```bash
PYTHONPATH=/Users/justinkoufopoulos/Projects/mailq-prototype \
  uv run pytest tests/test_temporal_decay.py -v
```

**Test Coverage**: 33 tests covering:
- ✅ Expired events (Rule 1)
- ✅ Active events (Rule 2)
- ✅ Upcoming events (Rule 3)
- ✅ Distant events (Rule 4)
- ✅ Non-temporal types (notifications, receipts, promos)
- ✅ Missing temporal data
- ✅ Digest visibility logic
- ✅ Timezone handling
- ✅ Regression suite from gds-1.0

### Example Test Cases

```python
def test_expired_event_hidden():
    """Lunch ended 2h ago should be hidden from digest."""
    result = resolve_temporal_importance(
        "event", "time_sensitive",
        now - timedelta(hours=3),
        now - timedelta(hours=2),
        now
    )
    assert result.resolved_importance == "routine"
    assert not should_show_in_digest("event", "routine", now - timedelta(hours=2), now)

def test_meeting_in_30_min_critical():
    """Meeting in 30 min should escalate to critical."""
    result = resolve_temporal_importance(
        "event", "routine",
        now + timedelta(minutes=30),
        now + timedelta(hours=1, minutes=30),
        now
    )
    assert result.resolved_importance == "critical"
    assert get_digest_section("critical") == "TODAY"
```

---

## Digest Section Mapping

| Resolved Importance | Digest Section | User-Facing Label |
|---------------------|----------------|-------------------|
| `critical` | `TODAY` | "Now" or "Today" |
| `time_sensitive` | `COMING_UP` | "Coming Up" (next 7 days) |
| `routine` | `WORTH_KNOWING` | "Worth Knowing" |
| (expired) | `ARCHIVED` | Hidden from digest |

---

## Grace Periods & Windows

| Parameter | Value | Rationale |
|-----------|-------|-----------|
| **Expired grace** | 1 hour | Late digests can still show "just-missed" events politely |
| **Active window** | ±1 hour | Captures "starting soon" and "in progress" |
| **Upcoming horizon** | 7 days | Maps to "Coming Up" section in digest |
| **Distant threshold** | >7 days | Events too far out to matter now |

---

## Monotonicity Guarantee

Temporal decay is **monotonic** (never downgrades without expiration):
- `routine` → `time_sensitive` → `critical` (escalations allowed)
- `critical` → `routine` (only if expired >1h)
- `time_sensitive` → `routine` (only if expired or >7d)

**Why**: Prevents temporal decay from overruling critical LLM decisions (e.g., flight cancellation notice 2 weeks out should stay critical)

---

## Audit Trail

Always store both values for debugging and transparency:

```python
# Before
importance: "routine"  # LLM said routine

# After temporal decay
stored_importance: "routine"       # What LLM said
resolved_importance: "critical"    # What we show in digest
decay_reason: "temporal_active"    # Why we changed it
was_modified: true                 # Flag for monitoring
decayed_at: "2025-11-10T14:00:00Z" # When decay happened
```

**Benefits**:
- Debug LLM vs temporal decisions
- Monitor escalation/downgrade rates
- A/B test temporal window thresholds
- Explain decisions to users

---

## Future Extensions

### Phase 5: Recency Boost (Planned)
Combine temporal decay with recency signals:
- Recent thread update + upcoming event → extra boost
- Old thread + distant event → extra downgrade

### Phase 6: User Feedback Loop (Planned)
Learn user-specific temporal preferences:
- User dismisses events >3 days → tighten upcoming horizon to 3 days
- User clicks events 10-14 days out → widen horizon to 14 days

### Phase 7: Timezone-Aware Decay (Future)
Use user's local timezone for "today" calculations:
- Event at 11pm UTC might be "tomorrow" in user's timezone
- Requires user timezone in profile

---

## Integration Checklist

To integrate Phase 4 temporal decay into your pipeline:

- [ ] After LLM classification, call `resolve_temporal_importance()`
- [ ] Store both `stored_importance` and `resolved_importance`
- [ ] Store `decay_reason` for audit trail
- [ ] Use `should_show_in_digest()` to filter expired events
- [ ] Use `get_digest_section()` to map to digest sections
- [ ] Add CI test: no expired events in "Now" or "Coming Up"
- [ ] Monitor `was_modified` rate (expect ~10-20% of events modified)
- [ ] Log temporal decisions for quality monitoring

---

## Monitoring & Alerts

### Key Metrics

**Escalation Rate**: % of emails where `resolved > stored`
- **Target**: 10-15% (mostly events/deadlines ≤7d)
- **Alert**: >30% (too aggressive) or <5% (not working)

**Downgrade Rate**: % of emails where `resolved < stored`
- **Target**: 5-10% (mostly expired events, distant >7d)
- **Alert**: >20% (too aggressive) or <2% (not working)

**Expired Hidden**: % of events hidden via `should_show_in_digest()`
- **Target**: 1-3% (depends on digest frequency)
- **Alert**: >10% (digest too late) or 0% (hiding not working)

### Logging

```python
logger.info(
    "temporal_decay_applied",
    email_id=email.id,
    stored_importance=email.stored_importance,
    resolved_importance=result.resolved_importance,
    decay_reason=result.decay_reason,
    was_modified=result.was_modified,
    temporal_start=email.temporal_start,
    temporal_end=email.temporal_end,
    time_until_start=email.temporal_start - now
)
```

---

## Summary

**What Phase 4 Does**:
- ✅ Prevents expired events from appearing as time_sensitive
- ✅ Escalates imminent events to critical automatically
- ✅ Downranks distant events to routine unless LLM overrode
- ✅ Maintains audit trail (stored vs resolved importance)
- ✅ Provides digest visibility logic (hide expired events)

**What It Doesn't Do**:
- ❌ Override type classification (type stays "event", "deadline", etc.)
- ❌ Extract temporal fields (that's Phase 3 LLM output)
- ❌ Learn user preferences (that's Phase 6)

**Status**: Production-ready, fully tested, schema-aligned with gds-1.0

**Next Steps**: Integrate into digest pipeline after Phase 3 LLM classification 🚀
