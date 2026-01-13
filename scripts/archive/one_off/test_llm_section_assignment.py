"""
Test LLM-based section assignment against Dataset 2.

This script evaluates the hybrid section assignment (rules + LLM) against
the ground truth T1 annotations.

Usage:
    # Test with LLM fallback enabled
    SHOPQ_LLM_SECTION_FALLBACK=true python scripts/test_llm_section_assignment.py

    # Test rules-only (baseline)
    SHOPQ_LLM_SECTION_FALLBACK=false python scripts/test_llm_section_assignment.py
"""

import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Enable LLM fallback for testing
os.environ["SHOPQ_LLM_SECTION_FALLBACK"] = "true"

from scripts.evaluate_dataset2_ground_truth import (
    calculate_metrics,
    load_dataset2,
    print_report,
    run_pipeline_on_dataset2,
)


def main():
    """Run evaluation with LLM-based section assignment"""

    # Check if LLM fallback is enabled
    llm_enabled = os.getenv("SHOPQ_LLM_SECTION_FALLBACK", "false").lower() == "true"

    print(f"\n{'=' * 80}")
    print("Testing Section Assignment")
    print(f"{'=' * 80}")
    print(f"LLM Fallback: {'ENABLED' if llm_enabled else 'DISABLED (rules only)'}")
    print(f"{'=' * 80}\n")

    # Load dataset
    csv_path = "reports/dataset2_nov2-9_70_emails.csv"
    print(f"Loading Dataset 2 from {csv_path}...")
    emails = load_dataset2(csv_path)
    print(f"Loaded {len(emails)} emails\n")

    # Run pipeline
    print("Running V2 pipeline with LLM-based section assignment...")
    pipeline_result = run_pipeline_on_dataset2(emails)

    # Get T1 sections
    section_assignments_t1 = pipeline_result["section_assignments"]

    print(f"Pipeline complete. {len(section_assignments_t1)} emails classified.\n")

    # Calculate metrics
    print("Calculating metrics...")
    metrics = calculate_metrics(emails, section_assignments_t1, "t1")

    # Print report
    print_report(metrics, "t1")

    # Save results
    output_suffix = "llm" if llm_enabled else "rules_only"
    output_path = f"reports/dataset2_evaluation_t1_{output_suffix}.txt"

    print(f"\n💾 Saving results to {output_path}...")
    with open(output_path, "w") as f:
        import io
        from contextlib import redirect_stdout

        f_stdout = io.StringIO()
        with redirect_stdout(f_stdout):
            print_report(metrics, "t1")

        f.write(f_stdout.getvalue())

    print("✅ Results saved!")

    # Print comparison with baseline
    if llm_enabled:
        baseline_accuracy = 60.0  # From previous evaluation
        new_accuracy = metrics["overall"]["accuracy"] * 100
        improvement = new_accuracy - baseline_accuracy

        print(f"\n{'=' * 80}")
        print("COMPARISON WITH BASELINE")
        print(f"{'=' * 80}")
        print(f"Baseline (rules only): {baseline_accuracy:.1f}%")
        print(f"With LLM fallback:     {new_accuracy:.1f}%")
        print(f"Improvement:           {improvement:+.1f}pp")
        print(f"{'=' * 80}\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
