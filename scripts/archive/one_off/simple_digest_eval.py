"""
Simple Digest Evaluation: What actually happened?

This script documents what the ACTUAL digest system did with Dataset 2.
Based on the logs from the failed run, we can extract the real performance metrics.
"""

from pathlib import Path

import pandas as pd

# Load Dataset 2
dataset_path = Path(__file__).parent.parent / "reports/dataset2_nov2-9_70_emails.csv"
df = pd.read_csv(dataset_path)

print("=" * 80)
print("ACTUAL DIGEST SYSTEM PERFORMANCE ON DATASET 2")
print("=" * 80)
print()

# From the logs, we know what happened:
print("📊 **WHAT THE SYSTEM ACTUALLY DID** (from logs):")
print()
print("Input: 70 emails from Dataset 2")
print()

print("Phase 1: Pre-filtering")
print("  - Filtered 8 expired events (11.4%)")
print("  - Remaining: 62 emails")
print()

print("Stage 1: Importance Classification")
print("  - Critical: 2 emails (2 threads)")
print("  - Time-sensitive: 3 emails (3 threads)")
print("  - Routine: 57 emails (57 threads)")
print()

print("Stage 2: Entity Extraction")
print("  - ❌ **ONLY 3 ENTITIES EXTRACTED FROM 70 EMAILS** (4.3% extraction rate)")
print("  - Entity 1: NotificationEntity (email_05)")
print("  - Entity 2: EventEntity - 'Action Required: Update Google Meet' (email_00)")
print("  - Entity 3: EventEntity - 'Braun Men's Aesthetic Event Tomorrow' (email_05)")
print()

print("Stage 3: Deduplication")
print("  - 3 entities after deduplication")
print()

print("Stage 3.5: Temporal Enrichment")
print("  - 3 processed, 0 escalated, 0 downgraded, 0 filtered")
print("  - All 3 entities remained visible")
print()

print("Stage 4: Timeline Building")
print("  - Featured: 3 entities")
print("  - Orphaned time-sensitive: 1 email")
print(
    "  - Noise breakdown: {'other': 38, 'shipment_notifications': 5, 'financial': 3, 'promotional': 10, 'receipts': 2}"
)
print()

print("Stage 6: Digest Generation")
print("  - ❌ **FAILED** - Error in hybrid_digest_renderer.py")
print("  - Error: AttributeError in _split_routine_emails() - email.get('type') on NoneType")
print()

print("=" * 80)
print("CRITICAL FINDINGS")
print("=" * 80)
print()

print("1. **Entity Extraction Rate: 4.3%** ❌")
print("   - Only 3 out of 70 emails converted to entities")
print("   - 67 emails (95.7%) were NOT extracted as entities")
print("   - This means the system is NOT creating structured entities for most emails")
print()

print("2. **Pre-filtering Removed 8 Expired Events** ✅")
print("   - filter_expired_events() correctly identified and removed 8 emails")
print("   - These were likely calendar notifications for past events")
print()

print("3. **Importance Classification Worked** ✅")
print("   - 2 critical (e.g., 'out for delivery')")
print("   - 3 time-sensitive (e.g., 'events_soon')")
print("   - 57 routine (newsletters, receipts, etc.)")
print()

print("4. **Digest Rendering Failed** ❌")
print("   - Error in hybrid_digest_renderer.py line 278")
print("   - Trying to call .lower() on None type")
print("   - Suggests email dict format mismatch")
print()

print("=" * 80)
print("ROOT CAUSE ANALYSIS")
print("=" * 80)
print()

print("**Why only 3 entities extracted?**")
print()
print("The HybridExtractor likely has strict rules for what becomes an entity:")
print("  - EventEntity: Requires event detection + temporal fields")
print("  - NotificationEntity: Requires specific notification patterns")
print("  - DeadlineEntity: Requires deadline keywords + dates")
print()
print("Most emails (95.7%) don't match these patterns, so they:")
print("  - Get classified for importance (critical/time_sensitive/routine)")
print("  - But DON'T get converted to entities")
print("  - End up in the 'noise summary' or 'orphaned' sections")
print()

print("**Comparison to Ground Truth:**")
print()

# Count ground truth sections
t0_counts = {
    "critical": (df["t0_critical"] == "X").sum(),
    "today": (df["t0_today"] == "X").sum(),
    "coming_up": (df["t0_coming_up"] == "X").sum(),
    "worth_knowing": (df["t0_worth_knowing"] == "X").sum(),
    "everything_else": (df["t0_everything_else"] == "X").sum(),
    "skip": (df["t0_skip"] == "X").sum(),
}

print("Ground Truth (T0) Section Distribution:")
for section, count in t0_counts.items():
    print(f"  {section.upper()}: {count} emails")

print()
print("System Distribution:")
print("  FEATURED (entities): 3 emails (4.3%)")
print("  ORPHANED TIME-SENSITIVE: 1 email")
print("  NOISE SUMMARY: 58 emails (82.9%)")
print("  FILTERED (expired): 8 emails (11.4%)")
print()

print("=" * 80)
print("CONCLUSION")
print("=" * 80)
print()

print("The actual digest system has a **fundamental architectural issue**:")
print()
print("1. ❌ **Entity extraction is too restrictive** - Only 4.3% of emails become entities")
print("2. ❌ **95.7% of emails** end up in generic 'noise summary'")
print("3. ❌ **Digest rendering failed** - email dict format mismatch")
print(
    "4. ✅ **Importance classification works** - correctly identified 2 critical, 3 time-sensitive"
)
print("5. ✅ **Temporal filtering works** - removed 8 expired events")
print()

print("**Expected vs. Actual:**")
print()
print("Expected (based on ground truth):")
print("  - 1 CRITICAL")
print("  - 14 TODAY")
print("  - 1 COMING_UP")
print("  - 30 WORTH_KNOWING")
print("  - 24 EVERYTHING_ELSE")
print()

print("Actual (what system did):")
print("  - 3 entities extracted (featured in digest)")
print("  - 1 orphaned time-sensitive")
print("  - 58 in noise summary")
print("  - 8 filtered (expired)")
print()

print("**The system is NOT creating a structured digest with clear sections.**")
print("Instead, it's only extracting a tiny fraction as entities and dumping")
print("the rest into a generic 'noise' section.")
print()

print("=" * 80)
