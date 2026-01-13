#!/usr/bin/env python3
"""
Merge edge-case emails into the temporal golden dataset.

This creates a comprehensive 60-email dataset:
- 50 real emails from GDS (seed=50)
- 10 synthetic edge cases for boundary testing
"""

from pathlib import Path

import pandas as pd


def main():
    # Load main dataset
    main_csv = Path(__file__).parent.parent / "reports" / "temporal_digest_review_50_emails.csv"
    edge_csv = Path(__file__).parent.parent / "reports" / "temporal_edge_cases_10_emails.csv"

    if not main_csv.exists():
        print(f"❌ Main dataset not found: {main_csv}")
        print("Run: python3 scripts/create_temporal_digest_review.py")
        return 1

    if not edge_csv.exists():
        print(f"❌ Edge cases not found: {edge_csv}")
        print("Run: python3 scripts/create_edge_case_emails.py")
        return 1

    main_df = pd.read_csv(main_csv)
    edge_df = pd.read_csv(edge_csv)

    print("=" * 80)
    print("MERGING EDGE CASES INTO TEMPORAL DATASET")
    print("=" * 80)
    print()
    print(f"Main dataset:  {len(main_df)} emails")
    print(f"Edge cases:    {len(edge_df)} emails")
    print()

    # Ensure columns match
    # Drop expected_* columns from edge cases (used for documentation only)
    edge_df = edge_df.drop(columns=[col for col in edge_df.columns if col.startswith("expected_")])

    # Merge
    combined_df = pd.concat([main_df, edge_df], ignore_index=True)

    # Save
    output_path = Path(__file__).parent.parent / "reports" / "temporal_digest_review_60_emails.csv"
    combined_df.to_csv(output_path, index=False)

    print(f"✅ Created combined dataset: {len(combined_df)} emails")
    print(f"📂 Location: {output_path}")
    print()

    print("NEXT STEPS:")
    print("-" * 80)
    print("1. Label all 60 emails using interactive tool:")
    print("   python3 scripts/interactive_temporal_review.py")
    print()
    print("2. The tool will automatically use the 60-email CSV")
    print("   (Update the CSV path in the script if needed)")
    print()
    print("3. Evaluate results:")
    print("   python3 scripts/evaluate_temporal_decay.py")
    print()

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
