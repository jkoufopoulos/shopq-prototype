# ShopQ Configuration Directory

YAML configuration files for runtime behavior, classification rules, guardrails, and policy thresholds.

## Philosophy

ShopQ externalizes all runtime configuration to YAML files to enable:
- **Tuning without code changes** - Adjust thresholds, rules, and examples without redeployment
- **Transparency** - Configuration is human-readable and version-controlled
- **A/B testing** - Easy to swap configurations for experimentation
- **AI-agent friendly** - LLMs can read and understand configuration easily

**Key principle**: Configuration-as-code, not hardcoded values.

---

## Configuration Files

### 📋 shopq_policy.yaml

**Purpose**: Core runtime policy thresholds for classification, verification, quality monitoring, and temporal decay.

**When to edit**: Tuning system behavior (confidence thresholds, time windows, quality triggers).

**Key sections**:

```yaml
classification:
  min_type_conf: 0.92        # Minimum confidence for email type (event, deadline, etc.)
  min_label_conf: 0.85       # Minimum confidence for domain/attention labels

verifier:
  trigger_conf_min: 0.50     # Always verify below this confidence
  trigger_conf_max: 0.90     # Skip verification above this confidence

quality_monitor:
  batch_min_emails: 25       # Minimum emails before quality analysis

temporal_decay:
  grace_period_hours: 1      # Events ended ≤1h ago still shown
  active_window_hours: 1     # Events starting ≤1h → critical
  upcoming_horizon_days: 7   # Events ≤7 days → time_sensitive
  distant_threshold_days: 30 # Events >30 days → routine
```

**Example tuning**:
```bash
# Make classification stricter (fewer uncategorized emails)
sed -i '' 's/min_type_conf: 0.92/min_type_conf: 0.88/' config/shopq_policy.yaml

# Expand active window for critical events (1h → 2h)
sed -i '' 's/active_window_hours: 1/active_window_hours: 2/' config/shopq_policy.yaml
```

**References**:
- Code: `shopq/config/settings.py` (loads this file)
- Docs: `/docs/CONFIGURATION.md`
- Temporal logic: `shopq/temporal_decay.py`

---

### 🛡️ guardrails.yaml

**Purpose**: Guardrail rules that override LLM classifications (force critical, force routine, etc.).

**When to edit**: Adding new patterns that should always be classified a certain way (e.g., OTP codes → routine).

**Structure**:

```yaml
force_critical:
  - patterns: ["breach", "fraud", "security alert"]
    reason: "Security-related, always critical"

force_non_critical:
  - patterns: ["one-time password", "verification code", "OTP"]
    reason: "OTP codes are routine (expire quickly)"
  - patterns: ["unsubscribe", "manage preferences"]
    reason: "Email management, not urgent"

skip:
  - patterns: ["newsletter", "digest", "weekly update"]
    reason: "Bulk emails, skip classification"
```

**How it works**:
1. Guardrails run **before** LLM classification (skip unnecessary calls)
2. If pattern matches, classification is forced (no LLM needed)
3. Saves cost and improves consistency

**Example: Add new guardrail**:

```yaml
force_non_critical:
  - patterns: ["shipping confirmation", "order confirmed"]
    reason: "Shipping confirmations are informational, not urgent"
```

**References**:
- Code: `shopq/bridge/guardrails.py` (implements matching)
- Tests: `tests/unit/test_guardrails_precedence.py`
- Docs: `/docs/VERIFY_FIRST_STRATEGY.md`

---

### 🎯 llm_importance_examples.yaml

**Purpose**: Few-shot examples for LLM importance classification (critical vs time_sensitive vs routine).

**When to edit**: Improving classification accuracy by adding exemplar emails.

**Structure** (13 KB, 100+ examples):

