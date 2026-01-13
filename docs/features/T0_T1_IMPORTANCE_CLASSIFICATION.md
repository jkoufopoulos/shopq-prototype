# T0/T1 Importance Classification

**Status**: ✅ Active Architecture (Canonical Reference)
**Created**: November 2025
**Last Updated**: November 30, 2025
**Purpose**: Define the two-stage importance classification system

> **Related**: For temporal decay implementation details, see [T0_T1_TEMPORAL_ARCHITECTURE.md](../architecture/T0_T1_TEMPORAL_ARCHITECTURE.md)

---

## Core Concept

MailQ uses a **two-stage importance classification** system to separate intrinsic email properties from time-dependent context:

- **T0 (Intrinsic Importance)**: What the email IS, independent of when it's observed
- **T1 (Time-Adjusted Importance)**: What the email MEANS right now, considering current time

---

## T0: Intrinsic Importance (Observer-Independent)

### Definition

**T0 answers**: "What is the intrinsic urgency of this email?"

T0 importance is **observer-independent** — the same regardless of when you evaluate it.

### Values

| Value | Definition | Examples |
|-------|------------|----------|
| **critical** | Real-world risk if ignored | Fraud alerts, suspicious login, security breaches, **OTPs** |
| **time_sensitive** | Has a deadline or event within timeframe | Calendar events, deliveries, bills due, appointments |
| **routine** | No urgency or deadline | Newsletters, receipts, confirmations, account updates |

### Rules

1. **OTPs are ALWAYS critical** (T0)
   - They expire in minutes
   - Require immediate action
   - Example: "Your verification code is 123456"

2. **Events/deadlines are time_sensitive** (T0)
   - Calendar notifications: "Meeting @ Fri Nov 21, 2025 6:30pm"
   - Delivery notifications: "Package arriving today"
   - Bill reminders: "Payment due Nov 12"

3. **Informational emails are routine** (T0)
   - Receipts: "Your Uber Eats order"
   - Confirmations: "Order #123 shipped"
   - Newsletters: "Weekly roundup"

### Implementation

**Module**: `mailq/classification/memory_classifier.py`
**Output**: `importance` field in classification result

```python
from mailq.classification.memory_classifier import MemoryClassifier

classifier = MemoryClassifier()
result = classifier.classify(
    subject="Invitation: Dinner @ Fri Nov 21, 2025 6:30pm",
    snippet="Join us for dinner",
    from_field="friend@example.com"
)

# T0 output
print(result['importance'])  # "time_sensitive"
```

**Key Point**: This is the **ONLY** output from the classifier. It doesn't change based on when you run it.

---

## T1: Time-Adjusted Importance (Observer-Dependent)

### Definition

**T1 answers**: "How urgent is this email **right now**?"

T1 importance is **observer-dependent** — changes based on evaluation time.

### Rules

T1 is derived from T0 + temporal context + current time:

#### 1. OTPs → Never in Digest
```python
if email.type == "otp":
    return None  # OTPs expire in minutes, useless by digest time
```

**Critical Constraint**: OTPs should NEVER appear in the digest because:
- They expire in minutes (not hours/days)
- By digest generation time, they're useless
- They trigger real-time notifications, not digest inclusion

#### 2. Temporal Urgency (Events/Deadlines)
```python
if T0 == "time_sensitive":
    time_until_event = event_time - now

    if time_until_event <= 0 and expired > 1h:
        return "routine"  # Expired → downgrade
    elif -1h <= time_until_event <= 1h:
        return "critical"  # Happening now → escalate
    elif 1h < time_until_event <= 7d:
        return "time_sensitive"  # Coming up → preserve
    elif time_until_event > 7d:
        return "routine"  # Too far out → downgrade
```

#### 3. Consequence-Based Urgency (Action Required)
```python
if client_label == "action-required" and not is_expired(email):
    return "critical"  # Inaction has consequences
```

**Examples**:
- Failed payment requiring fix
- Subscription cancellation warning
- Service interruption notice

#### 4. Intrinsic Urgency (Security)
```python
if T0 == "critical" and type != "otp":
    return "critical"  # Preserve critical (fraud, security)
```

### Implementation

**Module**: `mailq/digest/temporal_decay.py`
**Output**: T1 section for digest

```python
from mailq.digest.temporal_decay import apply_temporal_decay

# T0 classification
t0_section = "today"  # Event is time_sensitive (T0)

# T1 adjustment
t1_section = apply_temporal_decay(
    t0_section=t0_section,
    email=email,
    temporal_ctx={"event_time": datetime(2025, 11, 21, 18, 30)},
    now=datetime(2025, 11, 9, 14, 0)  # 12 days before event
)

print(t1_section)  # "worth_knowing" (>7 days out)
```

---

## Digest Section Mapping (T1 → User-Facing Sections)

