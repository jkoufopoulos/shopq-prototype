#!/usr/bin/env python3
"""
Generate Digest Comparison - Create fresh ACTUAL vs SUGGESTED IDEAL comparison

This script:
1. Finds the latest input_emails_*.json and actual_digest_*.html files
2. Runs importance classifier on inputs to suggest what SHOULD be featured
3. Extracts what WAS actually featured from the digest
4. Creates a fresh comparison_TIMESTAMP.md file in quality_logs/
5. You can then edit the SUGGESTED IDEAL if the automation got it wrong

This creates a NEW comparison file for each digest session (not accumulating).
"""

from __future__ import annotations

import json

# Import importance classifier
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from mailq.classification.importance_classifier import ImportanceClassifier


def find_latest_files():
    """Find the most recent input_emails_*.json and corresponding digest file"""
    quality_logs_dir = Path("quality_logs")
    if not quality_logs_dir.exists():
        print("❌ quality_logs/ directory not found")
        return None, None, None

    # Find all input_emails_*.json files
    email_files = sorted(quality_logs_dir.glob("input_emails_*.json"), reverse=True)

    if not email_files:
        print("❌ No input_emails_*.json files found in quality_logs/")
        return None, None, None

    latest_email_file = email_files[0]

    # Extract timestamp
    timestamp = latest_email_file.stem.replace("input_emails_", "")

    # Find corresponding digest HTML
    digest_file = quality_logs_dir / f"actual_digest_{timestamp}.html"

    if not digest_file.exists():
        print(f"⚠️  Found {latest_email_file.name} but no matching digest HTML")
        return latest_email_file, None, timestamp

    return latest_email_file, digest_file, timestamp


def suggest_ideal_from_inputs(emails_data):
    """Use importance classifier to suggest what SHOULD be featured"""
    classifier = ImportanceClassifier()

    suggested = {"critical": [], "today": [], "coming_up": [], "worth_knowing": []}

    for email in emails_data["emails"]:
        subject = email.get("subject", "")
        snippet = email.get("snippet", "")
        text = f"{subject} {snippet}"

        email_type = email.get("type", "notification")
        attention = email.get("attention", "none")

        # Classify importance
        importance = classifier.classify(text, email_type=email_type, attention=attention)

        # Create email summary
        email_summary = {
            "subject": subject,
            "from": email.get("from", "Unknown"),
            "importance": importance,
            "type": email_type,
            "attention": attention,
        }

        # Categorize based on importance
        if importance == "critical":
            suggested["critical"].append(email_summary)
        elif importance == "time_sensitive":
            # Further categorize time-sensitive
            # Deliveries/arrivals today go to TODAY
            if any(
                kw in text.lower()
                for kw in ["delivered:", "arriving today", "deadline today", "expires today"]
            ):
                suggested["today"].append(email_summary)
            # Events, appointments go to COMING UP
            elif email_type in ["event"] or any(
                kw in text.lower() for kw in ["appointment", "meeting", "scheduled"]
            ):
                suggested["coming_up"].append(email_summary)
            # Jobs, shipments, financial updates go to WORTH KNOWING
            elif any(
                kw in text.lower() for kw in ["job", "shipped:", "hiring", "balance", "statement"]
            ):
                suggested["worth_knowing"].append(email_summary)
            else:
                # Default time-sensitive goes to COMING UP
                suggested["coming_up"].append(email_summary)
        # Routine emails are not featured

    return suggested


def extract_actual_digest_content(html_file):
    """Extract what was actually featured from digest HTML"""
    with open(html_file, encoding="utf-8") as f:
        content = f.read()

    # Extract metadata
    metadata = {}
    for line in content.split("\n")[:10]:
        if "Featured:" in line:
            metadata["featured"] = int(line.split("Featured:")[1].split("-->")[0].strip())
        elif "Critical:" in line:
            metadata["critical"] = int(line.split("Critical:")[1].split("-->")[0].strip())

    # For now, just return metadata - actual content parsing can be added later
    return metadata


def generate_comparison_file(timestamp, actual_metadata, suggested_ideal, emails_data):
    """Generate comparison markdown file"""
    quality_logs_dir = Path("quality_logs")
    comparison_file = quality_logs_dir / f"comparison_{timestamp}.md"

    # Calculate counts
    suggested_critical = len(suggested_ideal["critical"])
    suggested_today = len(suggested_ideal["today"])
    suggested_coming_up = len(suggested_ideal["coming_up"])
    suggested_worth_knowing = len(suggested_ideal["worth_knowing"])
    suggested_total = (
        suggested_critical + suggested_today + suggested_coming_up + suggested_worth_knowing
    )

    actual_featured = actual_metadata.get("featured", 0)
    actual_critical = actual_metadata.get("critical", 0)

    # Calculate gap
    gap = suggested_total - actual_featured
    recall_pct = (actual_featured / suggested_total * 100) if suggested_total > 0 else 0

    # Generate markdown content
    content = f"""# Digest Comparison - {timestamp}

**Generated**: {datetime.now().strftime("%Y-%m-%d %H:%M")}
**Input emails**: {emails_data["email_count"]}
**Actual featured**: {actual_featured} items
**Suggested ideal**: {suggested_total} items should be featured
**Gap**: {gap} items missing ({100 - recall_pct:.1f}% recall failure)

---

## Side-by-Side Comparison

### ACTUAL DIGEST (What system produced)

**Featured items**: {actual_featured}
**Critical items**: {actual_critical}

*To view full HTML*: `open quality_logs/actual_digest_{timestamp}.html`

**Note**: The script `generate_digest_comparison.py` currently only extracts metadata.
To see the full list of what was featured, open the HTML file above.

---

### SUGGESTED IDEAL (What classifier thinks should be featured)

**⚠️  REVIEW AND EDIT THIS SECTION**

The suggestions below are based on running importance_classifier.py on the input emails.
The classifier may be wrong! Review and edit this section based on your manual review of the inputs.

```
🚨 CRITICAL ({suggested_critical} emails):
"""

    # Add critical items
    for email in suggested_ideal["critical"]:
        content += f"  • {email['subject']}\n"
        content += f"    From: {email['from']}\n"

    content += f"""
📦 TODAY ({suggested_today} emails):
"""

    # Add today items
    for email in suggested_ideal["today"]:
        content += f"  • {email['subject']}\n"

    content += f"""
📅 COMING UP ({suggested_coming_up} emails):
"""

    # Add coming up items
    for email in suggested_ideal["coming_up"]:
        content += f"  • {email['subject']}\n"

    content += f"""
💼 WORTH KNOWING ({suggested_worth_knowing} emails):
"""

    # Add worth knowing items
    for email in suggested_ideal["worth_knowing"]:
        content += f"  • {email['subject']}\n"

    recall_status = "✅ PASS" if recall_pct >= 70 else "❌ FAIL"

    content += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Everything else ({emails_data["email_count"] - suggested_total} emails):
  • Routine notifications and noise