```yaml
critical:
  - subject: "Flight delayed - gate change to B42"
    reason: "Immediate action required, affects travel plans"
    type: "notification"
    attention: "action_required"

time_sensitive:
  - subject: "Dinner reservation tomorrow at 7pm"
    reason: "Event within 24 hours, needs awareness"
    type: "event"
    attention: "awareness"

routine:
  - subject: "Weekly newsletter from TechCrunch"
    reason: "Informational, no time pressure"
    type: "notification"
    attention: "fyi"
```

**How it works**:
- LLM receives 5-10 examples per importance level
- Examples guide classification decisions
- More examples → better accuracy (but higher cost/latency)

**Example: Add new example**:

```yaml
critical:
  - subject: "Credit card fraud alert - verify transaction"
    reason: "Financial security, immediate response needed"
    type: "notification"
    attention: "action_required"
    domains: ["finance"]
```

**Best practices**:
- Add examples that cover edge cases or common misclassifications
- Balance examples across importance levels (avoid bias)
- Include diverse email types (events, deadlines, notifications)

**References**:
- Code: `shopq/importance_classifier.py` (loads examples)
- Evaluation: `scripts/check_importance_baseline.py`
- Golden Dataset: `tests/golden_set/gds-1.0.csv` (labeled examples)

---

### 🔀 mapper_rules.yaml

**Purpose**: Maps internal importance levels to Gmail labels (bridge pattern).

**When to edit**: Changing Gmail label names or mapping logic.

**Structure**:

```yaml
importance_to_labels:
  critical:
    - "IMPORTANT"
    - "STARRED"
  time_sensitive:
    - "IMPORTANT"
  routine:
    # No labels (leaves in inbox)

type_to_category:
  notification:
    - "CATEGORY_UPDATES"
  event:
    - "CATEGORY_PERSONAL"
  deadline:
    - "CATEGORY_PERSONAL"
```

**Bridge pattern**:
- **Backend** returns generic importance (critical, time_sensitive, routine)
- **Mapper** converts to Gmail labels (IMPORTANT, STARRED, CATEGORY_*)
- **Benefit**: Gmail policy decoupled from LLM, easy to change labels

**Example: Change critical label**:

```yaml
importance_to_labels:
  critical:
    - "URGENT"  # Changed from "IMPORTANT"
    - "STARRED"
```

**References**:
- Code: `shopq/bridge/mapper.py` (implements mapping)
- Extension: `extension/modules/mapper.js` (client-side mapping)
- Tests: `tests/unit/test_mapper.py`

---

### 📧 type_mapper_rules.yaml

**Purpose**: Maps email content patterns to email types (event, deadline, notification, etc.).

**When to edit**: Improving type classification or adding new email types.

**Structure**:

```yaml
event:
  keywords: ["meeting", "appointment", "calendar", "rsvp"]
  patterns:
    - "join us for"
    - "you're invited"
  confidence_boost: 0.1  # Boost confidence if multiple keywords match

deadline:
  keywords: ["due", "deadline", "expires", "submit by"]
  patterns:
    - "by [date]"
    - "before [date]"

notification:
  keywords: ["update", "alert", "reminder", "confirmation"]
```

**How it works**:
- Rules provide initial type hints before LLM classification
- If patterns match, confidence is boosted
- Reduces reliance on LLM for obvious cases

**Example: Add new type**:

```yaml
invoice:
  keywords: ["invoice", "payment due", "amount owed"]
  patterns:
    - "invoice #"
    - "total amount:"
  confidence_boost: 0.15
```

**References**:
- Code: `shopq/type_mapper.py` (implements matching)
- Tests: `tests/unit/test_type_mapper.py`
- Golden Dataset: `tests/golden_set/gds-1.0.csv` (type labels)

---

### 💰 budgets.yaml

**Purpose**: API call budgets to prevent quota exhaustion and control costs.

**When to edit**: Adjusting daily/weekly limits for LLM calls, Gmail API calls, etc.

**Structure**:

