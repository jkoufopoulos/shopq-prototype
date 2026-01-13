# MailQ Configuration Guide

Complete guide to configuring confidence thresholds, feature gates, and test mode.

## Quick Reference

```bash
# View current configuration
curl http://localhost:8000/api/config/confidence  # Confidence thresholds
curl http://localhost:8000/api/features           # Feature gates
curl http://localhost:8000/api/test/mode          # Test mode status

# Toggle features
curl -X POST http://localhost:8000/api/features/test_mode/enable
curl -X POST http://localhost:8000/api/features/digest_urgency_grouping/disable
```

---

## Table of Contents

- [Confidence System](#confidence-system)
- [Feature Gates](#feature-gates)
- [Test Mode](#test-mode)
- [Environment Variables](#environment-variables)

---

## Confidence System

### Overview

**Confidence scores** are probabilities (0.0-1.0) that indicate how certain the LLM is about its classification.

MailQ uses **7 confidence gates** throughout the classification pipeline to filter low-quality results:

1. **Type Gate (0.70)** - Must be 70%+ confident in email type (verify-first strategy)
2. **Label Gate (0.70)** - Individual labels must be 70%+ confident
3. **Mapper Gates (0.70)** - Apply when mapping to Gmail labels
4. **Learning Gate (0.70)** - Only learn from medium+ confidence classifications
5. **Domain Boost (0.60→0.70)** - Boost weak domain confidences
6. **Verifier Trigger (0.50-0.94)** - Trigger second opinion for most classifications
7. **Verifier Acceptance (0.15)** - Only accept corrections with significant improvement

### Centralized Configuration

All thresholds are defined in `config/mailq_policy.yaml` (single source of truth) and loaded by `mailq/observability/confidence.py`:

```yaml
# config/mailq_policy.yaml
classification:
  min_type_conf: 0.70           # Type must be 70%+ confident (verify-first)
  min_label_conf: 0.70          # Labels must be 70%+ confident
  type_gate: 0.70               # Matches min_type_conf
  domain_gate: 0.70             # Domain labels
  attention_gate: 0.70          # Action-required threshold
  learning_min_confidence: 0.70 # Learn from medium+ confidence LLM
  domain_min_threshold: 0.60    # Boost domains below this
  domain_boost_value: 0.70      # Boost weak domains to this value

verifier:
  trigger_conf_min: 0.50        # Verifier trigger range: 50-94%
  trigger_conf_max: 0.90        # Verify almost everything (skip only 0.95+)
```

**Verify-First Strategy**: Lower gate (0.70) + verify almost everything (0.50-0.94) = higher accuracy. Only skip verifier for 0.95+ confidence (detector-only classifications).

### The 7 Gates Explained

#### Gate 1: Type Confidence (0.70)

**Location**: `mailq/api/routes/organize.py`

```python
from mailq.observability.confidence import TYPE_CONFIDENCE_MIN  # 0.70

if result['type_conf'] < TYPE_CONFIDENCE_MIN:
    filtered_labels = ['Uncategorized']
```

**Purpose**: Filter out uncertain type classifications (verify-first strategy)

**Example**:
```
Input:  { type: "newsletter", type_conf: 0.65 }
Result: "Uncategorized" (below 0.70 threshold)

Input:  { type: "newsletter", type_conf: 0.75 }
Result: "newsletter" (above 0.70, triggers verifier for second opinion)
```

#### Gate 2: Label Confidence (0.70)

**Location**: `mailq/api/routes/organize.py`

```python
from mailq.observability.confidence import LABEL_CONFIDENCE_MIN  # 0.70

filtered = [label for label in labels
           if conf >= LABEL_CONFIDENCE_MIN]
```

**Purpose**: Filter out individual labels with low confidence

**Example**:
```
Input:  { domains: ["finance": 0.80, "shopping": 0.60] }
Result: ["finance"] only (shopping below 0.70)
```

#### Gate 3: Mapper Gates (0.70)

**Location**: `mailq/classification/mapper.py`

```python
from mailq.observability.confidence import TYPE_GATE, DOMAIN_GATE, ATTENTION_GATE

# All gates now 0.70 (verify-first strategy)
if type_conf >= TYPE_GATE:
    labels.append(f"MailQ-{type}")

for domain, conf in domain_confs.items():
    if conf >= DOMAIN_GATE:
        labels.append(f"MailQ-{domain}")

if attention == "action_required" and attention_conf >= ATTENTION_GATE:
    labels.append("MailQ-Action-Required")
```

**Purpose**: Apply gates when converting semantic labels to Gmail labels

**Why 0.70 for all?** Verify-first strategy: lower gates allow more classifications through, verifier catches errors.

#### Gate 4: Learning Gate (0.70)

**Location**: `mailq/classification/memory_classifier.py`

```python
from mailq.observability.confidence import LEARNING_MIN_CONFIDENCE  # 0.70

if type_conf >= LEARNING_MIN_CONFIDENCE:
    rules.learn_from_classification(...)  # Create pending rule
```

**Purpose**: Learn from medium+ confidence classifications (verifier-validated)

**Why 0.70?** With verify-first strategy, even 0.70+ classifications have been validated by the verifier, making them reliable for learning.

#### Gate 5: Domain Boost (0.60 → 0.70)

**Location**: `mailq/classification/vertex_gemini_classifier.py`

```python
from mailq.observability.confidence import DOMAIN_MIN_THRESHOLD, DOMAIN_BOOST_VALUE

for domain in result.get('domains', []):
    conf = domain_confs.get(domain, 0.0)
    if conf < DOMAIN_MIN_THRESHOLD:  # 0.60
        domain_confs[domain] = DOMAIN_BOOST_VALUE  # Boost to 0.70
```

**Purpose**: Help LLM when it's uncertain about domains

**Why?** LLM often undershoots domain confidence. Boosting 0.55→0.70 improves recall without hurting precision.

#### Gate 6: Verifier Trigger (0.50 - 0.94)

**Location**: `extension/modules/verifier.js`

```python
from mailq.observability.confidence import VERIFIER_LOW_CONFIDENCE, VERIFIER_HIGH_CONFIDENCE

def should_verify(classification):
    conf = classification.get('type_conf', 1.0)

    # Trigger if confidence in suspicious range (verify-first: almost everything)
    if VERIFIER_LOW_CONFIDENCE <= conf <= VERIFIER_HIGH_CONFIDENCE:
        return True

    # Also trigger on contradictions, multi-purpose senders, etc.
    ...
```

**Purpose**: Trigger second LLM opinion for most classifications (verify-first strategy)

**Why 0.50-0.94?**
- Too low (< 0.50): Already flagged as uncategorized
- Very high (> 0.94): Only detector classifications (OTP, receipt patterns) skip verifier
- **Verify-first**: Most LLM outputs (0.70-0.94) get verified for higher accuracy

#### Gate 7: Verifier Acceptance (0.15)

**Location**: `mailq/api_verify.py`

```python
from mailq.config.confidence import VERIFIER_CORRECTION_DELTA  # 0.15

if verifier_verdict == "reject":
    confidence_delta = correction_conf - original_conf

    if confidence_delta >= VERIFIER_CORRECTION_DELTA:
        # Accept correction (significantly more confident)
        return correction
    else:
        # Reject correction (not confident enough in change)
        return original
```

**Purpose**: Only accept verifier corrections that are significantly more confident

**Why 0.15?** Small differences (e.g., 0.72 vs 0.74) aren't meaningful. Require ≥15% improvement.

### API Endpoints

**Get all thresholds:**
```bash
curl http://localhost:8000/api/config/confidence
```

**Get confidence statistics:**
```bash
curl http://localhost:8000/api/confidence/stats?days=7
```

**Get low-confidence emails:**
```bash
curl http://localhost:8000/api/confidence/low?limit=100
```

**Get confidence trend:**
```bash
curl http://localhost:8000/api/confidence/trend?days=30
```

### Monitoring & Logging

All classifications are logged to `confidence_logs` table via `ConfidenceLogger`:

```python
from mailq.confidence_logger import ConfidenceLogger

logger = ConfidenceLogger()
logger.log_classification(result, email_id, subject, filtered_labels)
```

**Query logs:**
```bash
sqlite3 mailq/data/mailq.db "
  SELECT subject, type_conf, domain_conf
  FROM confidence_logs
  WHERE type_conf < 0.85
  ORDER BY created_at DESC
  LIMIT 10
"
```

### Why These Specific Values? (Verify-First Strategy)

**Type Gate (0.70):**
- **Old approach (0.92)**: High precision but many "Uncategorized" results
- **New approach (0.70)**: Lower gate + verifier = higher accuracy overall
- Verifier catches errors in the 0.70-0.94 range

**All Gates (0.70):**
- Unified threshold simplifies configuration
- Verify-first strategy means all medium+ confidence gets validated
- Fewer "Uncategorized" results, same or better precision

**Learning Gate (0.70):**
- With verify-first, even 0.70+ classifications are verifier-validated
- Safe to learn from these since they've been double-checked
- Faster rule creation without sacrificing reliability

**Verifier Trigger (0.50-0.94):**
- Widened from 0.50-0.90 to catch more edge cases
- Only 0.95+ (detector matches) skip verifier
- Trade-off: More LLM calls, but higher accuracy

---

## Feature Gates

### Overview

Feature gates allow you to switch between different versions of features without code changes.

### Available Features

#### Digest Generation

| Feature | Default | Description |
|---------|---------|-------------|
| `digest_urgency_grouping` | ✅ Enabled | **NEW**: Group digest by urgency (critical/time-sensitive)<br>**OLD**: Chronological listing |
| `digest_dynamic_examples` | ✅ Enabled | Use real inbox data as examples (no hardcoded examples) |

#### Classification

| Feature | Default | Description |
|---------|---------|-------------|
| `use_verifier` | ✅ Enabled | Use verifier LLM for suspicious classifications |
| `use_rules_engine` | ✅ Enabled | Use rules engine for T0 (free) matches |

#### Performance

| Feature | Default | Description |
|---------|---------|-------------|
| `cache_classifications` | ✅ Enabled | Cache classifications for 24 hours |
| `batch_gmail_api` | ✅ Enabled | Batch Gmail API calls for efficiency |

#### Experimental

| Feature | Default | Description |
|---------|---------|-------------|
| `experimental_entity_linking` | ❌ Disabled | Better entity linking (unstable) |
| `experimental_smart_scheduling` | ❌ Disabled | Smart event scheduling (unstable) |

### How to Use

#### Via API (Runtime - Session Only)

```bash
# Enable feature for current session
curl -X POST http://localhost:8000/api/features/digest_urgency_grouping/enable

# Disable feature for current session
curl -X POST http://localhost:8000/api/features/digest_urgency_grouping/disable

# Reset to default
curl -X POST http://localhost:8000/api/features/digest_urgency_grouping/reset

# View all features
curl http://localhost:8000/api/features

# Check specific feature
curl http://localhost:8000/api/features/digest_urgency_grouping
```

**Note:** API toggles are **session-only** and reset when you restart the server.

#### Via Environment Variables (Persistent)

```bash
# Enable by default
export FEATURE_DIGEST_URGENCY_GROUPING=true

# Disable by default
export FEATURE_USE_VERIFIER=false

# Start server with custom defaults
uvicorn mailq.api:app --reload
```

**Note:** Environment variables set the **default** state. API calls can still override during runtime.

### Priority Order

```
API Override (session) > Environment Variable > Code Default
```

**Example:**
```bash
# Code default: enabled
# .env: FEATURE_DIGEST_URGENCY_GROUPING=false  (disabled)
# Runtime: curl -X POST .../enable             (enabled)

# Result: Enabled (API override wins)
```

### Common Workflows

**Switch digest versions:**
```bash
# Use NEW grouped digest (v2)
curl -X POST http://localhost:8000/api/features/digest_urgency_grouping/enable

# Use OLD original digest (v1)
curl -X POST http://localhost:8000/api/features/digest_urgency_grouping/disable
```

**Disable verifier temporarily:**
```bash
# Disable for current session (faster, less cost)
curl -X POST http://localhost:8000/api/features/use_verifier/disable

# Re-enable later
curl -X POST http://localhost:8000/api/features/use_verifier/enable
```

**Test experimental features:**
```bash
# Enable experimental entity linking
curl -X POST http://localhost:8000/api/features/experimental_entity_linking/enable

# Test it out...

# Disable if unstable
curl -X POST http://localhost:8000/api/features/experimental_entity_linking/disable
```

---

## Test Mode

### Overview

Test mode allows you to classify emails without creating rules or learning from corrections. Perfect for testing classification accuracy without polluting your rules database.

### How to Enable

#### Option 1: Feature Gate (Recommended - Runtime Toggle)

```bash
# Enable
curl -X POST http://localhost:8000/api/features/test_mode/enable

# Disable
curl -X POST http://localhost:8000/api/features/test_mode/disable

# Check status
curl -s http://localhost:8000/api/test/mode
```

✅ **No backend restart needed**
✅ **Toggle on/off instantly**

#### Option 2: Environment Variable (Legacy)

```bash
# Set before starting backend
export TEST_MODE=true
uvicorn mailq.api:app --reload

# Or inline
TEST_MODE=true uvicorn mailq.api:app --reload
```

⚠️ **Requires backend restart to change**

### What Test Mode Does

When **either** method is enabled:

**❌ Disabled:**
- Rules engine (no T0 rule matches)
- Rule learning (no new rules created)
- Feedback collection (user corrections ignored)

**✅ Still Active:**
- LLM classification (all emails go through Gemini)
- Classification logging
- Confidence scoring
- Telemetry

### Use Cases

**1. Test Prompt Changes**
```bash
# Enable test mode
curl -X POST http://localhost:8000/api/features/test_mode/enable

# Edit mailq/prompts/classifier_prompt.txt
# Classify test emails
# Review results

# Disable test mode when done
curl -X POST http://localhost:8000/api/features/test_mode/disable
```

**2. Compare Confidence Thresholds**
```bash
# Enable test mode (no rules interference)
curl -X POST http://localhost:8000/api/features/test_mode/enable

# Edit mailq/config/confidence.py
# Test with new thresholds
# Check confidence stats

# Disable when done
curl -X POST http://localhost:8000/api/features/test_mode/disable
```

**3. Benchmark Classification Accuracy**
```bash
# Clear rules, enable test mode
python3 mailq/scripts/clear_rules.py
curl -X POST http://localhost:8000/api/features/test_mode/enable

# Classify 100 test emails
# Review accuracy without rules helping

# Re-enable rules when done
curl -X POST http://localhost:8000/api/features/test_mode/disable
```

### Quick Start

**1. Clear Existing Rules (Optional)**
```bash
cd /Users/justinkoufopoulos/Projects/mailq-prototype
python3 mailq/scripts/clear_rules.py
```

Creates backup, then asks for confirmation before clearing rules, pending rules, corrections, and feedback.

**2. Enable Test Mode**
```bash
curl -X POST http://localhost:8000/api/features/test_mode/enable
```

**3. Verify**
```bash
curl -s http://localhost:8000/api/test/mode
```

Expected output:
```json
{
  "test_mode": true,
  "source": "feature_gate",
  "rules_disabled": true,
  "learning_disabled": true,
  "feedback_disabled": true
}
```

**4. Classify Emails**

All emails will go through LLM classification without rules or learning.

**5. Disable When Done**
```bash
curl -X POST http://localhost:8000/api/features/test_mode/disable
```

---

## Environment Variables

### Core Configuration

| Variable | Default | Purpose |
|----------|---------|---------|
| `GOOGLE_API_KEY` | Required | Google Cloud API key |
| `GOOGLE_CLOUD_PROJECT` | `mailq-467118` | GCP project ID |
| `GEMINI_MODEL` | `gemini-2.0-flash` | LLM model to use |
| `API_PORT` | `8000` | Backend API port |

### Feature Defaults

| Variable | Default | Purpose |
|----------|---------|---------|
| `USE_RULES_ENGINE` | `true` | Enable rules engine |
| `USE_AI_CLASSIFIER` | `true` | Enable LLM classifier |
| `TEST_MODE` | `false` | Test mode on startup |
| `DEBUG_FEATURED` | `false` | Show debug hints in digest |

### Feature Gates (Persistent Defaults)

| Variable | Default | Purpose |
|----------|---------|---------|
| `FEATURE_DIGEST_URGENCY_GROUPING` | `true` | Group digest by urgency |
| `FEATURE_DIGEST_DYNAMIC_EXAMPLES` | `true` | Use real data as examples |
| `FEATURE_USE_VERIFIER` | `true` | Enable verifier |
| `FEATURE_CACHE_CLASSIFICATIONS` | `true` | Enable caching |
| `FEATURE_BATCH_GMAIL_API` | `true` | Batch Gmail API calls |

### Example .env File

```bash
# Required
GOOGLE_API_KEY=AIzaSy...
GOOGLE_CLOUD_PROJECT=mailq-467118

# Optional
GEMINI_MODEL=gemini-2.0-flash
API_PORT=8000

# Feature defaults
FEATURE_DIGEST_URGENCY_GROUPING=true
FEATURE_USE_VERIFIER=true
TEST_MODE=false
DEBUG_FEATURED=false
```

---

## Related Documentation

- [ARCHITECTURE.md](ARCHITECTURE.md) - System design and components
- [DEBUGGING.md](DEBUGGING.md) - Debugging tools and techniques
- [TESTING.md](TESTING.md) - Testing procedures
- [QUICKSTART.md](../QUICKSTART.md) - Getting started guide

---

**Last Updated**: 2025-11-30
