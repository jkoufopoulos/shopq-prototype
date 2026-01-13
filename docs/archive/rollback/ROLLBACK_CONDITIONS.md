# Rollback Conditions & Incident Response

**Purpose:** Define exact thresholds and procedures for rolling back ShopQ deployments when quality, performance, or cost metrics degrade beyond acceptable limits.

**Last Updated:** 2025-11-09
**Baseline Version:** gemini-2.0-flash/2.0/prompt-v1 (see VERSIONS.md)

---

## Quick Reference: When to Rollback

| Condition | Threshold | Action | Response Time |
|-----------|-----------|--------|---------------|
| **OTP in CRITICAL** | > 0 emails | Auto-rollback | Immediate |
| **Critical precision drop** | < baseline − 5pp | Manual rollback | < 15 min |
| **Invalid JSON rate** | > 10% | Auto-rollback | Immediate |
| **P95 latency spike** | > baseline + 1000ms | Investigate, rollback if sustained > 30min | < 30 min |
| **Cost explosion** | > baseline + 50% | Manual rollback | < 1 hour |
| **Error rate** | > 5% | Immediate rollback | < 5 min |

---

## Auto-Rollback Triggers (Immediate)

These conditions trigger **automatic rollback without human approval**:

### 1. OTP (One-Time Password) in CRITICAL Section

**Condition:** Any email containing OTP/verification code classified as `importance=critical` and featured in digest CRITICAL section.

**Why critical:** OTP codes are time-sensitive but NOT important decisions. Featuring them in CRITICAL trains users to ignore the section, destroying trust in the digest.

**Detection:**
```bash
# Check recent digest sessions for OTP in CRITICAL
sqlite3 shopq/data/shopq_tracking.db "
  SELECT session_id, timestamp
  FROM digest_sessions
  WHERE critical_section LIKE '%verification code%'
     OR critical_section LIKE '%OTP%'
     OR critical_section LIKE '%one-time password%'
  ORDER BY timestamp DESC
  LIMIT 5
"
```

**Rollback action:**
1. Immediately revert to previous model/prompt version
2. Page on-call engineer
3. Create incident report with example OTP emails
4. DO NOT re-deploy until root cause fixed and validated with golden set

### 2. Invalid JSON Rate > 10%

**Condition:** LLM returns malformed JSON in > 10% of classification attempts.

**Why critical:** Invalid JSON means fallback to rules-only or complete classification failure. Indicates prompt/schema drift or model degradation.

**Detection:**
```bash
# Check circuit breaker invalid JSON rate
curl https://shopq-api.run.app/metrics | grep "invalid_json_rate"

# Or check logs:
gcloud logging read "resource.type=cloud_run_revision AND
  jsonPayload.event=classification.llm.json_error"
  --limit 100 --format json | jq '[.[] | .jsonPayload] | length'
```

**Rollback action:**
1. Circuit breaker trips automatically (see `shopq/circuitbreaker.py`)
2. System falls back to rules-only classification
3. If rules-only also failing: immediate version rollback
4. Investigate schema changes, model behavior, or prompt corruption

### 3. Error Rate > 5%

**Condition:** Overall API error rate exceeds 5% over 5-minute window.

**Why critical:** Indicates systemic failure (deployment issue, dependency outage, or critical bug).

**Detection:**
```bash
# Cloud Run error rate
gcloud monitoring time-series list \
  --filter='metric.type="run.googleapis.com/request_count"
            AND metric.labels.response_code_class="5xx"' \
  --format="table(metric.labels.response_code)"
```

**Rollback action:**
1. Immediate traffic shift to previous stable revision
2. Check deployment logs for recent changes
3. Verify environment variables not corrupted
4. DO NOT retry deployment until root cause identified

---

## Manual Rollback Triggers (Human Judgment Required)

These conditions require **engineer review within specified time window**:

### 4. Critical Precision Drop (< Baseline − 5pp)

**Baseline (from golden set):** TBD after Phase 0 complete
**Threshold:** If critical precision drops below `baseline_critical_precision - 0.05`

**Example:** If baseline critical precision is 92%, trigger rollback if it drops below 87%.

