# Model/Prompt Rollback Runbook

**Purpose**: Define exact conditions that trigger rollback and step-by-step procedures to revert model or prompt versions safely.

**Last Updated**: 2025-11-11

---

## Table of Contents

1. [Rollback Triggers](#rollback-triggers)
2. [Pre-Rollback Checklist](#pre-rollback-checklist)
3. [Rollback Procedures](#rollback-procedures)
4. [Post-Rollback Verification](#post-rollback-verification)
5. [Root Cause Analysis Template](#root-cause-analysis-template)

---

## Rollback Triggers

Rollback is triggered **automatically** or **manually** when any of these conditions occur:

### 🔴 Automatic Triggers (Critical - Immediate Rollback)

#### 1. OTP in CRITICAL > 0
**Condition**: ANY verification code or OTP appears in CRITICAL importance emails

**Why critical**: This violates user trust and safety - verification codes should NEVER surface as critical
**Detection**:
- Quality monitoring checks: `SELECT COUNT(*) FROM classified WHERE importance='critical' AND (snippet LIKE '%verification code%' OR snippet LIKE '%OTP%')`
- Guardrails should prevent this, but if they fail, this is P0

**Action**: Immediate rollback + incident review

---

#### 2. Critical Precision < 90%
**Condition**: Precision for CRITICAL importance falls below 90% on Golden Dataset

**Why critical**: False positives in CRITICAL erode user trust rapidly
**Measurement**:
```bash
./scripts/test_against_gds.sh --report
# Check: critical_precision in output
```

**Threshold**:
- ✅ Healthy: ≥95% precision
- ⚠️ Warning: 90-95% precision (monitor closely)
- 🔴 **Rollback**: <90% precision

**Action**: Revert to previous model/prompt version

---

#### 3. Critical Recall < 80%
**Condition**: Recall for CRITICAL importance falls below 80% on Golden Dataset

**Why critical**: Missing truly critical emails defeats the purpose
**Measurement**: Same as precision (GDS eval)

**Threshold**:
- ✅ Healthy: ≥85% recall
- ⚠️ Warning: 80-85% recall (monitor)
- 🔴 **Rollback**: <80% recall

**Action**: Revert to previous model/prompt version

---

### ⚠️ Manual Triggers (Warning - Investigate First)

#### 4. False Positive Budget Exceeded
**Condition**: >5 false positives per 100 emails in production traffic (rolling 24h window)

**Why warning**: Indicates degraded quality but not immediate failure
**Detection**:
```sql
-- Check FP rate from user corrections
SELECT
  COUNT(*) as total_corrections,
  SUM(CASE WHEN old_importance = 'critical' AND new_importance != 'critical' THEN 1 ELSE 0 END) as critical_fps,
  (critical_fps * 100.0 / total_corrections) as fp_rate
FROM user_corrections
WHERE created_at > datetime('now', '-24 hours');
```

**Action**: Investigate root cause → consider rollback if FP rate continues to rise

---

#### 5. Latency Spike (P95 > 3s)
**Condition**: P95 classification latency exceeds 3 seconds for >10 minutes

**Why warning**: Poor UX, may indicate model/API issues
**Detection**: Check logs for `classification.llm.latency` metric

**Action**:
1. Check Vertex AI status
2. Verify model version didn't change unexpectedly
3. Consider rollback if latency persists >30min

---

#### 6. Cost Spike (>2x baseline)
**Condition**: Daily classification cost exceeds 2x baseline for current traffic

**Why warning**: May indicate inefficient prompts or unexpected behavior
**Detection**: Check Vertex AI billing dashboard

**Baseline costs**:
- Gemini 2.0 Flash: ~$0.001 per classification
- Target: <$5/day for 5000 emails/day

**Action**: Investigate prompt changes → optimize or rollback if cost unsustainable

---

#### 7. Importance Distribution Drift (±10pp)
**Condition**: Importance distribution shifts by more than 10 percentage points from baseline

**Why warning**: May indicate systematic bias in new model/prompt
**Detection**:
```sql
-- Compare current vs baseline distribution
SELECT
  importance,
  COUNT(*) * 100.0 / SUM(COUNT(*)) OVER() as percentage
FROM classified
WHERE created_at > datetime('now', '-24 hours')
GROUP BY importance;

-- Baseline (from GDS):
-- critical: ~15%
-- time_sensitive: ~25%
-- routine: ~60%
```

**Acceptable drift**: ±5pp
**Warning drift**: 5-10pp
**Rollback trigger**: >10pp

**Action**: Investigate cause → rollback if drift is systematic

---

## Pre-Rollback Checklist

Before executing rollback:

- [ ] **Confirm trigger condition** - Verify metrics/logs show rollback condition
- [ ] **Check current version** - Note exact model/prompt versions in production
  ```bash
  grep -r "MODEL_VERSION\|PROMPT_VERSION" shopq/versioning.py
  ```
- [ ] **Identify rollback target** - Determine which version to revert to (usually previous stable version)
- [ ] **Notify team** - Alert on Slack/Discord that rollback is imminent
- [ ] **Capture current state** - Export current metrics for post-mortem
  ```bash
  ./scripts/eval_baseline_gds1.py > /tmp/pre_rollback_baseline_$(date +%Y%m%d_%H%M%S).json
  ```

---

## Rollback Procedures

### Option A: Prompt-Only Rollback (Fast - 5 minutes)

**When to use**: Prompt version changed but model version is same

**Steps**:

1. **Revert prompt file**:
   ```bash
   cd /Users/justinkoufopoulos/Projects/mailq-prototype
   git log --oneline shopq/prompts/classifier_prompt.txt | head -10
   # Find commit hash before problematic change
   git checkout <previous-commit-hash> -- shopq/prompts/classifier_prompt.txt
   ```

2. **Update version constant**:
   ```bash
   # Edit shopq/versioning.py
   # Change PROMPT_VERSION from "v2" back to "v1" (or appropriate version)
   ```

3. **Run quick validation**:
   ```bash
   # Test on 10 sample emails
   python3 scripts/quick_smoke_test.py
   ```

4. **Deploy** (if validation passes):
   ```bash
   git add shopq/prompts/classifier_prompt.txt shopq/versioning.py
   git commit -m "rollback: Revert prompt to v1 due to [trigger reason]"
   ./deploy.sh
   ```

5. **Monitor for 30 minutes** - Watch metrics to confirm rollback resolves issue

---

### Option B: Model Version Rollback (Medium - 15 minutes)

**When to use**: Model version changed (e.g., gemini-2.0-flash → gemini-1.5-flash)

**Steps**:

1. **Update model configuration**:
   ```bash
   # Edit shopq/versioning.py
   MODEL_NAME = "gemini-1.5-flash"  # Revert from 2.0
   MODEL_VERSION = "1.5"
   ```

2. **Update VertexGeminiClassifier** (if needed):
   ```python
   # shopq/vertex_gemini_classifier.py
   # Line ~39: Change model initialization
   self.model = GenerativeModel("gemini-1.5-flash")
   ```

3. **Run GDS validation**:
   ```bash
   ./scripts/test_against_gds.sh --verbose
   # Verify: critical precision ≥95%, recall ≥85%
   ```

4. **Deploy** (if validation passes):
   ```bash
   git add shopq/versioning.py shopq/vertex_gemini_classifier.py
   git commit -m "rollback: Revert to Gemini 1.5 Flash due to [trigger reason]"
   ./deploy.sh
   ```

5. **Monitor for 1 hour** - Model changes may have subtle effects

---

### Option C: Full Rollback (Slow - 30 minutes)

**When to use**: Multiple changes combined (model + prompt + code changes)

**Steps**:

1. **Identify last stable release**:
   ```bash
   git log --oneline --all --graph | head -20
   # Find commit tagged as stable (e.g., "v1.2.0-stable")
   ```

2. **Create rollback branch**:
   ```bash
   git checkout -b rollback/$(date +%Y%m%d-%H%M)
   git revert <problematic-commit-hash>
   # OR full reset:
   git reset --hard <last-stable-commit>
   ```

3. **Run full test suite**:
   ```bash
   PYTHONPATH=. pytest tests/ -v
   ./scripts/test_against_gds.sh
   ```

4. **Deploy with care**:
   ```bash
   git push origin rollback/$(date +%Y%m%d-%H%M)
   ./deploy.sh
   ```

5. **Monitor for 2 hours** - Full changes need thorough validation

---

## Post-Rollback Verification

After rollback, verify these metrics return to baseline:

### Immediate (0-30 minutes)

- [ ] **OTP in CRITICAL** == 0
  ```sql
  SELECT COUNT(*) FROM classified
  WHERE importance='critical'
  AND (snippet LIKE '%verification%' OR snippet LIKE '%OTP%')
  AND created_at > datetime('now', '-30 minutes');
  ```

- [ ] **Latency P95** < 2s
  ```bash
  # Check logs for classification.llm.latency metric
  ```

- [ ] **No errors** in classification pipeline
  ```bash
  grep "ERROR" /tmp/shopq-api.log | tail -20
  ```

### Short-term (1-4 hours)

- [ ] **Critical precision** ≥95% on live traffic
- [ ] **Critical recall** ≥85% on live traffic
- [ ] **Cost per classification** within baseline (≤$0.001)
- [ ] **Importance distribution** within ±5pp of baseline

### Long-term (24 hours)

- [ ] **User corrections** not elevated (FP rate <3%)
- [ ] **No recurring quality issues** in monitoring
- [ ] **Baseline metrics stable** on golden dataset

---

## Root Cause Analysis Template

After rollback, conduct RCA:

### 1. Incident Summary

**Date/Time**: [YYYY-MM-DD HH:MM UTC]
**Trigger**: [Which rollback condition triggered]
**Version Rolled Back From**: Model [X], Prompt [Y]
**Version Rolled Back To**: Model [X-1], Prompt [Y-1]
**Duration of Incident**: [X hours]
**Impact**: [How many users/emails affected]

### 2. Timeline

- **T+0min**: [Trigger detected]
- **T+5min**: [Rollback initiated]
- **T+15min**: [Rollback deployed]
- **T+30min**: [Metrics confirmed stable]

### 3. Root Cause

**What changed**: [Describe model/prompt change]
**Why it caused issue**: [Technical explanation]
**How it bypassed safeguards**: [Why tests didn't catch it]

### 4. Lessons Learned

**What went well**:
- [e.g., Rollback executed quickly]
- [e.g., Monitoring detected issue before users reported]

**What needs improvement**:
- [e.g., Need better pre-deployment validation]
- [e.g., Shadow period was too short]

### 5. Action Items

- [ ] **Prevent recurrence**: [Specific fix]
- [ ] **Improve detection**: [Better monitoring]
- [ ] **Update process**: [Change deployment workflow]

---

## Version Change Workflow (Prevention)

To prevent rollbacks, follow this workflow for ALL model/prompt changes:

### Before Changing Version

1. **Document intent** in VERSIONS.md at repo root
2. **Run golden set baseline**:
   ```bash
   ./scripts/test_against_gds.sh > baseline_v$(version).txt
   ```
3. **Review changes with team** (if major version bump)

### During Change

4. **Update shopq/versioning.py** (single source of truth)
5. **Run tests**:
   ```bash
   pytest tests/ -v
   ./scripts/test_against_gds.sh --verbose
   ```
6. **Verify thresholds met**:
   - Critical precision ≥95%
   - Critical recall ≥85%
   - OTP in CRITICAL == 0

### After Change

7. **Shadow period** (3 days minimum):
   ```bash
   # Log both old and new model outputs
   # Compare distributions, drift, edge cases
   ```
8. **Deploy to production** only after shadow period passes
9. **Monitor closely** for 48 hours post-deployment
10. **Update baseline.md** with new version metrics

---

## Emergency Contacts

**On-Call Engineer**: [Slack @oncall]
**Vertex AI Status**: https://status.cloud.google.com/
**Deployment Logs**: `/tmp/shopq-api.log`
**Metrics Dashboard**: [Link to monitoring]

---

## Related Documentation

- `shopq/versioning.py` - Version constants (single source of truth)
- `VERSIONS.md` - Version change history (to be created)
- `docs/CLASSIFICATION_REFACTOR_PLAN.md` - Architecture reference
- `scripts/test_against_gds.sh` - Golden dataset validation

---

**Version**: 1.0
**Owner**: ShopQ Team
**Last Reviewed**: 2025-11-11