```yaml
daily_limits:
  gemini_classification: 1000   # Max Gemini calls per day
  claude_narrative: 10          # Max Claude calls per day (expensive)
  gmail_api: 2500               # Max Gmail API calls per day

cost_per_call:
  gemini_classification: 0.002  # $0.002 per call
  claude_narrative: 0.10        # $0.10 per call

alerts:
  - threshold: 0.80  # Alert at 80% budget
    action: "log"
  - threshold: 0.95  # Alert at 95% budget
    action: "notify"
```

**How it works**:
- Extension checks budget before expensive operations
- If budget exceeded, falls back to cached/rule-based classification
- Prevents runaway costs

**Example: Increase Gemini budget**:

```yaml
daily_limits:
  gemini_classification: 2000  # Increased from 1000
```

**References**:
- Code: `extension/modules/budget.js` (client-side tracking)
- Backend: `shopq/observability.py` (server-side tracking)
- Docs: `/docs/COST_PERFORMANCE.md`

---

## Configuration Loading

### Python Backend

```python
from shopq.config.settings import get_config

config = get_config()
min_conf = config['classification']['min_type_conf']  # 0.92
```

**Loading order**:
1. Load YAML from `config/shopq_policy.yaml`
2. Override with environment variables (if set)
3. Cache in memory for performance

### JavaScript Extension

```javascript
// Extension loads mapper_rules.yaml via backend API
const rules = await fetch(`${API_URL}/api/config/mapper_rules`);
```

**Note**: Extension cannot directly read YAML files (browser sandbox).

---

## Configuration Best Practices

### 1. Document All Changes
When editing configuration, document the reason:

```yaml
# 2025-11-11: Increased min_type_conf from 0.88 to 0.92
# Reason: Reduce uncategorized emails (precision > recall)
min_type_conf: 0.92
```

### 2. Test After Changes

```bash
# Run baseline evaluation
python scripts/check_importance_baseline.py

# Run integration tests
pytest tests/integration/

# Check for regressions
python scripts/compare_actual_vs_ideal.py
```

### 3. Version Configuration Files

Configuration is version-controlled. Use git to track changes:

```bash
git diff config/shopq_policy.yaml
git log config/guardrails.yaml
```

### 4. Use Feature Flags for Risky Changes

For risky configuration changes, use feature flags:

```python
from shopq.feature_gates import feature_gates

if feature_gates.is_enabled('strict_classification'):
    min_conf = 0.95  # Stricter
else:
    min_conf = 0.92  # Default
```

### 5. Monitor Impact

After configuration changes, monitor:
- Classification accuracy (precision, recall)
- API call budget usage
- User feedback (false positives/negatives)

See: `/docs/QUALITY_MONITOR.md`

---

## Common Configuration Tasks

### Tune Classification Thresholds

**Goal**: Reduce uncategorized emails without sacrificing accuracy.

1. Check current accuracy:
   ```bash
   python scripts/check_importance_baseline.py
   ```

2. Lower `min_type_conf`:
   ```yaml
   classification:
     min_type_conf: 0.88  # Was 0.92
   ```

3. Re-evaluate:
   ```bash
   python scripts/eval_baseline_gds1.py
   ```

4. If accuracy acceptable, keep change. Otherwise, revert.

### Add New Guardrail

**Goal**: Force specific email patterns to always be classified as routine.

1. Edit `guardrails.yaml`:
   ```yaml
   force_non_critical:
     - patterns: ["marketing", "promotional", "sale"]
       reason: "Marketing emails are routine"
   ```

2. Test guardrail:
   ```bash
   pytest tests/unit/test_guardrails_precedence.py
   ```

3. Verify in production:
   ```bash
   # Check shadow log for guardrail matches
   grep "guardrail=force_non_critical" logs/shadow_logger.log
   ```

### Add Few-Shot Examples

**Goal**: Improve classification of specific email types.

1. Identify misclassifications:
   ```bash
   python scripts/analyze_gds_misclassifications.py
   ```

