#!/usr/bin/env python3
"""
Pre-commit hook to enforce file size limits.

Prevents Python files from exceeding the LOC limit to maintain code quality
and encourage modular design.

Usage:
    python scripts/check_file_size.py [--max-lines 500] [files...]

If no files specified, checks all staged Python files in shopq/ directory.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

# Default configuration
DEFAULT_MAX_LINES = 500
CHECKED_DIRECTORIES = ["shopq/"]
EXCLUDED_PATTERNS = [
    "__init__.py",  # Init files can be large due to re-exports
    "test_",  # Test files can be long
    "_test.py",
    "conftest.py",
]


def count_lines(file_path: Path) -> int:
    """Count non-empty, non-comment lines in a Python file."""
    try:
        with open(file_path, encoding="utf-8") as f:
            lines = f.readlines()
    except (OSError, UnicodeDecodeError):
        return 0

    # Count all lines (including comments/blank for simplicity)
    # This matches `wc -l` behavior
    return len(lines)


def is_excluded(file_path: Path) -> bool:
    """Check if file should be excluded from size check."""
    name = file_path.name
    return any(pattern in name for pattern in EXCLUDED_PATTERNS)


def get_staged_files() -> list[Path]:
    """Get list of staged Python files in checked directories."""
    try:
        result = subprocess.run(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            capture_output=True,
            text=True,
            check=True,
        )
        files = result.stdout.strip().split("\n")
        return [
            Path(f)
            for f in files
            if f.endswith(".py")
            and any(f.startswith(d) for d in CHECKED_DIRECTORIES)
            and not is_excluded(Path(f))
        ]
    except subprocess.CalledProcessError:
        return []


def check_files(files: list[Path], max_lines: int) -> list[tuple[Path, int]]:
    """Check files for size violations."""
    violations = []
    for file_path in files:
        if not file_path.exists():
            continue
        if is_excluded(file_path):
            continue

        line_count = count_lines(file_path)
        if line_count > max_lines:
            violations.append((file_path, line_count))

    return violations


def main() -> int:
    parser = argparse.ArgumentParser(description="Check Python files don't exceed LOC limit")
    parser.add_argument(
        "--max-lines",
        type=int,
        default=DEFAULT_MAX_LINES,
        help=f"Maximum lines allowed per file (default: {DEFAULT_MAX_LINES})",
    )
    parser.add_argument(
        "files",
        nargs="*",
        type=Path,
        help="Files to check (default: staged files in shopq/)",
    )
    args = parser.parse_args()

    # Get files to check
    files = [f for f in args.files if f.suffix == ".py"] if args.files else get_staged_files()

    if not files:
        return 0

    # Check for violations
    violations = check_files(files, args.max_lines)

    if violations:
        print(f"\n{'=' * 60}")
        print(f"FILE SIZE LIMIT EXCEEDED (max {args.max_lines} lines)")
        print(f"{'=' * 60}\n")

        for file_path, line_count in sorted(violations, key=lambda x: -x[1]):
            excess = line_count - args.max_lines
            print(f"  {file_path}: {line_count} lines (+{excess} over limit)")

        print(f"\n{'=' * 60}")
        print("To fix: Extract helper functions/classes into separate modules")
        print("See docs/CORE_PRINCIPLES.md (P1: Concepts Are Rooms)")
        print(f"{'=' * 60}\n")

        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