**Why 5pp threshold:**
- Small drops (1-2pp) = natural variance or edge cases
- Large drops (5pp+) = systematic misclassification indicating broken logic

**Detection:**
```bash
# Run golden set replay with new version
PYTHONPATH=. pytest tests/test_importance_baseline.py --baseline=eval/baseline.json

# Compare precision by class
python scripts/check_importance_baseline.py --compare

# Or manual calculation from recent sessions:
sqlite3 shopq/data/shopq_tracking.db "
  SELECT
    COUNT(*) as total_critical,
    SUM(CASE WHEN user_corrected=1 THEN 1 ELSE 0 END) as incorrect
  FROM classified_emails
  WHERE importance='critical'
    AND timestamp > datetime('now', '-24 hours')
"
# Precision = (total - incorrect) / total
```

**Rollback action:**
1. Document examples of misclassified emails
2. Check if specific pattern (e.g., all fraud alerts demoted, all receipts promoted)
3. If systematic: rollback immediately
4. If isolated edge cases: monitor for 24h before rollback

### 5. P95 Latency Spike (> Baseline + 1000ms)

**Baseline (from golden set):** TBD after Phase 0 complete
**Threshold:** P95 latency > `baseline_p95 + 1000ms` sustained for > 30 minutes

**Example:** If baseline P95 is 2000ms, trigger investigation if P95 exceeds 3000ms.

**Why 1000ms threshold:**
- Users tolerate up to 3-5s digest generation
- Sustained high latency indicates inefficient prompts, API throttling, or runaway complexity

**Detection:**
```bash
# Cloud Run P95 latency
gcloud monitoring time-series list \
  --filter='metric.type="run.googleapis.com/request_latencies"
            AND metric.labels.percentile="95"' \
  --format="table(metric.labels.percentile, value)"

# Or check recent classify timings:
gcloud logging read "resource.type=cloud_run_revision AND
  jsonPayload.event=classification.llm.success"
  --limit 100 --format json | jq '[.[] | .jsonPayload.elapsed_ms] | sort | .[95]'
```

**Rollback action:**
1. If spike correlates with deployment: rollback immediately
2. If gradual degradation: investigate prompt complexity, few-shot example count, or model changes
3. Consider prompt optimization before re-deploying

### 6. Cost Explosion (> Baseline + 50%)

**Baseline (from golden set):** TBD after Phase 0 complete (cost per email)
**Threshold:** Daily cost > `baseline_daily_cost * 1.5`

**Example:** If baseline is $0.50/day, trigger investigation if daily cost exceeds $0.75/day.

**Why 50% threshold:**
- Expected variance: ±20% based on email volume and complexity
- 50%+ spike = prompt inefficiency, excessive retries, or unintended model upgrade

**Detection:**
```bash
# Check recent LLM costs
sqlite3 shopq/data/shopq_tracking.db "
  SELECT
    DATE(timestamp) as date,
    COUNT(*) as emails_classified,
    SUM(llm_cost_usd) as daily_cost
  FROM classified_emails
  WHERE decider='gemini'
  GROUP BY DATE(timestamp)
  ORDER BY date DESC
  LIMIT 7
"

# Or estimate from token counts:
gcloud logging read "resource.type=cloud_run_revision AND
  jsonPayload.event=classification.llm.success"
  --limit 1000 --format json | jq '[.[] | .jsonPayload.tokens_used] | add'
```

**Rollback action:**
1. If cost spike correlates with prompt version change: rollback
2. If model provider increased pricing: negotiate or switch models
3. Optimize prompt (reduce few-shot examples, simplify instructions)

---

## Monitoring Commands

### Real-Time Health Check

```bash
# Quick sanity check (run every 5 minutes during deployment)
curl https://shopq-api.run.app/health

# Expected response:
# {"status": "healthy", "version": "gemini-2.0-flash/2.0/prompt-v1"}
```

### Classification Quality Metrics