2. Add examples to `llm_importance_examples.yaml`:
   ```yaml
   critical:
     - subject: "Password reset requested"
       reason: "Security action, requires immediate attention"
       type: "notification"
       attention: "action_required"
   ```

3. Re-evaluate:
   ```bash
   python scripts/check_importance_baseline.py
   ```

### Adjust Temporal Decay Windows

**Goal**: Change how event proximity affects importance.

1. Edit `shopq_policy.yaml`:
   ```yaml
   temporal_decay:
     active_window_hours: 2  # Was 1 (meetings within 2h → critical)
     upcoming_horizon_days: 3  # Was 7 (events within 3 days → time_sensitive)
   ```

2. Test temporal logic:
   ```bash
   pytest tests/unit/test_temporal_decay.py
   ```

3. Verify with real data:
   ```bash
   python scripts/extract_temporal_fields.py
   ```

---

## Configuration Validation

### YAML Syntax Check

```bash
# Check YAML syntax
python -c "import yaml; yaml.safe_load(open('config/shopq_policy.yaml'))"
```

### Schema Validation

```bash
# Validate against expected schema (if configured)
python scripts/validate_config.py
```

### Integration Test

```bash
# Load all configs and verify no errors
pytest tests/config/test_config_loading.py
```

---

## Environment Variables

Some configuration can be overridden via environment variables:

| Variable | Overrides | Default |
|----------|-----------|---------|
| `MIN_EMAILS_FOR_ANALYSIS` | `quality_monitor.batch_min_emails` | 25 |
| `MIN_TYPE_CONF` | `classification.min_type_conf` | 0.92 |
| `VERIFIER_TRIGGER_MIN` | `verifier.trigger_conf_min` | 0.50 |

**Priority**: Environment variables > YAML config > hardcoded defaults

**Migration note**: Environment variables are legacy. Prefer YAML configuration.

---

## Troubleshooting

### Configuration Not Loaded

**Symptom**: Changes to YAML not reflected in behavior.

**Causes**:
1. Configuration cached (restart backend)
2. Environment variable override (check `.env`)
3. Wrong file path (check `shopq/config/settings.py`)

**Fix**:
```bash
# Restart backend to reload config
pkill -f "uvicorn shopq.api:app"
uvicorn shopq.api:app --reload

# Check loaded config
curl http://localhost:8000/api/debug/config
```

### YAML Syntax Error

**Symptom**: Backend crashes on startup with YAML parse error.

**Fix**:
```bash
# Validate YAML syntax
python -c "import yaml; print(yaml.safe_load(open('config/shopq_policy.yaml')))"

# Common issues:
# - Missing spaces after colons
# - Inconsistent indentation (use spaces, not tabs)
# - Unquoted strings with special characters
```

### Guardrail Not Matching

**Symptom**: Expected guardrail not triggering.

**Fix**:
1. Check pattern matching logic:
   ```python
   from shopq.bridge.guardrails import GuardrailMatcher
   matcher = GuardrailMatcher()
   result = matcher.match("subject", "body")
   print(result)  # Should show matched guardrail
   ```

2. Check case sensitivity (patterns are case-insensitive)
3. Check substring matching (patterns match anywhere in subject/body)

---

## Related Documentation

- **Settings Module**: `shopq/config/settings.py` (loads configuration)
- **Configuration Guide**: `/docs/CONFIGURATION.md`
- **Guardrails**: `/docs/VERIFY_FIRST_STRATEGY.md`
- **Policy Overview**: `/claude.md` (section 8: ShopQ-specific guardrails)

---

## Configuration Statistics

- **Total YAML files**: 6
- **Total configuration lines**: 500+ (across all files)
- **Guardrail rules**: 24 (as of Nov 2025)
- **Few-shot examples**: 100+ (llm_importance_examples.yaml)

---

**Last Updated**: November 2025
**Configuration Format**: YAML
**Maintained by**: See `/CONTRIBUTING.md`
