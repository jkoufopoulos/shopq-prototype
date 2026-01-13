#!/usr/bin/env python3
"""
Digest Comparison Evaluation Script

Compares generated digests against golden reference digests for quality evaluation.

Usage:
    uv run python scripts/evals/digest_comparison.py --dataset dataset3
    uv run python scripts/evals/digest_comparison.py --all
    uv run python scripts/evals/digest_comparison.py --dataset dataset3 --save-output

Comparison Approach:
    Since digests contain dynamic content (weather, exact formatting), we compare
    structural elements:
    - Section presence (Today/Urgent, Coming Up, Worth Knowing)
    - Key items mentioned (calendar events, action items)
    - Email references (which emails are mentioned vs omitted)
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

# Add project root to path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


@dataclass
class DigestSection:
    """Represents a section in a digest."""

    name: str
    items: list[str]
    raw_html: str


@dataclass
class ParsedDigest:
    """Parsed representation of a digest for comparison."""

    greeting: str
    sections: list[DigestSection]
    summary: str
    raw_html: str


@dataclass
class ComparisonResult:
    """Result of comparing two digests."""

    dataset: str
    golden_sections: list[str]
    generated_sections: list[str]
    missing_sections: list[str]
    extra_sections: list[str]
    section_item_diffs: dict[str, dict]
    email_coverage: dict[str, Any]
    similarity_score: float
    notes: list[str]


def load_emails_from_csv(csv_path: Path) -> list[dict]:
    """Load emails from a dataset CSV."""
    emails = []
    with open(csv_path, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            emails.append(dict(row))
    return emails


# Path to the Golden Dataset (GDS)
GDS_PATH = Path("data/evals/classification/gds-2.0.csv")


def load_gds_as_dict() -> dict[str, dict]:
    """Load the GDS into a dict keyed by email_id for fast lookup.

    Returns:
        Dict mapping email_id (str) to email row dict.
    """
    gds = {}
    with open(GDS_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            gds[row["email_id"]] = dict(row)
    return gds


def load_emails_from_ids(ids_path: Path) -> list[dict]:
    """Load emails from GDS by ID reference file.

    Args:
        ids_path: Path to file containing comma-separated email IDs.

    Returns:
        List of email dicts from GDS matching the IDs.

    Raises:
        ValueError: If any email_id is not found in GDS.
    """
    # Load the ID list
    ids_text = ids_path.read_text().strip()
    email_ids = [eid.strip() for eid in ids_text.split(",") if eid.strip()]

    # Load GDS and lookup
    gds = load_gds_as_dict()
    emails = []
    missing = []

    for eid in email_ids:
        if eid in gds:
            emails.append(gds[eid])
        else:
            missing.append(eid)

    if missing:
        raise ValueError(f"Email IDs not found in GDS: {missing}")

    return emails


def extract_user_name_from_greeting(html: str) -> str | None:
    """Extract user name from the greeting in a digest.

    Looks for patterns like "Good morning, Justin" or "Good afternoon, Jane".
    Returns None if no name found.
    """
    greeting_match = re.search(r"Good (?:morning|afternoon|evening),\s+([A-Z][a-z]+)", html)
    if greeting_match:
        return greeting_match.group(1)
    return None


def extract_date_from_greeting(html: str) -> str | None:
    """Extract date from the greeting in a digest.

    Looks for patterns like "It's Sunday, November 9th" or "It's Friday, October 31st".
    Returns ISO format date string at 8am Eastern, or None if not found.
    """
    # Match: "It's [Day], [Month] [Day][suffix]"
    date_match = re.search(
        r"It's\s+\w+,\s+(\w+)\s+(\d{1,2})(?:st|nd|rd|th)",
        html,
    )
    if not date_match:
        return None

    month_name = date_match.group(1)
    day = int(date_match.group(2))

    # Parse month
    months = {
        "January": 1,
        "February": 2,
        "March": 3,
        "April": 4,
        "May": 5,
        "June": 6,
        "July": 7,
        "August": 8,
        "September": 9,
        "October": 10,
        "November": 11,
        "December": 12,
    }
    month = months.get(month_name)
    if not month:
        return None

    # Assume current/recent year (2025 for our test data)
    # In production, would infer from email dates
    year = 2025

    # Return as ISO format at 8am Eastern
    return f"{year}-{month:02d}-{day:02d}T08:00:00-05:00"


def parse_digest_html(html: str) -> ParsedDigest:
    """Parse a digest HTML into structured components."""
    # Extract greeting
    greeting_match = re.search(r'class="greeting"[^>]*>(.*?)</div>', html, re.DOTALL)
    greeting = greeting_match.group(1).strip() if greeting_match else ""

    # Extract sections
    sections = []
    section_pattern = (
        r'<div class="section">(.*?)</div>\s*(?=<div class="section">|<br>|<div class="footer">)'
    )

    for section_match in re.finditer(section_pattern, html, re.DOTALL):
        section_html = section_match.group(1)

        # Try to find section header
        header_patterns = [
            r"\*\*([^*]+)\*\*",  # **Section Name**
            r'class="section-header"[^>]*>([^<]+)',
        ]

        section_name = "unnamed"
        for pattern in header_patterns:
            header_match = re.search(pattern, section_html)
            if header_match:
                section_name = header_match.group(1).strip()
                break

        # Extract items (numbered or bulleted)
        items = []
        item_pattern = r'<span class="item-number">\((\d+)\)</span>\s*(.*?)</div>'
        for item_match in re.finditer(item_pattern, section_html, re.DOTALL):
            item_text = re.sub(r"<[^>]+>", "", item_match.group(2))
            items.append(item_text.strip())

        sections.append(DigestSection(name=section_name, items=items, raw_html=section_html))

    # Extract summary (usually after sections, before footer)
    summary = ""
    summary_match = re.search(
        r'<br>\s*<div class="section">(.*?)</div>\s*<div class="footer">', html, re.DOTALL
    )
    if summary_match:
        summary = re.sub(r"<[^>]+>", "", summary_match.group(1)).strip()

    return ParsedDigest(greeting=greeting, sections=sections, summary=summary, raw_html=html)


def extract_email_references(html: str, emails: list[dict]) -> dict[str, bool]:
    """Check which emails are referenced in the digest."""
    coverage = {}
    html_lower = html.lower()

    for email in emails:
        email_id = email.get("email_id", "")
        subject = email.get("subject", "").lower()

        # Check if email is likely referenced (fuzzy match on subject keywords)
        subject_words = [w for w in re.findall(r"\w+", subject) if len(w) > 3]
        is_referenced = any(word in html_lower for word in subject_words[:3])

        coverage[email_id] = is_referenced

    return coverage


def compare_digests(
    golden: ParsedDigest,
    generated: ParsedDigest,
    emails: list[dict],
    dataset: str,
) -> ComparisonResult:
    """Compare a generated digest against the golden reference."""
    golden_section_names = [s.name for s in golden.sections]
    generated_section_names = [s.name for s in generated.sections]

    missing_sections = [s for s in golden_section_names if s not in generated_section_names]
    extra_sections = [s for s in generated_section_names if s not in golden_section_names]

    # Compare items within matching sections
    section_diffs = {}
    for g_section in golden.sections:
        for gen_section in generated.sections:
            if g_section.name == gen_section.name:
                section_diffs[g_section.name] = {
                    "golden_items": len(g_section.items),
                    "generated_items": len(gen_section.items),
                    "diff": len(gen_section.items) - len(g_section.items),
                }

    # Check email coverage
    golden_coverage = extract_email_references(golden.raw_html, emails)
    generated_coverage = extract_email_references(generated.raw_html, emails)

    golden_referenced = sum(1 for v in golden_coverage.values() if v)
    generated_referenced = sum(1 for v in generated_coverage.values() if v)

    email_coverage = {
        "total_emails": len(emails),
        "golden_references": golden_referenced,
        "generated_references": generated_referenced,
        "coverage_diff": generated_referenced - golden_referenced,
    }

    # Calculate similarity score
    section_match_score = 1.0 - (len(missing_sections) + len(extra_sections)) / max(
        len(golden_section_names), 1
    )
    coverage_score = (
        min(generated_referenced, golden_referenced) / max(golden_referenced, 1)
        if golden_referenced
        else 1.0
    )
    similarity_score = (section_match_score + coverage_score) / 2

    notes = []
    if missing_sections:
        notes.append(f"Missing sections: {missing_sections}")
    if extra_sections:
        notes.append(f"Extra sections: {extra_sections}")

    return ComparisonResult(
        dataset=dataset,
        golden_sections=golden_section_names,
        generated_sections=generated_section_names,
        missing_sections=missing_sections,
        extra_sections=extra_sections,
        section_item_diffs=section_diffs,
        email_coverage=email_coverage,
        similarity_score=similarity_score,
        notes=notes,
    )


def infer_evaluation_date(emails: list[dict]) -> str | None:
    """
    Infer the evaluation date from email received dates.

    For digest evaluation, we want to generate the digest as if it were
    the day after the latest email - simulating "morning digest" for that period.

    Returns ISO format string or None if can't be inferred.
    """
    from datetime import timedelta
    from email.utils import parsedate_to_datetime

    latest_date = None
    for email in emails:
        received = email.get("received_date", "")
        if not received:
            continue
        try:
            # Parse RFC 2822 date format: "Thu, 06 Nov 2025 00:07:06 -0800"
            dt = parsedate_to_datetime(received)
            if latest_date is None or dt > latest_date:
                latest_date = dt
        except (ValueError, TypeError):
            continue

    if latest_date:
        # Set to 8am the next day (typical morning digest time)
        eval_date = latest_date.replace(hour=8, minute=0, second=0, microsecond=0)
        eval_date = eval_date + timedelta(days=1)
        return eval_date.isoformat()
    return None


def generate_digest_for_emails(
    emails: list[dict],
    eval_date: str | None = None,
    user_name: str | None = None,
) -> str:
    """Generate a digest from emails using the digest pipeline.

    Args:
        emails: List of email dicts from CSV
        eval_date: ISO timestamp to use as "now" for evaluation (optional)
        user_name: User's first name for personalized greeting (optional)
    """
    try:
        from shopq.digest.context_digest import ContextDigest

        # Convert CSV format to expected email format
        formatted_emails = []
        for email in emails:
            formatted_emails.append(
                {
                    "id": email.get("email_id", ""),
                    "from": email.get("from_email", ""),
                    "subject": email.get("subject", ""),
                    "snippet": email.get("snippet", ""),
                    "receivedAt": email.get("received_date", ""),
                    "date": email.get("received_date", ""),  # Duplicate for compatibility
                    "type": email.get("email_type", ""),
                    "importance": email.get("importance", ""),
                    "temporal_start": email.get(
                        "temporal_start", ""
                    ),  # For expired event filtering
                    "temporal_end": email.get("temporal_end", ""),
                    "client_label": email.get("client_label", ""),  # For footer label counts
                }
            )

        digest = ContextDigest()
        result = digest.generate(
            formatted_emails,
            client_now=eval_date,
            timezone="America/New_York",
            user_name=user_name,
        )
        # generate() returns dict with 'html' key
        if isinstance(result, dict):
            return result.get("html", str(result))
        return result
    except Exception as e:
        return f"<html><body>Error generating digest: {e}</body></html>"


def run_evaluation(dataset: str, save_output: bool = False) -> ComparisonResult | None:
    """Run evaluation for a single dataset."""
    dataset_dir = Path(f"data/evals/digests/{dataset}")

    if not dataset_dir.exists():
        print(f"Dataset not found: {dataset_dir}")
        return None

    # Check for email sources: prefer email_ids.txt (GDS lookup), fallback to emails.csv
    ids_path = dataset_dir / "email_ids.txt"
    emails_path = dataset_dir / "emails.csv"
    golden_path = dataset_dir / "golden.html"

    if not ids_path.exists() and not emails_path.exists():
        print(f"No email source found: need {ids_path} or {emails_path}")
        return None

    if not golden_path.exists():
        print(f"Golden digest not found: {golden_path}")
        print("  (You can still generate a digest, but comparison will be skipped)")
        return None

    # Load data - prefer GDS lookup via email_ids.txt
    print(f"Loading {dataset}...")
    if ids_path.exists():
        print(f"  Using GDS lookup via {ids_path.name}")
        emails = load_emails_from_ids(ids_path)
    else:
        print(f"  Using local {emails_path.name} (legacy mode)")
        emails = load_emails_from_csv(emails_path)
    golden_html = golden_path.read_text()

    print(f"  Loaded {len(emails)} emails")

    # Parse golden digest
    golden_parsed = parse_digest_html(golden_html)
    print(f"  Golden digest: {len(golden_parsed.sections)} sections")

    # Extract evaluation date from golden digest (preferred) or infer from emails
    eval_date = extract_date_from_greeting(golden_html)
    if eval_date:
        print(f"  Evaluation date (from golden): {eval_date}")
    else:
        eval_date = infer_evaluation_date(emails)
        if eval_date:
            print(f"  Evaluation date (inferred): {eval_date}")
        else:
            print("  Warning: Could not determine evaluation date, using current time")

    # Extract user name from golden digest for personalization
    user_name = extract_user_name_from_greeting(golden_html)
    if user_name:
        print(f"  User name: {user_name}")

    # Generate digest
    print("  Generating digest...")
    generated_html = generate_digest_for_emails(emails, eval_date=eval_date, user_name=user_name)
    generated_parsed = parse_digest_html(generated_html)
    print(f"  Generated digest: {len(generated_parsed.sections)} sections")

    # Save generated output if requested
    if save_output:
        output_path = dataset_dir / "generated.html"
        output_path.write_text(generated_html)
        print(f"  Saved generated digest to: {output_path}")

    # Compare
    return compare_digests(golden_parsed, generated_parsed, emails, dataset)


def print_result(result: ComparisonResult):
    """Print comparison result."""
    print(f"\n{'=' * 60}")
    print(f"DIGEST COMPARISON: {result.dataset}")
    print(f"{'=' * 60}")

    print(f"\nSimilarity Score: {result.similarity_score:.1%}")

    print("\nSections:")
    print(f"  Golden:    {result.golden_sections}")
    print(f"  Generated: {result.generated_sections}")

    if result.missing_sections:
        print(f"  MISSING:   {result.missing_sections}")
    if result.extra_sections:
        print(f"  EXTRA:     {result.extra_sections}")

    print("\nSection Item Counts:")
    for section, diff in result.section_item_diffs.items():
        status = (
            "OK"
            if diff["diff"] == 0
            else f"+{diff['diff']}"
            if diff["diff"] > 0
            else str(diff["diff"])
        )
        g_items = diff["golden_items"]
        gen_items = diff["generated_items"]
        print(f"  {section}: golden={g_items}, generated={gen_items} [{status}]")

    print("\nEmail Coverage:")
    cov = result.email_coverage
    print(f"  Total emails: {cov['total_emails']}")
    print(f"  Golden references: {cov['golden_references']}")
    print(f"  Generated references: {cov['generated_references']}")

    if result.notes:
        print("\nNotes:")
        for note in result.notes:
            print(f"  - {note}")


def main():
    parser = argparse.ArgumentParser(description="Compare generated digests to golden references")
    parser.add_argument("--dataset", type=str, help="Dataset to evaluate (e.g., dataset3)")
    parser.add_argument(
        "--all", action="store_true", help="Evaluate all datasets with golden digests"
    )
    parser.add_argument("--save-output", action="store_true", help="Save generated digest HTML")
    parser.add_argument("--list", action="store_true", help="List available datasets")
    args = parser.parse_args()

    digests_dir = Path("data/evals/digests")

    if args.list:
        print("Available datasets:")
        for d in sorted(digests_dir.iterdir()):
            if d.is_dir():
                has_golden = (d / "golden.html").exists()
                has_ids = (d / "email_ids.txt").exists()
                has_emails = (d / "emails.csv").exists()
                status = []
                if has_ids:
                    status.append("ids (GDS)")
                elif has_emails:
                    status.append("emails (legacy)")
                if has_golden:
                    status.append("golden")
                print(f"  {d.name}: [{', '.join(status) or 'empty'}]")
        return

    if args.all:
        datasets = [
            d.name for d in digests_dir.iterdir() if d.is_dir() and (d / "golden.html").exists()
        ]
    elif args.dataset:
        datasets = [args.dataset]
    else:
        print("Please specify --dataset <name>, --all, or --list")
        return

    results = []
    for dataset in datasets:
        result = run_evaluation(dataset, args.save_output)
        if result:
            results.append(result)
            print_result(result)

    if len(results) > 1:
        print(f"\n{'=' * 60}")
        print("SUMMARY")
        print(f"{'=' * 60}")
        avg_score = sum(r.similarity_score for r in results) / len(results)
        print(f"Datasets evaluated: {len(results)}")
        print(f"Average similarity: {avg_score:.1%}")


if __name__ == "__main__":
    main()