```bash
# Recent classification confidence distribution
sqlite3 shopq/data/shopq.db "
  SELECT
    CASE
      WHEN type_conf >= 0.9 THEN 'high (≥0.9)'
      WHEN type_conf >= 0.7 THEN 'medium (0.7-0.9)'
      ELSE 'low (<0.7)'
    END as confidence_bucket,
    COUNT(*) as count,
    ROUND(AVG(type_conf), 3) as avg_conf
  FROM confidence_logs
  WHERE timestamp > datetime('now', '-24 hours')
  GROUP BY confidence_bucket
"
```

### Version Verification

```bash
# Verify all recent classifications use expected version
sqlite3 shopq/data/shopq.db "
  SELECT
    model_name,
    model_version,
    prompt_version,
    COUNT(*) as count
  FROM confidence_logs
  WHERE timestamp > datetime('now', '-1 hour')
  GROUP BY model_name, model_version, prompt_version
"

# Expected: All rows show current version from VERSIONS.md
```

### Error Rate Tracking

```bash
# Cloud Run errors (last hour)
gcloud logging read "resource.type=cloud_run_revision AND
  severity=ERROR AND
  timestamp > \"$(date -u -v-1H '+%Y-%m-%dT%H:%M:%SZ')\""
  --limit 50 --format json | jq -r '.[] | .jsonPayload.message'
```

### Golden Set Replay (Validation)

```bash
# Run golden set against current production version
PYTHONPATH=. pytest tests/test_importance_baseline.py -v

# Compare to baseline
python scripts/check_importance_baseline.py --compare

# Expected:
# ✓ All metrics within ±2pp of baseline
# ✓ No OTP in critical
# ✓ No systematic misclassifications
```

---

## Rollback Procedures

### Procedure 1: Immediate Traffic Shift (< 5 minutes)

**Use when:** Auto-rollback trigger fires (OTP in critical, error rate > 5%)

```bash
# Option A: Cloud Console (fastest)
# 1. Go to https://console.cloud.google.com/run
# 2. Click "shopq-api" service
# 3. Click "Revisions" tab
# 4. Find previous stable revision (check timestamp)
# 5. Click "..." menu → "Manage Traffic"
# 6. Set previous revision to 100%, current to 0%
# 7. Click "Save"

# Option B: CLI
gcloud run services update-traffic shopq-api \
  --to-revisions PREVIOUS=100 \
  --platform managed \
  --region us-central1

# Verify rollback
gcloud run services describe shopq-api \
  --platform managed \
  --region us-central1 \
  --format="get(status.traffic)"
```

### Procedure 2: Disable LLM Only (< 2 minutes)

**Use when:** LLM-specific issues (invalid JSON rate, cost explosion) but rules-engine works

```bash
# Disable LLM, fall back to rules
gcloud run services update shopq-api \
  --update-env-vars SHOPQ_USE_LLM=false \
  --platform managed \
  --region us-central1

# Verify flag updated
gcloud run services describe shopq-api \
  --platform managed \
  --region us-central1 \
  --format="get(spec.template.spec.containers[0].env)"
```

### Procedure 3: Revert Model/Prompt Version (< 10 minutes)

**Use when:** Version change caused precision drop or latency spike

```bash
# 1. Update versioning constants to previous version
# Edit shopq/versioning.py:
#   MODEL_VERSION = "1.5"  # or previous
#   PROMPT_VERSION = "v0"  # or previous

# 2. Add rollback entry to VERSIONS.md
echo "| $(date +%Y-%m-%d) | gemini-2.0-flash | 1.5 | v0 | ROLLBACK: Critical precision drop from v2.0/v1 |" >> VERSIONS.md

# 3. Commit and deploy
git add shopq/versioning.py VERSIONS.md
git commit -m "rollback: Revert to model v1.5/prompt v0 due to precision drop"
git push origin main

# 4. Deploy immediately (no canary)
gcloud run deploy shopq-api \
  --source . \
  --platform managed \
  --region us-central1

# 5. Verify version in logs
gcloud logging read "resource.type=cloud_run_revision AND
  jsonPayload.event=classification.llm.success"
  --limit 5 --format json | jq '.[] | .jsonPayload | {model_version, prompt_version}'
```

### Procedure 4: Full Code Revert (< 15 minutes)

