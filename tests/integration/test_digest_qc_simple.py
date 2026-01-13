"""
Simple QC check on generated digest.

Validates:
1. Section structure (CRITICAL, COMING UP, WORTH KNOWING)
2. No OTP codes in CRITICAL
3. HTML validity
4. Content quality
"""

from pathlib import Path


def test_digest_qc():
    """Run simple QC checks on generated digest."""

    # Load digest
    digest_path = Path(__file__).parent.parent / "reports" / "test_digest_gds_sample.html"

    if not digest_path.exists():
        print(f"❌ Digest not found at: {digest_path}")
        return

    digest_html = digest_path.read_text()

    print("\n" + "=" * 60)
    print("DIGEST QUALITY CONTROL CHECK")
    print("=" * 60)
    print()

    issues = []

    # Check 1: Required sections
    print("📋 SECTION STRUCTURE")
    print("-" * 60)

    required_sections = {
        "CRITICAL": ["🚨 CRITICAL", "CRITICAL"],
        "COMING UP": ["📅 COMING UP", "COMING UP"],
        "WORTH KNOWING": ["💡 WORTH KNOWING", "WORTH KNOWING", "💼 WORTH KNOWING"],
    }

    for section_name, keywords in required_sections.items():
        found = any(kw in digest_html for kw in keywords)
        status = "✅" if found else "❌"
        print(f"{status} {section_name} section")
        if not found:
            issues.append({"severity": "high", "issue": f"Missing {section_name} section"})

    print()

    # Check 2: OTP codes in CRITICAL
    print("🔐 OTP FILTERING")
    print("-" * 60)

    critical_start = digest_html.find("CRITICAL")
    if critical_start != -1:
        critical_end = digest_html.find("COMING UP", critical_start)
        if critical_end == -1:
            critical_end = digest_html.find("WORTH KNOWING", critical_start)
        if critical_end == -1:
            critical_end = len(digest_html)

        critical_section = digest_html[critical_start:critical_end].lower()

        otp_keywords = ["verification code", "otp", "2fa", "one-time", "login code", "passcode"]
        otp_in_critical = any(kw in critical_section for kw in otp_keywords)

        if otp_in_critical:
            print("❌ OTP codes found in CRITICAL section")
            issues.append({"severity": "high", "issue": "OTP codes in CRITICAL section"})
        else:
            print("✅ No OTP codes in CRITICAL section")
    else:
        print("⚠️  CRITICAL section not found")

    print()

    # Check 3: HTML validity
    print("🌐 HTML STRUCTURE")
    print("-" * 60)

    has_html_tag = "<html" in digest_html.lower()
    has_body_tag = "<body" in digest_html.lower()
    has_doctype = "<!doctype" in digest_html.lower()
    has_closing_tags = "</html>" in digest_html.lower() and "</body>" in digest_html.lower()

    print(f"{'✅' if has_doctype else '❌'} DOCTYPE declaration")
    print(f"{'✅' if has_html_tag else '❌'} HTML tag")
    print(f"{'✅' if has_body_tag else '❌'} Body tag")
    print(f"{'✅' if has_closing_tags else '❌'} Closing tags")

    if not (has_html_tag and has_body_tag and has_closing_tags):
        issues.append({"severity": "medium", "issue": "Incomplete HTML structure"})

    print()

    # Check 4: Content quality
    print("📊 CONTENT QUALITY")
    print("-" * 60)

    # Check for reasonable number of email items
    email_item_count = digest_html.count("<li")
    print(f"   Email items: {email_item_count}")

    if email_item_count < 5:
        print("⚠️  Very few items in digest")
        issues.append({"severity": "low", "issue": f"Only {email_item_count} items in digest"})
    else:
        print("✅ Reasonable number of items")

    # Check for numbered list (should use categories instead)
    has_numbered_list = bool(
        digest_html.count("<li>1.") > 0
        or digest_html.count("<li>2.") > 0
        or digest_html.count("1)") > 0
    )

    if has_numbered_list:
        print("❌ Using numbered list (should use category sections)")
        issues.append({"severity": "medium", "issue": "Using numbered list instead of categories"})
    else:
        print("✅ Using category sections (not numbered list)")

    print()

    # Check 5: Digest size
    digest_size_kb = len(digest_html) / 1024
    print(f"   Digest size: {digest_size_kb:.1f} KB")

    if digest_size_kb > 100:
        print("⚠️  Digest is large (may have rendering issues)")
        issues.append({"severity": "low", "issue": f"Large digest size: {digest_size_kb:.1f} KB"})
    else:
        print("✅ Reasonable size")

    print()

    # Summary
    print("=" * 60)
    print("SUMMARY")
    print("=" * 60)

    high_issues = [i for i in issues if i["severity"] == "high"]
    medium_issues = [i for i in issues if i["severity"] == "medium"]
    low_issues = [i for i in issues if i["severity"] == "low"]

    print(f"\n🔴 High severity: {len(high_issues)}")
    for issue in high_issues:
        print(f"   - {issue['issue']}")

    print(f"\n🟡 Medium severity: {len(medium_issues)}")
    for issue in medium_issues:
        print(f"   - {issue['issue']}")

    print(f"\n⚪ Low severity: {len(low_issues)}")
    for issue in low_issues:
        print(f"   - {issue['issue']}")

    print()

    if not issues:
        print("✅ DIGEST QUALITY: EXCELLENT")
        print("   No issues detected!")
    elif high_issues:
        print("❌ DIGEST QUALITY: NEEDS IMPROVEMENT")
        print(f"   Found {len(high_issues)} critical issues")
    elif medium_issues:
        print("⚠️  DIGEST QUALITY: ACCEPTABLE")
        print(f"   Found {len(medium_issues)} moderate issues")
    else:
        print("✅ DIGEST QUALITY: GOOD")
        print("   Only minor issues")

    print()


if __name__ == "__main__":
    test_digest_qc()
