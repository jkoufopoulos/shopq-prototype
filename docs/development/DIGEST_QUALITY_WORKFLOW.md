# Digest Quality Monitoring Workflow

Automated tracking and comparison of digest output to ensure continuous improvement.

## Overview

Every digest generation is automatically logged and can be compared against the ideal target to identify gaps and track improvements over time.

## Architecture

```
Digest Generation (mailq/api.py)
    ↓
Automatic Logging
    ↓
quality_logs/actual_digest_TIMESTAMP.html
    ↓
Manual Review & Comparison Script
    ↓
docs/ACTUAL_VS_IDEAL_COMPARISON.md (updated)
    ↓
Identify Gaps → Fix Classification → Re-test
```

## Files

| File | Purpose |
|------|---------|
| `quality_logs/actual_digest_*.html` | Auto-generated digest outputs with metadata |
| `quality_logs/input_emails_*.json` | Input emails for each digest |
| `quality_logs/comparison_*.md` | Fresh comparison per digest (ACTUAL vs SUGGESTED IDEAL) |
| `generate_digest_comparison.py` | Creates fresh comparison with AI-suggested ideal |
| `review_digest_quality.py` | Interactive review tool for inputs |
| `docs/archive/comparison_20251101_example.md` | Example comparison (archived) |

## Workflow

### Step 1: Generate Digest

Digest is automatically generated when:
- User triggers digest in Chrome extension
- API call to `/api/context-digest`
- Test digest generation script

**Automatic logging**: Every digest creates TWO files:
1. `quality_logs/actual_digest_TIMESTAMP.html` - The digest output
2. `quality_logs/input_emails_TIMESTAMP.json` - The input emails

This allows you to review what went IN and what came OUT.

### Step 2: Review Input & Output

Use the review script to see both:
```bash
python review_digest_quality.py
```

This will show you:
- All input emails grouped by type
- What the digest actually featured
- Prompts to help you determine the ideal

Or review manually:
```bash
# View input emails
cat quality_logs/$(ls -t quality_logs/input_emails_*.json | head -1) | jq .

# View digest output
open quality_logs/$(ls -t quality_logs/actual_digest_*.html | head -1)
```

### Step 3: Determine Your Ideal

**Important**: The IDEAL section in the comparison file is just an example from November 1st.
For YOUR digest, you need to manually determine what SHOULD have been featured by:

1. Reviewing the input emails (from `input_emails_*.json`)
2. Identifying critical items (bills, alerts, security issues)
3. Identifying time-sensitive items (deliveries today, upcoming events)
4. Identifying worth-knowing items (jobs, shipments, financial updates)
5. Identifying noise that shouldn't be featured (promotions, past events)

The `review_digest_quality.py` script helps guide you through this process.

### Step 4: Generate Comparison with Suggested Ideal

Run the script to create a fresh comparison file:
```bash
python generate_digest_comparison.py
```

This will:
1. Find the latest `input_emails_*.json` and `actual_digest_*.html`
2. Run importance classifier on inputs to SUGGEST what should be featured
3. Create a fresh `quality_logs/comparison_TIMESTAMP.md` file
4. Include both ACTUAL and SUGGESTED IDEAL

Output:
```
📊 Generating Digest Comparison with Suggested Ideal

✅ Found files:
   Input:  input_emails_20251106_120000.json
   Output: actual_digest_20251106_120000.html

📧 Loading input emails...
   Loaded 99 emails

🤖 Running importance classifier to suggest ideal...
   Suggested ideal: 28 items
   - Critical: 8
   - Today: 3
   - Coming up: 12
   - Worth knowing: 5

📄 Extracting actual digest content...
   Actual featured: 12 items
   Actual critical: 3 items

✏️  Generating comparison file...

🎉 Comparison file created: quality_logs/comparison_20251106_120000.md
```

### Step 5: Review and Edit Suggested Ideal

Open the comparison file:
```bash
open quality_logs/comparison_20251106_120000.md
```

The file contains:
- **ACTUAL DIGEST**: What the system produced
- **SUGGESTED IDEAL**: What the classifier thinks should be featured (may be wrong!)

**Important**: Review and edit the SUGGESTED IDEAL section! The importance classifier may:
- Miss items that should be featured
- Suggest items that shouldn't be featured
- Miscategorize items (critical vs today vs coming up)

Edit based on your manual review of the inputs.

### Step 6: Compare ACTUAL vs Your Edited IDEAL