```

---

## Performance Metrics (Based on Suggested Ideal)

| Metric | Value | Target | Status |
|--------|-------|--------|--------|
| **Recall** | {recall_pct:.1f}% ({actual_featured}/{suggested_total}) | ≥70% | {recall_status} |

### Breakdown by Category

| Category | Suggested | Actually Featured | Gap |
|----------|-----------|-------------------|-----|
| Critical | {suggested_critical} | {actual_critical} | {suggested_critical - actual_critical} |
| Today | {suggested_today} | ? | ? |
| Coming Up | {suggested_coming_up} | ? | ? |
| Worth Knowing | {suggested_worth_knowing} | ? | ? |
| **TOTAL** | **{suggested_total}** | **{actual_featured}** | **{gap}** |

---

## Next Steps

1. **Review SUGGESTED IDEAL section above**
   - Check if classifier suggestions are correct
   - Edit items that shouldn't be featured
   - Add items that should be featured but classifier missed

2. **Compare ACTUAL vs your edited IDEAL**
   - What critical items were missed?
   - What deliveries/events weren't featured?
   - What noise was incorrectly featured?

3. **Identify root causes**
   - Missing patterns in importance_classifier.py?
   - Wrong patterns triggering time_sensitive?
   - Filters not catching past events?

4. **Fix and re-test**
   - Update patterns
   - Generate new digest
   - Run this script again
   - Compare improvements

---

## Input Data

**Input emails file**: `quality_logs/input_emails_{timestamp}.json`
**Actual digest file**: `quality_logs/actual_digest_{timestamp}.html`

To review inputs in detail:
```bash
python review_digest_quality.py
```
"""

    # Write file
    with open(comparison_file, "w", encoding="utf-8") as f:
        f.write(content)

    return comparison_file


def main():
    print("📊 Generating Digest Comparison with Suggested Ideal\n")

    # Find latest files
    email_file, digest_file, timestamp = find_latest_files()

    if not email_file:
        return 1

    print("✅ Found files:")
    print(f"   Input:  input_emails_{timestamp}.json")
    if digest_file:
        print(f"   Output: actual_digest_{timestamp}.html")
    else:
        print("   Output: NOT FOUND")
        return 1

    # Load input emails
    print("\n📧 Loading input emails...")
    with open(email_file, encoding="utf-8") as f:
        emails_data = json.load(f)

    print(f"   Loaded {emails_data['email_count']} emails")

    # Suggest ideal using importance classifier
    print("\n🤖 Running importance classifier to suggest ideal...")
    suggested_ideal = suggest_ideal_from_inputs(emails_data)

    suggested_total = (
        len(suggested_ideal["critical"])
        + len(suggested_ideal["today"])
        + len(suggested_ideal["coming_up"])
        + len(suggested_ideal["worth_knowing"])
    )

    print(f"   Suggested ideal: {suggested_total} items")
    print(f"   - Critical: {len(suggested_ideal['critical'])}")
    print(f"   - Today: {len(suggested_ideal['today'])}")
    print(f"   - Coming up: {len(suggested_ideal['coming_up'])}")
    print(f"   - Worth knowing: {len(suggested_ideal['worth_knowing'])}")

    # Extract actual digest content
    print("\n📄 Extracting actual digest content...")
    actual_metadata = extract_actual_digest_content(digest_file)

    print(f"   Actual featured: {actual_metadata.get('featured', 0)} items")
    print(f"   Actual critical: {actual_metadata.get('critical', 0)} items")

    # Generate comparison file
    print("\n✏️  Generating comparison file...")
    comparison_file = generate_comparison_file(
        timestamp, actual_metadata, suggested_ideal, emails_data
    )

    print(f"\n🎉 Comparison file created: {comparison_file}")
    print("\n📋 Next steps:")
    print(f"   1. Open: {comparison_file}")
    print("   2. Review and edit the SUGGESTED IDEAL section")
    print("   3. Compare ACTUAL vs your edited IDEAL")
    print("   4. Identify gaps and fix classification issues")
    print("   5. Re-run this script after generating a new digest")

    return 0


if __name__ == "__main__":
    exit(main())