**Use when:** Code changes (not just version bump) caused regression

```bash
# 1. Find last known good commit
git log --oneline -20

# 2. Create revert commit
git revert <bad-commit-hash>

# Or reset to previous commit (if not yet pushed to main)
git reset --hard <good-commit-hash>
git push origin main --force  # ⚠️ Use with caution

# 3. Redeploy
gcloud run deploy shopq-api \
  --source . \
  --platform managed \
  --region us-central1

# 4. Verify deployment
curl https://shopq-api.run.app/health
```

---

## Post-Rollback Validation

After any rollback, verify system health:

### Validation Checklist

- [ ] **Error rate < 1%** (check Cloud Run metrics)
- [ ] **P95 latency < baseline + 500ms** (check monitoring)
- [ ] **Version verified** (check logs for correct model/prompt version)
- [ ] **Golden set passing** (run `pytest tests/test_importance_baseline.py`)
- [ ] **No OTP in critical** (manual digest review)
- [ ] **Cost normalized** (check daily spend)
- [ ] **Incident report created** (document root cause, timeline, impact)

### Incident Report Template

```markdown
# Incident Report: [Brief Title]

**Date:** YYYY-MM-DD
**Duration:** [Start time] - [End time]
**Severity:** [Critical / High / Medium]

## Timeline
- HH:MM - Deployed version X
- HH:MM - Alert triggered: [condition]
- HH:MM - Rollback initiated
- HH:MM - Rollback complete, system stable

## Root Cause
[What caused the issue - code change, model behavior, prompt change, etc.]

## Impact
- [Number] emails misclassified
- [Number] users affected
- Cost: $[amount] overspent
- Precision drop: [baseline → observed]

## Resolution
[What was rolled back, how system was restored]

## Prevention
- [ ] Add test case to catch this regression
- [ ] Update ROLLBACK_CONDITIONS.md with new threshold
- [ ] Update CI to block similar changes
- [ ] Document in VERSIONS.md

## Follow-Up
- [ ] Post-mortem scheduled for [date]
- [ ] Fix implemented and validated offline
- [ ] Re-deployment plan approved
```

---

## Baseline Metrics (To Be Filled After Phase 0)

**Once golden dataset is complete, fill in these baseline values:**

| Metric | Baseline Value | Measurement Date | Rollback Threshold |
|--------|----------------|------------------|-------------------|
| Critical Precision | _TBD_ | _TBD_ | baseline − 5pp |
| Time-Sensitive Precision | _TBD_ | _TBD_ | baseline − 5pp |
| Routine Precision | _TBD_ | _TBD_ | baseline − 5pp |
| Overall Accuracy | _TBD_ | _TBD_ | baseline − 3pp |
| P50 Latency | _TBD_ | _TBD_ | baseline + 500ms |
| P95 Latency | _TBD_ | _TBD_ | baseline + 1000ms |
| P99 Latency | _TBD_ | _TBD_ | baseline + 2000ms |
| Cost per Email | _TBD_ | _TBD_ | baseline + 50% |
| Daily Cost (50 users) | _TBD_ | _TBD_ | baseline + 50% |
| Invalid JSON Rate | _TBD_ | _TBD_ | > 10% |

**How to measure baseline:**
```bash
# After completing golden dataset labeling:
python scripts/check_importance_baseline.py --update

# This generates eval/baseline.json with:
# - Precision/recall per importance class
# - Overall accuracy
# - Confusion matrix
# - Cost and latency percentiles

# Copy values to table above
```

---

## Related Documentation

- **DEPLOYMENT_PLAYBOOK.md** - Full deployment procedures including canary and monitoring
- **VERSIONS.md** - Model and prompt version history
- **CONTRIBUTING.md** - Version change workflow (shadow period, golden set replay)
- **config/shopq_policy.yaml** - Runtime threshold configuration
- **MONITORING_ALERTS.md** - Alert setup and escalation paths (if exists)

---

**Maintenance:** Review this document after each incident. Update thresholds based on actual production variance. Baseline values must be refreshed whenever golden dataset is updated or classification logic changes.
