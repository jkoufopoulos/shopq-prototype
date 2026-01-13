#!/usr/bin/env python3
"""Find functions missing Side Effects documentation."""

import ast
from pathlib import Path


def check_file(filepath: Path) -> list[tuple[str, int, str]]:
    """Check a file for functions missing Side Effects documentation.

    Returns list of (filename, line_number, function_name) tuples.
    """
    missing = []

    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source)

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                # Skip private functions (start with _) - they inherit context
                if node.name.startswith("_") and not node.name.startswith("__"):
                    continue

                # Check if function has a docstring
                docstring = ast.get_docstring(node)
                if docstring and "Side Effects:" not in docstring:
                    missing.append((str(filepath), node.lineno, node.name))

    except Exception as e:
        print(f"Error processing {filepath}: {e}")

    return missing


def main():
    """Find all functions missing Side Effects documentation."""
    shopq_dir = Path("mailq")

    all_missing = []

    for py_file in shopq_dir.rglob("*.py"):
        # Skip __init__.py files - usually just imports
        if py_file.name == "__init__.py":
            continue

        missing = check_file(py_file)
        all_missing.extend(missing)

    # Group by file
    by_file = {}
    for filepath, lineno, funcname in all_missing:
        if filepath not in by_file:
            by_file[filepath] = []
        by_file[filepath].append((lineno, funcname))

    # Sort by number of missing functions (descending)
    sorted_files = sorted(by_file.items(), key=lambda x: len(x[1]), reverse=True)

    print(f"\n{'=' * 80}")
    print("Functions Missing 'Side Effects:' Documentation")
    print(f"{'=' * 80}\n")

    print(f"Total files with warnings: {len(sorted_files)}")
    print(f"Total functions missing documentation: {len(all_missing)}\n")

    for filepath, funcs in sorted_files[:30]:  # Top 30 files
        print(f"\n{filepath} - {len(funcs)} warnings:")
        for lineno, funcname in sorted(funcs, key=lambda x: x[0])[:10]:  # First 10 per file
            print(f"  Line {lineno}: {funcname}()")
        if len(funcs) > 10:
            print(f"  ... and {len(funcs) - 10} more")


if __name__ == "__main__":
    main()
