# MailQ Deployment Playbook

## Overview

This playbook provides step-by-step procedures for deploying the refactored MailQ backend to production. Follow these steps in order to ensure a safe, monitored rollout.

## Pre-Deployment Checklist

Before deploying, verify:

- [ ] All 44+ tests passing locally (`pytest tests/contracts/ tests/adapters/ tests/soak/ tests/llm/ tests/integration/`)
- [ ] Code reviewed and approved
- [ ] Environment variables configured (see Configuration section)
- [ ] Database migrations prepared (if any)
- [ ] Monitoring and alerts configured
- [ ] Rollback plan reviewed and understood

## Configuration

### Required Environment Variables

```bash
# Google Cloud
export GOOGLE_CLOUD_PROJECT=mailq-467118
export GOOGLE_API_KEY=AIzaSy...

# Gemini Model
export GEMINI_MODEL=gemini-2.0-flash

# LLM Safety (disabled by default for safety)
export MAILQ_USE_LLM=false  # Set to "true" to enable after validation

# API Port (optional)
export API_PORT=8000
```

### Feature Flags

| Flag | Default | Description | When to Enable |
|------|---------|-------------|----------------|
| `MAILQ_USE_LLM` | `false` | Enable LLM classification | After rules-only validation passes |
| `USE_RULES_ENGINE` | `true` | Enable rules-based classification | Always enabled |
| `USE_AI_CLASSIFIER` | `true` | Enable AI classifier (fallback to rules) | Always enabled |

## Deployment Steps

### Stage 1: Canary Deployment (10% Traffic)

1. **Deploy to production with traffic splitting**
   ```bash
   # Deploy new version without traffic
   gcloud run deploy mailq-api \
     --source . \
     --platform managed \
     --region us-central1 \
     --no-traffic \
     --tag canary \
     --set-env-vars MAILQ_USE_LLM=false

   # Route 10% traffic to canary
   gcloud run services update-traffic mailq-api \
     --to-revisions canary=10,LATEST=90
   ```

2. **Monitor canary for 2 hours**
   - Check error rate: `< 1%`
   - Check P95 latency: `< 5s`
   - Check classification success rate: `> 99%`
   - Monitor counters:
     - `classification.rules_fallback` (should be ~100%)
     - `llm.disabled` (should increment)
     - `pipeline.completed` (should increment)
     - No `schema_validation_failures`

3. **Validation queries**
   ```bash
   # Check Cloud Run logs
   gcloud run services logs read mailq-api \
     --platform managed \
     --region us-central1 \
     --limit 1000 | grep ERROR

   # Should show minimal errors
   ```

### Stage 2: Full Production Rollout

1. **Increase traffic gradually**
   ```bash
   # 50% traffic
   gcloud run services update-traffic mailq-api \
     --to-revisions canary=50,LATEST=50

   # Wait 1 hour, monitor metrics

   # 100% traffic
   gcloud run services update-traffic mailq-api \
     --to-latest
   ```

2. **Final validation**
   - Verify all traffic on new version
   - Check metrics dashboard
   - Confirm no regression in:
     - Error rate
     - Latency (P50, P95, P99)
     - Classification accuracy

### Stage 3: Enable LLM (Optional)

**Only proceed if rules-only classification is working perfectly**

1. **Update environment variable**
   ```bash
   gcloud run services update mailq-api \
     --update-env-vars MAILQ_USE_LLM=true \
     --platform managed \
     --region us-central1
   ```

2. **Monitor LLM metrics**
   - `llm.call_success` (should increment)
   - `llm.cache_hit` (should grow over time)
   - `llm.schema_validation_failures` (should be `< 5%`)
   - `classification.llm_success` (should increment)

3. **Verify fallback behavior**
   - Inject LLM errors (temporarily disable API key)
   - Verify `classification.llm_error` increments
   - Verify `classification.rules_fallback` increments
   - Verify digest generation continues successfully

## Rollback Procedures

**See `docs/ROLLBACK_CONDITIONS.md` for complete rollback triggers, thresholds, and procedures.**

Quick reference below for common scenarios:

### Immediate Rollback (< 5 minutes)

If critical issues detected (see ROLLBACK_CONDITIONS.md for full trigger list):

```bash
# Rollback to previous revision
gcloud run services update-traffic mailq-api \
  --to-revisions LATEST=0,PREVIOUS=100 \
  --platform managed \
  --region us-central1

# Or rollback via Console:
# 1. Go to Cloud Run console
# 2. Click on mailq-api service
# 3. Click "Revisions" tab
# 4. Find previous stable revision
# 5. Click "Manage Traffic"
# 6. Route 100% to previous revision
```

