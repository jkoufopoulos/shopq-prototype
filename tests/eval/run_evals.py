#!/usr/bin/env python3
"""
Eval runner for the Reclaim extraction pipeline.

Loads synthetic email cases, sends them through the live API, runs code evals
and expectation evals on each result, and generates a JSON report.

Usage:
    # Run against local server (default)
    python tests/eval/run_evals.py

    # Filter by tag
    python tests/eval/run_evals.py --tag amazon

    # Include LLM judges
    python tests/eval/run_evals.py --judges

    # Target production
    python tests/eval/run_evals.py --url https://reclaim-api-488078904670.us-central1.run.app

    # With auth token (required for production)
    python tests/eval/run_evals.py --url https://... --token <google-oauth-token>

    # Send emails one at a time (default is batch)
    python tests/eval/run_evals.py --single

    # Dry run — just show which cases would run
    python tests/eval/run_evals.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Support running as both `python tests/eval/run_evals.py` and `python -m tests.eval.run_evals`
try:
    from tests.eval.code_evals import run_code_evals
    from tests.eval.expectation_evals import run_expectation_evals
except ModuleNotFoundError:
    # When run directly as a script, add project root to path
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from tests.eval.code_evals import run_code_evals
    from tests.eval.expectation_evals import run_expectation_evals

FIXTURES_DIR = Path(__file__).parent / "fixtures"
REPORTS_DIR = Path(__file__).parent / "reports"
DEFAULT_URL = "http://localhost:8000"


def load_cases(tag: str | None = None) -> list[dict]:
    """Load synthetic email cases, optionally filtered by tag."""
    cases_file = FIXTURES_DIR / "synthetic-emails.json"
    if not cases_file.exists():
        print(f"ERROR: {cases_file} not found. Run: python tests/eval/gen_synthetic.py")
        sys.exit(1)

    cases = json.loads(cases_file.read_text())

    if tag:
        cases = [c for c in cases if tag in c.get("tags", [])]
        if not cases:
            print(f"WARNING: No cases match tag '{tag}'")

    return cases


def send_single(client: "httpx.Client", url: str, case: dict) -> dict:
    """Send a single email through the extraction API."""
    payload = {
        "emails": [{
            "email_id": case["id"],
            "from_address": case["from_address"],
            "subject": case["subject"],
            "body": case["body"],
            "body_html": case.get("body_html"),
        }],
    }

    resp = client.post(f"{url}/api/extract", json=payload, timeout=30.0)

    if resp.status_code != 200:
        return {
            "success": False,
            "rejection_reason": f"http_error:{resp.status_code}",
            "stage_reached": "error",
            "_http_status": resp.status_code,
            "_http_body": resp.text[:500],
        }

    data = resp.json()
    results = data.get("results", [])

    if not results:
        return {
            "success": False,
            "rejection_reason": "empty_response",
            "stage_reached": "error",
        }

    return results[0]


def send_batch(client: "httpx.Client", url: str, cases: list[dict]) -> dict[str, dict]:
    """Send all emails as a single batch and return results keyed by case ID."""
    payload = {
        "emails": [{
            "email_id": case["id"],
            "from_address": case["from_address"],
            "subject": case["subject"],
            "body": case["body"],
            "body_html": case.get("body_html"),
        } for case in cases],
    }

    resp = client.post(f"{url}/api/extract", json=payload, timeout=120.0)

    if resp.status_code != 200:
        error_result = {
            "success": False,
            "rejection_reason": f"http_error:{resp.status_code}",
            "stage_reached": "error",
            "_http_status": resp.status_code,
            "_http_body": resp.text[:500],
        }
        return {case["id"]: error_result for case in cases}

    data = resp.json()
    results = data.get("results", [])

    # Map results by email_id
    results_by_id = {}
    for r in results:
        eid = r.get("email_id", "")
        results_by_id[eid] = r

    # For cases not in results (e.g., deduplication removed them), create empty results
    out = {}
    for case in cases:
        if case["id"] in results_by_id:
            out[case["id"]] = results_by_id[case["id"]]
        else:
            out[case["id"]] = {
                "success": False,
                "rejection_reason": "not_in_response",
                "stage_reached": "unknown",
            }

    return out


def run_judges(result: dict, case: dict) -> list[dict]:
    """Run LLM judge evals if available."""
    try:
        from tests.eval.judge_evals import run_judge_evals
    except ModuleNotFoundError:
        from judge_evals import run_judge_evals  # type: ignore[no-redef]
    try:
        return run_judge_evals(result, case)
    except ImportError:
        return []
    except Exception as e:
        return [{"name": "judge_error", "pass": False, "detail": str(e)}]


def evaluate_case(result: dict, case: dict, *, include_judges: bool = False) -> dict:
    """Run all evals on a single case result."""
    code_results = run_code_evals(result)
    expectation_results = run_expectation_evals(result, case)
    judge_results = run_judges(result, case) if include_judges else []

    all_evals = code_results + expectation_results + judge_results
    passed = all(e["pass"] for e in all_evals)
    failures = [e for e in all_evals if not e["pass"]]

    return {
        "case_id": case["id"],
        "tags": case.get("tags", []),
        "passed": passed,
        "eval_count": len(all_evals),
        "failure_count": len(failures),
        "failures": failures,
        "evals": all_evals,
        "result_summary": {
            "success": result.get("success"),
            "stage_reached": result.get("stage_reached"),
            "rejection_reason": result.get("rejection_reason"),
            "merchant": (result.get("card") or {}).get("merchant"),
        },
    }


def generate_report(
    case_results: list[dict],
    base_url: str,
    elapsed_s: float,
) -> dict:
    """Generate a summary report from all case evaluations."""
    total = len(case_results)
    passed = sum(1 for c in case_results if c["passed"])
    failed = sum(1 for c in case_results if not c["passed"])
    errors = sum(1 for c in case_results
                  if c["result_summary"].get("stage_reached") == "error")

    # Failure breakdown by eval name
    failure_breakdown: dict[str, int] = {}
    for cr in case_results:
        for f in cr["failures"]:
            name = f["name"]
            failure_breakdown[name] = failure_breakdown.get(name, 0) + 1

    # Sort by count descending
    failure_breakdown = dict(
        sorted(failure_breakdown.items(), key=lambda x: -x[1])
    )

    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "base_url": base_url,
        "elapsed_seconds": round(elapsed_s, 1),
        "total": total,
        "passed": passed,
        "failed": failed,
        "errors": errors,
        "pass_rate": f"{(passed / total * 100):.1f}%" if total > 0 else "N/A",
        "failure_breakdown": failure_breakdown,
        "cases": case_results,
    }


def print_summary(report: dict) -> None:
    """Print a human-readable summary to stdout."""
    print("\n" + "=" * 60)
    print(f"  Eval Report — {report['timestamp'][:19]}")
    print(f"  Target: {report['base_url']}")
    print(f"  Duration: {report['elapsed_seconds']}s")
    print("=" * 60)
    print(f"\n  Total:  {report['total']}")
    print(f"  Passed: {report['passed']}")
    print(f"  Failed: {report['failed']}")
    print(f"  Errors: {report['errors']}")
    print(f"  Pass Rate: {report['pass_rate']}")

    if report["failure_breakdown"]:
        print(f"\n  Failure Breakdown:")
        for name, count in report["failure_breakdown"].items():
            print(f"    {name}: {count}")

    # Show details of failed cases
    failed_cases = [c for c in report["cases"] if not c["passed"]]
    if failed_cases:
        print(f"\n  Failed Cases ({len(failed_cases)}):")
        for fc in failed_cases[:10]:  # limit output
            print(f"    [{fc['case_id']}] {', '.join(fc['tags'][:3])}")
            for f in fc["failures"]:
                print(f"      FAIL {f['name']}: {f['detail'][:80]}")

        if len(failed_cases) > 10:
            print(f"    ... and {len(failed_cases) - 10} more")

    print()


def main():
    parser = argparse.ArgumentParser(description="Run Reclaim pipeline evals")
    parser.add_argument("--url", default=DEFAULT_URL, help="Base URL of the API")
    parser.add_argument("--tag", help="Filter cases by tag")
    parser.add_argument("--judges", action="store_true", help="Include LLM judge evals")
    parser.add_argument("--single", action="store_true", help="Send emails one at a time (slower)")
    parser.add_argument("--token", help="Google OAuth token for authenticated endpoints")
    parser.add_argument("--dry-run", action="store_true", help="Show cases without running")
    parser.add_argument("--output", help="Output report file path (default: auto-generated)")
    args = parser.parse_args()

    cases = load_cases(args.tag)
    print(f"Loaded {len(cases)} cases" + (f" (tag: {args.tag})" if args.tag else ""))

    if args.dry_run:
        for c in cases:
            tags = ", ".join(c.get("tags", []))
            extract = "EXTRACT" if c["expected"]["should_extract"] else "REJECT"
            print(f"  [{c['id']}] {extract} | {tags}")
        return

    try:
        import httpx
    except ImportError:
        print("ERROR: httpx is required. Install with: pip install httpx")
        sys.exit(1)

    # Set up HTTP client
    headers = {"Content-Type": "application/json"}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"

    client = httpx.Client(headers=headers)

    # Execute
    start = time.monotonic()

    if args.single:
        print(f"Sending {len(cases)} emails individually...")
        case_results = []
        for i, case in enumerate(cases):
            result = send_single(client, args.url, case)
            evaluation = evaluate_case(result, case, include_judges=args.judges)
            case_results.append(evaluation)
            status = "PASS" if evaluation["passed"] else "FAIL"
            print(f"  [{i + 1}/{len(cases)}] {case['id']}: {status}")
    else:
        print(f"Sending batch of {len(cases)} emails...")
        results_by_id = send_batch(client, args.url, cases)
        case_results = []
        for case in cases:
            result = results_by_id.get(case["id"], {
                "success": False,
                "rejection_reason": "missing_from_batch",
                "stage_reached": "error",
            })
            evaluation = evaluate_case(result, case, include_judges=args.judges)
            case_results.append(evaluation)

    elapsed = time.monotonic() - start
    client.close()

    # Generate report
    report = generate_report(case_results, args.url, elapsed)
    print_summary(report)

    # Save report
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    output_path = args.output or str(REPORTS_DIR / f"eval-{ts}.json")
    Path(output_path).write_text(json.dumps(report, indent=2))
    print(f"Report saved to {output_path}")

    # Exit with non-zero if any failures
    if report["failed"] > 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
