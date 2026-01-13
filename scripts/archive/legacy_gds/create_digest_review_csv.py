# ruff: noqa
"""
Generate CSV with 100 sample emails for digest section review.
"""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).parent.parent))

from mailq.classification.importance_mapping.guardrails import GuardrailMatcher
from mailq.classification.importance_mapping.mapper import BridgeImportanceMapper
from mailq.classification.pipeline_wrapper import RefactoredPipelineClassifier

# Load GDS
gds_path = Path(__file__).parent.parent / "tests" / "golden_set" / "gds-1.0.csv"
gds = pd.read_csv(gds_path)

# Sample 100 random emails (same as digest test)
sample = gds.sample(n=min(100, len(gds)), random_state=42)

# Classify emails
base_classifier = RefactoredPipelineClassifier()
guardrails = GuardrailMatcher()
importance_mapper = BridgeImportanceMapper(guardrail_matcher=guardrails)

results = []

print("🔄 Classifying 100 emails...")

for _, email_row in sample.iterrows():
    # Backend classification
    base_classification = base_classifier.classify(
        subject=email_row["subject"],
        snippet=email_row["snippet"],
        from_field=email_row["from_email"],
    )

    # Apply importance mapping
    email_with_classification = {
        "subject": email_row["subject"],
        "snippet": email_row["snippet"],
        "from": email_row["from_email"],
        **base_classification,
    }

    decision = importance_mapper.map_email(email_with_classification)
    final_importance = decision.importance or "routine"

    results.append(
        {
            "subject": email_row["subject"],
            "from": email_row["from_email"],
            "snippet": email_row["snippet"][:150],  # First 150 chars
            "predicted_importance": final_importance,
            "predicted_type": base_classification.get("type", ""),
            "your_critical": "",  # User marks X if should be in CRITICAL
            "your_coming_up": "",  # User marks X if should be in COMING UP
            "your_worth_knowing": "",  # User marks X if should be in WORTH KNOWING
            "your_everything_else": "",  # User marks X if should be in EVERYTHING ELSE
            "your_skip": "",  # User marks X if should be skipped entirely
            "notes": "",  # User notes
        }
    )

# Save to CSV
output_df = pd.DataFrame(results)
output_path = Path(__file__).parent.parent / "reports" / "digest_review_100_emails.csv"
output_df.to_csv(output_path, index=False)

print(f"✅ Created review CSV with {len(output_df)} emails")
print(f"📂 Location: {output_path}")
print()
print("Instructions:")
print("1. Open the CSV in Excel/Numbers/Google Sheets or use interactive_digest_review.py")
print("2. For each email, mark which section it should be in:")
print("   - your_critical: Mark 'X' if should be in 🚨 CRITICAL")
print("   - your_coming_up: Mark 'X' if should be in 📅 COMING UP")
print("   - your_worth_knowing: Mark 'X' if should be in 💡 WORTH KNOWING")
print("   - your_everything_else: Mark 'X' if should be in 📬 EVERYTHING ELSE")
print("   - your_skip: Mark 'X' if should not appear in digest at all")
print("3. Add any notes in the 'notes' column")
print("4. Compare your markings to 'predicted_importance' to see agreement")
print()
print("Predicted importance distribution:")
print(output_df["predicted_importance"].value_counts())