### Disable LLM Only

If LLM causing issues but pipeline works:

```bash
gcloud run services update mailq-api \
  --update-env-vars MAILQ_USE_LLM=false \
  --platform managed \
  --region us-central1
```

### Rollback to Previous Code Version

```bash
# Find previous commit
git log --oneline -10

# Revert to previous commit
git revert <commit-hash>
git push origin main

# Redeploy
gcloud run deploy mailq-api --source .
```

## Post-Deployment Validation

### Automated Checks

```bash
# Run production health check
curl https://mailq-api.run.app/health

# Run synthetic monitoring
pytest tests/integration/test_e2e_pipeline.py --url=https://mailq-api.run.app
```

### Manual Verification

1. **Check Cloud Run Dashboard**
   - CPU utilization: `< 60%`
   - Memory usage: `< 512MB`
   - Request count: Trending as expected
   - Error rate: `< 1%`

2. **Check Logs**
   ```bash
   gcloud run services logs read mailq-api --limit=1000 | grep -E "(ERROR|WARN)"
   ```

3. **Verify Metrics**
   - `pipeline.total` P95: `< 10s`
   - `gmail.fetch.latency` P95: `< 2s`
   - `classification.rules_fallback`: `> 90%` (if LLM disabled)

## Monitoring & Alerts

### Key Metrics to Monitor

| Metric | Threshold | Alert Action |
|--------|-----------|--------------|
| Error rate | > 5% | Page on-call, consider rollback |
| P95 latency | > 10s | Investigate performance, scale up |
| `schema_validation_failures` | > 5% | Disable LLM, investigate schema drift |
| `llm.call_error` | > 10% | Disable LLM, check API status |
| `circuit_open_rate` | > 1/min | Investigate adapter failures |

### Alert Configuration

See `docs/MONITORING_ALERTS.md` for detailed alert setup.

## Troubleshooting

### Issue: High Error Rate

**Symptoms**: Error rate > 5%, many `pipeline.error` events

**Diagnosis**:
```bash
# Check error logs
gcloud run services logs read mailq-api --limit=1000 | grep ERROR

# Check which stage failing
gcloud run services logs read mailq-api --limit=1000 | grep "stage_error"
```

**Resolution**:
1. Identify failing stage (fetch, parse, classify, assemble)
2. If LLM-related: Disable LLM (`MAILQ_USE_LLM=false`)
3. If persistent: Rollback to previous version
4. Investigate offline, redeploy when fixed

### Issue: High Latency

**Symptoms**: P95 > 10s, slow response times

**Diagnosis**:
```bash
# Check latency breakdown
gcloud run services logs read mailq-api --limit=1000 | grep "timing="
```

**Resolution**:
1. Scale up Cloud Run instances
   ```bash
   gcloud run services update mailq-api --max-instances=10
   ```
2. Enable parallel processing (if not already)
3. Check for slow external calls (Gmail API, LLM)
4. Verify batch operations working

### Issue: Schema Validation Failures

**Symptoms**: `llm.schema_validation_failures` > 5%

**Diagnosis**:
```bash
# Check validation errors
gcloud run services logs read mailq-api --limit=1000 | grep "schema_validation_failed"
```

**Resolution**:
1. Disable LLM immediately (`MAILQ_USE_LLM=false`)
2. Review LLM output format changes
3. Update `domain/classify.py` LLMClassification schema if needed
4. Test offline before re-enabling

## Success Criteria

Deployment is successful when:

- [ ] Error rate < 1% sustained for 24 hours
- [ ] P95 latency < 5s for normal load
- [ ] P95 latency < 10s for high load (1000+ emails)
- [ ] All 44+ tests passing in production
- [ ] No schema validation failures
- [ ] Classification success rate > 99%
- [ ] Monitoring and alerts operational
- [ ] Rollback plan tested and documented

## Post-Launch

### Week 1: Close Monitoring

- Check metrics dashboard daily
- Review error logs
- Validate performance trends
- Collect user feedback

### Week 2: Enable LLM (if desired)

- Follow Stage 4 procedure
- Monitor LLM-specific metrics
- Validate cache hit rate growing
- Verify fallback behavior working

### Ongoing: Maintenance

- Review metrics weekly
- Update alert thresholds based on actual traffic
- Optimize based on P95 latency trends
- Plan capacity based on growth

---

**Last Updated**: 2025-11-02
**Version**: 1.0 (Post-Phase 5 Refactor)
**Owner**: Engineering Team