After editing the SUGGESTED IDEAL section to match what you think is correct, you now have a meaningful comparison:
- **ACTUAL DIGEST**: What the system produced
- **YOUR IDEAL**: What it SHOULD produce (classifier suggestions + your edits)

### Step 7: Identify Gaps

The comparison file includes:
- ✅ **What Actual Got Right**: Items correctly featured
- ❌ **False Positives**: Items that shouldn't be featured
- ❌ **False Negatives**: Important items missing

Example gap analysis:
```
Gap Analysis:
- Missing 7/8 critical items (bills, statements)
- Missing 2/3 deliveries
- 3 past events wrongly featured
```

### Step 6: Fix Classification Issues

Based on gaps, fix the classification logic:

**For missing items:**
- Check `mailq/importance_classifier.py` patterns
- Add missing keywords (e.g., "bill due", "delivered:")
- Update pattern categorization

**For false positives:**
- Strengthen filtering in `mailq/filters/time_decay.py`
- Add promotional detection patterns
- Improve time-based filtering

**For wrong framing:**
- Update `mailq/context_digest.py` entity extraction
- Improve title generation logic

### Step 7: Test & Iterate

1. Generate new digest with fixes
2. Check new `quality_logs/actual_digest_*.html` file
3. Run `python update_digest_comparison.py`
4. Review improvements in comparison file
5. Repeat until metrics meet targets

## Performance Targets

| Metric | Target | Status |
|--------|--------|--------|
| **Precision** | ≥75% | Track in comparison file |
| **Recall** | ≥70% | Track in comparison file |
| **Noise Filtered** | ≤25% | Track in comparison file |

## Example Session

```bash
# 1. Generate digest (via extension or test)
# Automatic: digest saved to quality_logs/actual_digest_20251106_120000.html

# 2. Quick check
cat quality_logs/actual_digest_20251106_120000.html | grep "Featured:"
# Output: <!-- Featured: 15 -->

# 3. Update comparison
python update_digest_comparison.py
# ✅ Updated docs/ACTUAL_VS_IDEAL_COMPARISON.md
#    Featured: 15 items
#    Critical: 4 items

# 4. Review comparison
open docs/ACTUAL_VS_IDEAL_COMPARISON.md

# 5. Identify missing items
# Example: "Con Edison bill" not featured (should be critical)

# 6. Fix pattern in importance_classifier.py
# Add: 'con edison', 'utility bill' to CRITICAL_PATTERNS

# 7. Re-test
# Generate new digest and repeat
```

## Tracking Improvements

Keep history of comparisons:
```bash
# Create snapshots before major changes
cp docs/ACTUAL_VS_IDEAL_COMPARISON.md \
   docs/archive/comparison_$(date +%Y%m%d).md

# Track digest outputs
ls -lh quality_logs/actual_digest_*.html

# Compare consecutive runs
diff quality_logs/actual_digest_20251106_120000.html \
     quality_logs/actual_digest_20251106_130000.html
```

## Maintenance

**Clean up old logs** (after reviewing):
```bash
# Keep last 10 digests
ls -t quality_logs/actual_digest_*.html | tail -n +11 | xargs rm
```

**Archive comparison snapshots**:
```bash
# Before major refactors
cp docs/ACTUAL_VS_IDEAL_COMPARISON.md \
   docs/archive/ACTUAL_VS_IDEAL_COMPARISON_$(date +%Y%m%d).md
```

## Tips

1. **Generate digests regularly** during development to catch regressions
2. **Compare before/after** when changing classification logic
3. **Use timestamps** in filenames to track progression
4. **Keep IDEAL up to date** as requirements evolve
5. **Track metrics** (precision, recall) in comparison file

## Troubleshooting

**No digest files in quality_logs/**:
- Check that digest generation is working
- Verify API endpoint `/api/context-digest` is called
- Check logs for errors

**Comparison script fails**:
- Verify `quality_logs/` directory exists
- Check file permissions
- Ensure latest Python 3.x installed

**ACTUAL section not updating**:
- Check that `docs/ACTUAL_VS_IDEAL_COMPARISON.md` exists
- Verify file has "### ACTUAL DIGEST" and "### IDEAL DIGEST" markers
- Check script output for errors

## See Also

- `docs/ACTUAL_VS_IDEAL_COMPARISON.md` - Current comparison
- `mailq/importance_classifier.py` - Pattern-based classification
- `mailq/context_digest.py` - Digest generation logic
- `mailq/filters/time_decay.py` - Time-based filtering
