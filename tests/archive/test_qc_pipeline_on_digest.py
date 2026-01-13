"""
Test QC pipeline on generated digest.

This verifies that the quality control system can:
1. Analyze the digest HTML structure
2. Detect any format issues
3. Identify misclassifications
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "scripts" / "quality-monitor"))

from digest_format_analyzer import DigestFormatAnalyzer


def test_qc_pipeline_on_gds_digest():
    """Test QC pipeline on the digest we generated from GDS."""

    # Load the generated digest
    digest_path = Path(__file__).parent.parent / "reports" / "test_digest_gds_sample.html"

    if not digest_path.exists():
        print(f"❌ Digest not found at: {digest_path}")
        print("   Run test_digest_generation_gds.py first")
        return None

    digest_html = digest_path.read_text()

    print("\n" + "=" * 60)
    print("QC PIPELINE: DIGEST FORMAT ANALYSIS")
    print("=" * 60)
    print()

    # Analyze digest format
    analyzer = DigestFormatAnalyzer()
    analysis = analyzer.analyze_digest_html(digest_html)

    print("📊 SECTION STRUCTURE")
    print("-" * 60)
    sections = analysis.get("sections_found", {})
    for section_name, _found in analyzer.EXPECTED_SECTIONS.items():
        status = "✅" if sections.get(section_name, False) else "❌"
        print(f"{status} {section_name.replace('_', ' ')}")
    print()

    # Check structure type
    structure_type = analysis.get("structure_type", "unknown")
    print("📋 STRUCTURE TYPE")
    print("-" * 60)
    if structure_type == "categorized":
        print("✅ Using categorized sections (correct)")
    elif structure_type == "numbered":
        print("❌ Using numbered list (should use categories)")
    else:
        print(f"⚠️  Unknown structure type: {structure_type}")
    print()

    # Check for issues
    issues = analysis.get("issues", [])
    print("🔍 DETECTED ISSUES")
    print("-" * 60)
    if not issues:
        print("✅ No issues detected!")
    else:
        for i, issue in enumerate(issues, 1):
            severity = issue.get("severity", "medium")
            pattern = issue.get("pattern", "Unknown")
            evidence = issue.get("evidence", "")

            emoji = {"high": "🔴", "medium": "🟡", "low": "⚪"}.get(severity, "⚪")
            print(f"{emoji} Issue {i}: {pattern}")
            if evidence:
                print(f"   Evidence: {evidence}")
    print()

    # Email counts by section
    section_counts = analysis.get("section_counts", {})
    if section_counts:
        print("📧 EMAILS BY SECTION")
        print("-" * 60)
        total = sum(section_counts.values())
        for section, count in section_counts.items():
            pct = (count / total * 100) if total > 0 else 0
            print(f"   {section}: {count} ({pct:.1f}%)")
        print()

    # Noise detection
    noise_detected = analysis.get("noise_in_main_sections", False)
    print("🎯 NOISE FILTERING")
    print("-" * 60)
    if noise_detected:
        print("⚠️  Promotional/past event content detected in main sections")
        print("   (Should be in 'Everything else' section)")
    else:
        print("✅ No promotional/past event noise in main sections")
    print()

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)

    has_critical_issues = any(issue.get("severity") == "high" for issue in issues)
    has_medium_issues = any(issue.get("severity") == "medium" for issue in issues)

    if not issues:
        print("✅ DIGEST FORMAT: EXCELLENT")
        print("   No quality issues detected")
    elif has_critical_issues:
        print("❌ DIGEST FORMAT: NEEDS IMPROVEMENT")
        print(
            f"   Found {len([i for i in issues if i.get('severity') == 'high'])} high-severity issues"
        )
    elif has_medium_issues:
        print("⚠️  DIGEST FORMAT: ACCEPTABLE")
        print(
            f"   Found {len([i for i in issues if i.get('severity') == 'medium'])} medium-severity issues"
        )
    else:
        print("✅ DIGEST FORMAT: GOOD")
        print("   Only minor issues detected")

    print()
    return analysis


if __name__ == "__main__":
    test_qc_pipeline_on_gds_digest()
