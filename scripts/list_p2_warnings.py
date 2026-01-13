#!/usr/bin/env python3
"""Extract P2 warnings from validation script for focused fixing."""

from pathlib import Path

from validate_principles import find_python_files, validate_file


def main():
    paths = [Path("mailq")]
    python_files = find_python_files(paths)

    all_violations = []
    for filepath in python_files:
        violations = validate_file(filepath, verbose=False)
        all_violations.extend(violations)

    # Filter to P2 warnings only
    p2_warnings = [v for v in all_violations if v.principle == "P2" and v.severity == "warning"]

    # Group by file
    by_file = {}
    for v in p2_warnings:
        by_file.setdefault(v.file, []).append(v)

    # Sort by count
    for file, violations in sorted(by_file.items(), key=lambda x: len(x[1]), reverse=True):
        try:
            file_str = str(file.relative_to(Path.cwd()))
        except ValueError:
            file_str = str(file)
        print(f"\n{file_str} ({len(violations)} warnings):")
        for v in violations:
            print(f"  Line {v.line}: {v.function}")
            print(f"    {v.message}")

    print(f"\n\nTotal P2 warnings: {len(p2_warnings)}")


if __name__ == "__main__":
    main()
