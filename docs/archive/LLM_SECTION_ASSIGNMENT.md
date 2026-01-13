# LLM-Based Section Assignment

**Date**: 2025-11-14
**Status**: Implemented, ready for testing

---

## Overview

Added **hybrid LLM-based section assignment** to the V2 digest pipeline, following the same architecture as GDS classification (Rules → LLM fallback).

This addresses the 60% → 85% accuracy gap identified in Dataset 2 evaluation.

---

## Architecture

### **Before** (Rules Only)
```
Email → T0 Section Assignment (331 lines of rules) → T1 Temporal Decay
         ↓
    60% accuracy on Dataset 2
    Over-classifies WORTH_KNOWING
    Misses newsletters/content patterns
```

### **After** (Hybrid: Rules + LLM)
```
Email → Fast Rules → [Match?] → T0 Section
              ↓ No match (ambiguous)
         LLM Classifier → Validation → T0 Section
              ↓
         T1 Temporal Decay
```

---

## Implementation

### **Files Created**

1. **`mailq/prompts/section_assignment_prompt.txt`**
   - LLM prompt for T0 section classification
   - Explains sections, patterns, and rules
   - Instructs LLM on content vs transactional distinction

2. **`concepts/llm_section_classifier.py`**
   - `classify_section_with_llm()` - Calls Gemini API
   - `validate_llm_section()` - Validates LLM output against rules
   - `classify_with_hybrid()` - Orchestrates rules + LLM

3. **`scripts/test_llm_section_assignment.py`**
   - Test script to evaluate LLM-based assignment
   - Compares accuracy with/without LLM fallback

### **Files Modified**

1. **`concepts/section_assignment_t0.py`**
   - Added LLM fallback at end of function
   - Only triggers if `MAILQ_LLM_SECTION_FALLBACK=true`
   - Falls back to "noise" if LLM fails

2. **`.env.example`**
   - Added `MAILQ_LLM_SECTION_FALLBACK` flag
   - Documented feature and cost implications

---

## How It Works

### **Fast Path (Rules)**

Obvious patterns are handled by rules (no LLM cost):

```python
# Critical patterns
if "verification code" in subject:
    return "critical"

# Receipt patterns
if "receipt" in subject or "order confirmation" in subject:
    return "worth_knowing"

# Event patterns
if temporal_ctx and temporal_ctx.get("event_time"):
    return "today"
```

**Cost**: Free
**Latency**: < 1ms
**Coverage**: ~40% of emails

---

### **Slow Path (LLM Fallback)**

Ambiguous cases use LLM:

```python
# LLM sees patterns rules can't encode:
# "7 Counterintuitive Product Lessons" → everything_else
# "This week in Stratechery" → everything_else
# "Technically Monthly (November 2025)" → everything_else

llm_section = classify_section_with_llm(email, temporal_ctx)
```

**Cost**: ~$0.0001 per email
**Latency**: 200-500ms
**Coverage**: ~60% of emails (the ambiguous ones)

---

### **Validation Layer**

LLM output is validated against critical rules:

```python
# Validation catches obvious LLM mistakes:
if "verification code" in subject and llm_section != "critical":
    return fallback_to_rules(email)

if "newsletter" in subject and llm_section == "worth_knowing":
    return fallback_to_rules(email)
```

---

## Testing

### **Enable LLM Fallback**

Add to `.env`:
```bash
MAILQ_LLM_SECTION_FALLBACK=true
```

### **Run Evaluation**

```bash
# Test with LLM enabled
MAILQ_LLM_SECTION_FALLBACK=true python scripts/test_llm_section_assignment.py

# Compare with rules-only baseline
MAILQ_LLM_SECTION_FALLBACK=false python scripts/test_llm_section_assignment.py
```

### **Expected Results**

Based on Dataset 2 analysis:

| Metric | Rules Only | With LLM | Improvement |
|--------|------------|----------|-------------|
| Overall Accuracy | 60.0% | **75-85%** | +15-25pp |
| Newsletter Detection | Poor | **Excellent** | Fixes 20 emails |
| Content vs Transactional | Poor | **Good** | Major fix |
| Edge Cases | Misses | **Handles** | More robust |

---

## Cost Analysis

### **Current (Rules Only)**
- Cost per email: $0 (rules only)
- Accuracy: 60%
- Maintainability: Low (331 lines of rules)

### **With LLM Fallback**
- Cost per email: ~$0.00006 average (60% × $0.0001)
- Accuracy: **75-85%** (projected)
- Maintainability: **High** (rules + flexible LLM)

