#!/usr/bin/env python3
"""Automatically add Side Effects documentation to functions that are clearly pure."""

import ast
import re
from pathlib import Path

# Patterns that indicate a function is likely pure
PURE_FUNCTION_INDICATORS = [
    # Validators
    r"^validate_",
    r"_validator$",
    # Getters/accessors (property-like)
    r"^get_\w+_name$",
    r"^get_\w+_config$",
    r"^get_\w+_status$",
    # Formatters/renderers (usually pure if no file I/O)
    r"^format_",
    r"^render_\w+$",  # Be careful - some render_ write files
    # Calculators/computations
    r"^calculate_",
    r"^compute_",
    # Builders (dict/list builders)
    r"^build_",
    # Converters
    r"^to_dict$",
    r"^to_json$",
    r"^to_\w+$",
    # String operations
    r"^sanitize_",
    r"^normalize_",
    r"^clean_",
    # Comparisons
    r"^compare_",
    r"^equals$",
    # Checks/predicates
    r"^is_",
    r"^has_",
    r"^can_",
    r"^should_",
]

# Patterns that indicate a function has side effects
SIDE_EFFECT_INDICATORS = [
    r"^record_",
    r"^save_",
    r"^write_",
    r"^delete_",
    r"^update_",
    r"^create_",
    r"^send_",
    r"^upload_",
    r"^download_",
    r"^apply_",
    r"^set_",
    r"^add_",
    r"^remove_",
    r"^log_event",
    r"^init_",
    r"^__init__$",
]


def is_likely_pure(func_name: str, body_source: str) -> bool:
    """Check if function is likely pure based on name and body analysis."""
    # Check if matches pure indicators
    for pattern in PURE_FUNCTION_INDICATORS:
        if re.search(pattern, func_name):
            # Double check body doesn't have obvious side effects
            if not any(
                keyword in body_source for keyword in ["write(", "execute(", "commit(", "cursor."]
            ):
                return True

    # Check if explicitly has side effects
    for pattern in SIDE_EFFECT_INDICATORS:
        if re.search(pattern, func_name):
            return False

    # Check body for side effect keywords
    side_effect_keywords = [
        "cursor.execute(",
        ".execute(",
        ".commit(",
        ".save(",
        "open(",
        "write(",
        "log_event(",
        "counter(",
        "INSERT INTO",
        "UPDATE ",
        "DELETE FROM",
    ]

    if any(keyword in body_source for keyword in side_effect_keywords):
        return False

    return False  # Conservative: default to requiring manual review


def add_side_effects_doc(filepath: Path, dry_run: bool = True) -> tuple[int, list[str]]:
    """Add Side Effects documentation to functions missing it.

    Returns:
        Tuple of (num_updated, list_of_updated_functions)
    """
    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return 0, []

    # Parse AST
    try:
        tree = ast.parse(source)
    except SyntaxError as e:
        print(f"Syntax error in {filepath}: {e}")
        return 0, []

    updates = []
    lines = source.splitlines()

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue

        # Skip private functions (inherit context from parent)
        if node.name.startswith("_") and not node.name.startswith("__"):
            continue

        # Check if already has Side Effects documentation
        docstring = ast.get_docstring(node)
        if not docstring or "Side Effects:" in docstring:
            continue

        # Get function body source for analysis
        func_start = node.lineno - 1
        func_end = node.end_lineno if hasattr(node, "end_lineno") else func_start + 10
        body_source = "\n".join(lines[func_start:func_end])

        # Determine if pure
        if is_likely_pure(node.name, body_source):
            updates.append((node.lineno, node.name, "pure"))
        else:
            # Not auto-documenting functions with side effects (too risky)
            # Just flag them for manual review
            pass

    if dry_run or not updates:
        return len(updates), [name for _, name, _ in updates]

    # Apply updates (would need more sophisticated text manipulation)
    # For now, just return what we'd update
    return len(updates), [name for _, name, _ in updates]


def main():
    """Find and document pure functions."""
    shopq_dir = Path("mailq")

    total_pure = 0
    all_updates = {}

    for py_file in shopq_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue

        count, funcs = add_side_effects_doc(py_file, dry_run=True)
        if count > 0:
            total_pure += count
            all_updates[str(py_file)] = funcs

    print(f"\n{'=' * 80}")
    print("Pure Functions That Can Be Auto-Documented")
    print(f"{'=' * 80}\n")

    print(f"Total pure functions identified: {total_pure}\n")

    for filepath, funcs in sorted(all_updates.items(), key=lambda x: len(x[1]), reverse=True)[:20]:
        print(f"\n{filepath} - {len(funcs)} pure functions:")
        for func in funcs[:10]:
            print(f"  - {func}()")
        if len(funcs) > 10:
            print(f"  ... and {len(funcs) - 10} more")


if __name__ == "__main__":
    main()