| T1 Value | Digest Section | User Label | Inclusion Rule |
|----------|----------------|------------|----------------|
| **critical** | TODAY / URGENT | "Now" or "Action Required" | Temporal urgency (0-24h) OR intrinsic urgency (fraud) OR consequence urgency (action-required) |
| **time_sensitive** | COMING UP | "Coming Up" | Events/deadlines 1-7 days out |
| **routine** | WORTH KNOWING | "Worth Knowing" | Informational content >7 days out OR no deadline |
| **skip** | (hidden) | — | Expired events, OTPs |

### TODAY / URGENT Section (T1 = critical)

Three types of urgency:

1. **Temporal urgency**: Events within 24 hours
   - Example: "1pm call today", "Flight boarding in 2h"

2. **Intrinsic urgency**: Security/fraud (NOT OTPs)
   - Example: "Unusual activity on your account"

3. **Consequence-based urgency**: Action required with consequences
   - Example: "Failed payment - verify bank account"
   - Example: "Subscription ending in 3 days unless renewed"

---

## GDS Ground Truth Annotations

### GDS Contains T0 Labels

**Critical**: GDS labels are **T0 (intrinsic importance)**, NOT T1.

**Rationale**:
- GDS is meant to be a stable, reusable dataset
- T1 labels would change every time we evaluate (observer-dependent)
- T0 labels are **observer-agnostic** — same for all evaluators

### Example

```
Email: "Invitation: Dinner @ Fri Nov 21, 2025 6:30pm"
GDS Label (T0): time_sensitive

Evaluation on Nov 9, 2025:
  Classifier Output (T0): time_sensitive ✅ MATCH
  Temporal Decay (T1): worth_knowing (12 days out)

Evaluation on Nov 20, 2025:
  Classifier Output (T0): time_sensitive ✅ MATCH
  Temporal Decay (T1): today (within 24h)
```

**Key Insight**: T0 accuracy is stable across evaluations. T1 accuracy depends on evaluation time.

---

## Evaluation Strategy

### Test T0 vs T1 Separately

```python
# Test T0 (intrinsic classification)
def test_t0_accuracy():
    """
    Compare classifier output to GDS labels.
    Should be stable across evaluation times.
    """
    for email in gds:
        result = classifier.classify(...)
        predicted_t0 = result['importance']
        actual_t0 = email['importance']  # GDS label
        assert predicted_t0 == actual_t0

# Test T1 (temporal decay)
def test_t1_accuracy():
    """
    Compare digest sections to user expectations.
    Depends on evaluation time.
    """
    for email in gds:
        t0 = classifier.classify(...)['importance']
        t1 = apply_temporal_decay(t0, temporal_ctx, now)

        # Expected T1 depends on now
        if now - event_time > 7d:
            assert t1 == "worth_knowing"
        elif now - event_time <= 1h:
            assert t1 == "critical"
```

---

## Pipeline Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│ STAGE 1: Classification (T0)                                    │
│ Module: mailq/classification/memory_classifier.py               │
│                                                                  │
│ Input:  Email (subject, snippet, from)                          │
│ Output: importance="time_sensitive" (T0)                        │
│         type="event"                                             │
│         client_label="everything-else"                           │
└─────────────────────────────────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│ STAGE 2: Temporal Context Extraction                            │
│ Module: mailq/digest/temporal_extraction.py                     │
│                                                                  │
│ Input:  Email (subject, snippet)                                │
│ Output: temporal_ctx = {                                         │
│           "event_time": datetime(2025, 11, 21, 18, 30),         │
│           "event_end_time": datetime(2025, 11, 21, 19, 30)      │
│         }                                                        │
└─────────────────────────────────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│ STAGE 3: Temporal Decay (T0 → T1)                              │
│ Module: mailq/digest/temporal_decay.py                          │
│                                                                  │
│ Input:  T0 importance="time_sensitive"                          │
│         temporal_ctx (event_time)                                │
│         now = datetime(2025, 11, 9, 14, 0)                      │
│                                                                  │
│ Logic:  event_time - now = 12 days                             │
│         12 days > 7 days → downgrade to "routine"               │
│                                                                  │
│ Output: T1 section="worth_knowing"                              │
└─────────────────────────────────────────────────────────────────┘
                             ↓
┌─────────────────────────────────────────────────────────────────┐
│ STAGE 4: Digest Rendering                                       │
│ Module: mailq/digest/digest_pipeline.py                         │
│                                                                  │
│ Sections:                                                        │
│   - TODAY / URGENT (T1=critical)                                │
│   - COMING UP (T1=time_sensitive)                               │
│   - WORTH KNOWING (T1=routine) ← Event goes here               │
│   - EVERYTHING ELSE (receipts, newsletters)                     │
└─────────────────────────────────────────────────────────────────┘
```

---

## Critical Constraints

### 1. OTPs Never in Digest

```python
# Digest generation
def should_include_in_digest(email):
    if email.type == "otp":
        return False  # OTPs expire too fast
    return True