### **Cost at Scale**

| Users | Emails/day | LLM Calls/day | Cost/day | Cost/month |
|-------|------------|---------------|----------|------------|
| 100   | 10,000     | 6,000         | $0.60    | $18        |
| 1,000 | 100,000    | 60,000        | $6.00    | $180       |
| 10,000| 1,000,000  | 600,000       | $60.00   | $1,800     |

**Trade-off**: Spend ~$18-1800/month to improve accuracy by 15-25pp.

---

## Rollout Strategy

### **Phase 1: Testing** (Current)
- LLM fallback **OFF** by default
- Manual testing on Dataset 2
- Measure accuracy improvement
- Validate cost estimates

### **Phase 2: Dogfooding**
- Enable for internal users only
- Monitor accuracy, cost, latency
- Collect edge cases
- Refine prompt based on failures

### **Phase 3: Gradual Rollout**
- Start at 1% of users
- Monitor metrics (accuracy, cost, latency)
- Increase to 10% → 50% → 100%
- A/B test with rules-only control group

### **Phase 4: Production**
- LLM fallback **ON** by default
- Rules handle obvious cases (fast, free)
- LLM handles ambiguous cases (accurate, cheap)

---

## Monitoring

### **Key Metrics**

Track in production:

1. **Accuracy**
   - Section assignment accuracy vs ground truth
   - Newsletter detection rate
   - Content vs transactional precision

2. **Cost**
   - LLM API calls per day
   - Cost per user per month
   - % of emails using LLM vs rules

3. **Latency**
   - P50, P95, P99 classification latency
   - Rules path vs LLM path latency

4. **Errors**
   - LLM validation failures
   - LLM API errors
   - Fallback to "noise" rate

### **Logging**

All LLM classifications are logged with:
```python
logger.info("LLM section assignment", extra={
    "email_subject": subject,
    "section": llm_section,
    "source": "llm_fallback",
    "validation": "passed",
})
```

Query logs to find patterns:
- Which emails trigger LLM?
- What sections does LLM assign?
- Where does validation fail?

---

## Principles Alignment

✅ **P1: Concepts Are Rooms**
- All LLM section logic in `concepts/llm_section_classifier.py`
- Single module, easy to understand

✅ **P2: Side Effects Are Loud**
- Functions declare LLM API calls in docstrings
- Logging shows when LLM is used

✅ **P3: Compiler Is Your Senior Engineer**
- All functions typed
- Validation catches invalid LLM output

✅ **P4: Explicit Dependencies**
- Feature flag controls LLM fallback
- Clear when LLM is used vs rules

✅ **P5: Production Complexity vs Debt**
- This is **tuning** (improving accuracy)
- Not architecture debt (no structural changes)
- Hybrid approach follows existing GDS pattern

---

## Next Steps

1. **Test on Dataset 2**
   ```bash
   MAILQ_LLM_SECTION_FALLBACK=true python scripts/test_llm_section_assignment.py
   ```

2. **Measure Accuracy**
   - Compare with 60% baseline
   - Target: 75-85% accuracy

3. **Refine Prompt** (if needed)
   - Based on misclassifications
   - Edit `mailq/prompts/section_assignment_prompt.txt`

4. **Enable for Dogfooding**
   - Set `MAILQ_LLM_SECTION_FALLBACK=true` in production `.env`
   - Monitor cost, accuracy, latency

5. **Plan Gradual Rollout**
   - Add percentage-based rollout flag
   - A/B test with control group

---

## FAQs

### **Q: Why not just use LLM for everything?**

A: Rules are **free and fast** for obvious cases. Only use LLM for ambiguous emails where rules fail.

### **Q: What if LLM makes a mistake?**

A: Validation layer catches critical mistakes (e.g., verification codes not marked critical). Falls back to rules if validation fails.

### **Q: Can I edit the prompt without code changes?**

A: Yes! Edit `mailq/prompts/section_assignment_prompt.txt` and restart the server.

### **Q: How do I disable LLM fallback?**

A: Set `MAILQ_LLM_SECTION_FALLBACK=false` in `.env` (default is already false).

### **Q: What's the performance impact?**

A: LLM adds 200-500ms latency, but only for ~60% of emails (the ambiguous ones). Rules-based emails are still < 1ms.

---

**Status**: Ready for testing
**Next**: Run evaluation on Dataset 2 and measure accuracy