```

**Rationale**:
- OTPs expire in minutes
- By digest generation time (daily), they're useless
- Should trigger real-time notifications, not appear in digest

### 2. Action-Required → URGENT (if relevant)

```python
# Digest section assignment
def get_digest_section(email, t1_importance, client_label):
    # Consequence-based urgency
    if client_label == "action-required" and not is_expired(email):
        return "TODAY / URGENT"

    # Otherwise use T1 importance
    return section_map[t1_importance]
```

**Examples**:
- ✅ Failed payment (action required, not expired) → URGENT
- ✅ Subscription cancellation warning → URGENT
- ❌ OTP (action required, but expired) → Skip (not in digest)

### 3. GDS = T0 Only

**Never add T1 labels to GDS** — they would become stale immediately.

**Correct approach**:
- GDS contains T0 labels (observer-independent)
- Generate T1 labels dynamically at evaluation time
- Compare T0 classifier output to GDS T0 labels

---

## Examples

### Example 1: Calendar Event (T0 → T1)

```
Email: "Invitation: Dinner @ Fri Nov 21, 2025 6:30pm"

T0 (Intrinsic):
  - Has event time → time_sensitive
  - GDS label: time_sensitive ✅

T1 (Nov 9, 2025 14:00):
  - Event is 12 days out
  - 12 days > 7 days → downgrade to routine
  - Digest section: WORTH KNOWING

T1 (Nov 20, 2025 14:00):
  - Event is tomorrow
  - <24 hours → escalate to critical
  - Digest section: TODAY / URGENT
```

### Example 2: OTP (T0 → Never in Digest)

```
Email: "Your verification code is 123456"

T0 (Intrinsic):
  - One-time passcode → critical
  - GDS label: critical ✅

T1 (Any time):
  - type == "otp" → SKIP
  - Never included in digest
  - Reason: Expires in minutes, useless by digest time
```

### Example 3: Failed Payment (T0 + Action-Required → URGENT)

```
Email: "Payment failed - update your billing info"

T0 (Intrinsic):
  - Financial action required → time_sensitive
  - client_label: action-required
  - GDS label: time_sensitive ✅

T1 (Any time):
  - client_label == "action-required" AND not expired
  - Consequence-based urgency → critical
  - Digest section: TODAY / URGENT
```

### Example 4: Receipt (T0 → T1, No Change)

```
Email: "Your Uber Eats order receipt"

T0 (Intrinsic):
  - Informational, no urgency → routine
  - GDS label: routine ✅

T1 (Any time):
  - No temporal context → no decay
  - Stays routine
  - Digest section: EVERYTHING ELSE
```

---

## Principles Alignment

### P1: Concepts Are Rooms ✅

- T0 classification: One module (`memory_classifier.py`)
- T1 temporal decay: One module (`temporal_decay.py`)
- Clear separation of concerns

### P2: Side Effects Are Loud ✅

All stages document side effects:
```python
def apply_temporal_decay(...) -> str:
    """
    Apply temporal decay to T0 importance.

    Side Effects: None (pure function, no state modification)
    """
```

### P3: Compiler Is Senior Engineer ✅

Fully typed contracts:
```python
def apply_temporal_decay(
    t0_section: str,
    email: dict[str, Any],
    temporal_ctx: dict[str, Any] | None,
    now: datetime,
    user_timezone: str = "UTC",
) -> str:
    """Returns T1 section"""
```

### P4: Synchronizations Explicit ✅

Pipeline dependencies declared:
```python
TemporalDecayStage:
    depends_on: ["extract_temporal_context", "assign_sections_t0"]
```

---

## Summary

| Concept | Definition | Module | Output | Observer-Dependent? |
|---------|------------|--------|--------|---------------------|
| **T0** | Intrinsic importance | `memory_classifier.py` | `importance` field | ❌ No (stable) |
| **T1** | Time-adjusted importance | `temporal_decay.py` | Digest section | ✅ Yes (changes with evaluation time) |
| **GDS** | Ground truth labels | `gds-2.0-manually-reviewed.csv` | T0 labels only | ❌ No (T0 = stable) |

**Key Insight**: Separating T0 and T1 enables:
1. ✅ Stable, reusable ground truth (T0)
2. ✅ Dynamic, context-aware digests (T1)
3. ✅ Independent evaluation of classification vs temporal logic
4. ✅ Clear architectural boundaries (P1)

---

## Related Documentation

- [Temporal Decay Implementation](PHASE_4_TEMPORAL_DECAY.md) - Technical details of temporal decay rules
- [GDS Temporal Context](../archive/GDS_TEMPORAL_CONTEXT.md) - Testing strategy for temporal classification
- [T0/T1 Refactor Results](../../reports/archive/2025-01/PHASE_3_T0_T1_REFACTOR_RESULTS.md) - Evaluation results after refactor

---

**Status**: ✅ Active - This is the current architecture for importance classification in MailQ.
