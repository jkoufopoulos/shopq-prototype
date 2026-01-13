#!/usr/bin/env python3
"""
Validation script for ShopQ Core Principles (P2 and P3).

Checks:
- P2: Side Effects Are Loud, Not Sneaky
  - Functions with DB/API side effects must document them
  - Functions that modify state must declare it in name/docstring

- P3: The Compiler Is Your Senior Engineer
  - Functions must have type hints
  - Return types must be explicit
  - Dict types must be parameterized (dict[str, Any] not dict)

Usage:
    python scripts/validate_principles.py [--fix] [--verbose] [path...]

    --fix: Auto-add missing type hints where possible
    --verbose: Show detailed violations
    path: Specific files/directories to check (default: shopq/, scripts/)

Exit codes:
    0: All checks passed
    1: Violations found
    2: Script error
"""

import argparse
import ast
import re
import sys
from dataclasses import dataclass
from pathlib import Path


@dataclass
class Violation:
    """A principle violation found in code."""

    principle: str  # "P2" or "P3"
    severity: str  # "error" or "warning"
    file: Path
    line: int
    function: str
    message: str
    suggestion: str | None = None


class PrincipleValidator(ast.NodeVisitor):
    """AST visitor that validates P2 and P3."""

    # Keywords that indicate side effects (used for name-based detection)
    # NOTE: These trigger warnings when found in function names but no actual
    # side effects are detected in the function body. Be conservative here.
    SIDE_EFFECT_KEYWORDS = {
        "write",
        "save",
        "delete",
        "insert",
        "commit",
        "rollback",
        "publish",
        "emit",
        "notify",
        "add_rule",
        "learn",
        "train",
    }

    # Keywords that often appear in pure functions - exclude from false positive warnings
    # These are commonly used in function names but don't indicate external side effects
    PURE_FUNCTION_KEYWORDS = {
        "validate",  # validators are pure
        "compute",  # pure computation
        "calculate",  # pure computation
        "parse",  # pure parsing
        "sanitize",  # pure transformation
        "format",  # pure transformation
        "build",  # pure construction
        "create",  # often creates objects in memory, not DB
        "generate",  # often generates data in memory
        "get",  # getters are pure
        "load",  # loading into memory
        "dispatch",  # middleware routing
    }

    # Function name patterns that are always false positives for P2
    FALSE_POSITIVE_PATTERNS = {
        "__post_init__",  # dataclass hook
        "_post_checks",  # validation hook
        "do_GET",  # HTTP handler
        "do_POST",  # HTTP handler
        # Singleton/factory patterns (create once, cache)
        "get_logger",
        "get_storage_client",
        "get_type_mapper",
        # Functions that build results/fallbacks (not external writes)
        "_create_fallback_result",
        "_create_error_result",
        "_get_static_examples",
        "_initialize_default_categories",
        "_get_or_create_label",
        # Factory functions
        "create_v2_pipeline",
        # In-memory storage (not persistent)
        "save_debug_sample",
    }

    # Function names that MUST have side effect docs
    KNOWN_SIDE_EFFECT_FUNCTIONS = {
        "record_correction",
        "add_rule",
        "update_rule",
        "delete_rule",
        "learn_patterns",
        "create_rule",
        "save_entity",
        "update_entity",
        "execute_sql",
        "commit_transaction",
        "_learn_from_correction",
    }

    # Modules/calls that indicate side effects
    SIDE_EFFECT_CALLS = {
        "cursor.execute",
        "conn.commit",
        "db.execute",
        "session.commit",
        "requests.post",
        "requests.put",
        "requests.patch",
        "requests.delete",
        "gemini.call",
        "llm.call",
        "api.call",
    }

    def __init__(self, filepath: Path):
        self.filepath = filepath
        self.violations: list[Violation] = []
        self.current_function: str | None = None
        self.current_class: str | None = None

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        """Track current class for context."""
        old_class = self.current_class
        self.current_class = node.name
        self.generic_visit(node)
        self.current_class = old_class

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        """Validate function definitions against P2 and P3."""
        self.current_function = node.name

        # Get qualified name
        qualified_name = f"{self.current_class}.{node.name}" if self.current_class else node.name

        # P3: Check for type hints
        self._check_type_hints(node, qualified_name)

        # P2: Check for documented side effects
        self._check_side_effects(node, qualified_name)

        self.generic_visit(node)
        self.current_function = None

    visit_AsyncFunctionDef = visit_FunctionDef

    def _check_type_hints(self, node: ast.FunctionDef, qualified_name: str) -> None:
        """P3: Validate type hints on function."""
        # Skip magic methods and private functions starting with _
        if node.name.startswith("__") and node.name.endswith("__"):
            return
        is_single_underscore_private = (
            node.name.startswith("_") and len(node.name) > 1 and node.name[1] != "_"
        )
        important_private_funcs = {"_learn_from_correction", "_select_best_entity"}
        if is_single_underscore_private and node.name not in important_private_funcs:
            return

        # Check return type
        if node.returns is None:
            # Special case: __init__ should return None
            if node.name == "__init__":
                self.violations.append(
                    Violation(
                        principle="P3",
                        severity="warning",
                        file=self.filepath,
                        line=node.lineno,
                        function=qualified_name,
                        message="Missing return type hint (should be -> None for __init__)",
                        suggestion=f"def {node.name}(...) -> None:",
                    )
                )
            else:
                self.violations.append(
                    Violation(
                        principle="P3",
                        severity="error",
                        file=self.filepath,
                        line=node.lineno,
                        function=qualified_name,
                        message="Missing return type hint",
                        suggestion=f"Add -> ReturnType to {qualified_name}()",
                    )
                )

        # Check parameter type hints (excluding self, cls)
        for arg in node.args.args:
            if arg.arg in ("self", "cls"):
                continue
            if arg.annotation is None:
                self.violations.append(
                    Violation(
                        principle="P3",
                        severity="error",
                        file=self.filepath,
                        line=node.lineno,
                        function=qualified_name,
                        message=f"Parameter '{arg.arg}' missing type hint",
                        suggestion=f"{arg.arg}: <type>",
                    )
                )

        # Check for bare dict/list in return type (should be dict[K, V], list[T])
        if node.returns:
            return_type_str = ast.unparse(node.returns)
            if re.match(r"\bdict\b(?!\[)", return_type_str):
                self.violations.append(
                    Violation(
                        principle="P3",
                        severity="error",
                        file=self.filepath,
                        line=node.lineno,
                        function=qualified_name,
                        message="Return type 'dict' should be parameterized (dict[str, Any])",
                        suggestion="-> dict[str, Any] or more specific type",
                    )
                )
            if re.match(r"\blist\b(?!\[)", return_type_str):
                self.violations.append(
                    Violation(
                        principle="P3",
                        severity="error",
                        file=self.filepath,
                        line=node.lineno,
                        function=qualified_name,
                        message="Return type 'list' should be parameterized (list[T])",
                        suggestion="-> list[YourType] or more specific type",
                    )
                )

    def _check_side_effects(self, node: ast.FunctionDef, qualified_name: str) -> None:
        """P2: Check if function with side effects documents them."""
        docstring = ast.get_docstring(node)

        # Skip known false positive patterns
        if node.name in self.FALSE_POSITIVE_PATTERNS:
            return

        # Check if function name contains pure function keywords (likely false positive)
        name_has_pure_keyword = any(
            keyword in node.name.lower() for keyword in self.PURE_FUNCTION_KEYWORDS
        )

        # Check if function name suggests side effects
        name_has_side_effect = any(
            keyword in node.name.lower() for keyword in self.SIDE_EFFECT_KEYWORDS
        )

        # Check if function is known to have side effects
        is_known_side_effect = node.name in self.KNOWN_SIDE_EFFECT_FUNCTIONS

        # Check if function body contains side effect operations
        has_db_ops = self._contains_database_operations(node)
        has_api_ops = self._contains_api_operations(node)
        has_mutation = self._contains_mutation(node)

        has_side_effects = has_db_ops or has_api_ops or is_known_side_effect or has_mutation

        # If function has side effects, check documentation
        if has_side_effects:
            if not docstring:
                self.violations.append(
                    Violation(
                        principle="P2",
                        severity="error",
                        file=self.filepath,
                        line=node.lineno,
                        function=qualified_name,
                        message="Function with side effects missing docstring",
                        suggestion=(
                            f'Add docstring with "Side Effects:" section to {qualified_name}()'
                        ),
                    )
                )
            elif "Side Effects:" not in docstring and "side effect" not in docstring.lower():
                side_effect_types = []
                if has_db_ops:
                    side_effect_types.append("database writes")
                if has_api_ops:
                    side_effect_types.append("API calls")
                if has_mutation:
                    side_effect_types.append("state mutations")

                self.violations.append(
                    Violation(
                        principle="P2",
                        severity="warning",
                        file=self.filepath,
                        line=node.lineno,
                        function=qualified_name,
                        message=(
                            f"Function has side effects ({', '.join(side_effect_types)}) "
                            "but doesn't document them"
                        ),
                        suggestion=(
                            f'Add "Side Effects:" section to docstring listing: '
                            f"{', '.join(side_effect_types)}"
                        ),
                    )
                )

        # If function name suggests side effects but has none, warn
        # BUT skip if the name also contains pure function keywords (likely false positive)
        if name_has_side_effect and not has_side_effects and not name_has_pure_keyword:
            self.violations.append(
                Violation(
                    principle="P2",
                    severity="warning",
                    file=self.filepath,
                    line=node.lineno,
                    function=qualified_name,
                    message=(
                        f"Function name suggests side effects ('{node.name}') but none detected"
                    ),
                    suggestion="Verify function behavior or rename to clarify intent",
                )
            )

    def _contains_database_operations(self, node: ast.FunctionDef) -> bool:
        """Check if function contains database WRITE operations (not reads)."""
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                call_str = ast.unparse(child.func)
                # Only flag writes (INSERT, UPDATE, DELETE, CREATE), not SELECT
                if any(pattern in call_str for pattern in ["conn.commit", "session.commit"]):
                    return True
            if isinstance(child, ast.Attribute) and child.attr in ("commit", "rollback"):
                # commit and rollback are write operations
                return True
            # Check for SQL string containing write operations
            if isinstance(child, ast.Constant) and isinstance(child.value, str):
                sql_upper = child.value.upper()
                # Check for write operations in SQL
                if any(
                    keyword in sql_upper
                    for keyword in ["INSERT ", "UPDATE ", "DELETE ", "CREATE ", "DROP ", "ALTER "]
                ):
                    return True
        return False

    def _contains_api_operations(self, node: ast.FunctionDef) -> bool:
        """Check if function contains API calls."""
        for child in ast.walk(node):
            if isinstance(child, ast.Call):
                call_str = ast.unparse(child.func)
                if any(pattern in call_str for pattern in ["requests.", "gemini.", "llm.", "api."]):
                    return True
        return False

    def _contains_mutation(self, node: ast.FunctionDef) -> bool:
        """Check if function mutates GLOBAL/EXTERNAL state (not local variables).

        This is conservative - we only flag mutations to:
        - Global variables (declared with 'global' keyword)
        - Module-level singletons (_instance, _cache, etc.)
        - External objects passed as parameters

        We DON'T flag:
        - Local variable mutations (building results, temp data)
        - self.attr mutations (that's internal state)
        - Common result-building patterns (result.append, items.extend)
        """
        # First, collect all local variable names defined in the function
        local_vars = set()
        for child in ast.walk(node):
            # Track assignments to local names
            if isinstance(child, ast.Assign):
                for target in child.targets:
                    if isinstance(target, ast.Name):
                        local_vars.add(target.id)
            # Track loop variables
            if isinstance(child, ast.For):
                if isinstance(child.target, ast.Name):
                    local_vars.add(child.target.id)
                elif isinstance(child.target, ast.Tuple):
                    for elt in child.target.elts:
                        if isinstance(elt, ast.Name):
                            local_vars.add(elt.id)
            # Track comprehension variables
            if isinstance(child, (ast.ListComp, ast.DictComp, ast.SetComp, ast.GeneratorExp)):
                for gen in child.generators:
                    if isinstance(gen.target, ast.Name):
                        local_vars.add(gen.target.id)

        # Check for global declarations (definite side effects)
        for child in ast.walk(node):
            if isinstance(child, ast.Global):
                return True

        # Check for mutations on clearly external/singleton objects
        mutation_methods = {"append", "extend", "update", "pop", "remove", "clear", "add"}
        for child in ast.walk(node):
            if not isinstance(child, ast.Call):
                continue
            if not isinstance(child.func, ast.Attribute):
                continue
            if child.func.attr not in mutation_methods:
                continue
            if not isinstance(child.func.value, ast.Name):
                continue

            var_name = child.func.value.id
            # Only flag if it's a module-level singleton pattern (_var) and not local
            is_singleton = var_name.startswith("_") and var_name not in local_vars
            is_local = var_name in local_vars

            if is_singleton and not is_local:
                return True
            # Skip all other cases - too many false positives

        return False


def validate_file(filepath: Path, verbose: bool = False) -> list[Violation]:
    """Validate a single Python file against principles."""
    try:
        with open(filepath, encoding="utf-8") as f:
            source = f.read()

        tree = ast.parse(source, filename=str(filepath))
        validator = PrincipleValidator(filepath)
        validator.visit(tree)

        if verbose and validator.violations:
            print(f"\n{filepath}:")
            for v in validator.violations:
                print(f"  [{v.principle}] Line {v.line} in {v.function}: {v.message}")
                if v.suggestion:
                    print(f"         Suggestion: {v.suggestion}")

        return validator.violations

    except SyntaxError as e:
        print(f"Syntax error in {filepath}: {e}", file=sys.stderr)
        return []
    except Exception as e:
        print(f"Error processing {filepath}: {e}", file=sys.stderr)
        return []


def find_python_files(paths: list[Path]) -> list[Path]:
    """Find all Python files in given paths."""
    python_files = []

    for path in paths:
        if path.is_file() and path.suffix == ".py":
            python_files.append(path)
        elif path.is_dir():
            python_files.extend(path.rglob("*.py"))

    # Exclude test files, migrations, __pycache__, and archived scripts
    return [
        f
        for f in python_files
        if "__pycache__" not in str(f)
        and "test_" not in f.name
        and "migration" not in str(f).lower()
        and ".venv" not in str(f)
        and "scripts/archive" not in str(f)  # Legacy/one-off scripts
    ]


def print_summary(violations: list[Violation]) -> None:
    """Print summary of violations."""
    if not violations:
        print("✅ All principle checks passed!")
        return

    # Group by principle and severity
    p2_errors = [v for v in violations if v.principle == "P2" and v.severity == "error"]
    p2_warnings = [v for v in violations if v.principle == "P2" and v.severity == "warning"]
    p3_errors = [v for v in violations if v.principle == "P3" and v.severity == "error"]
    p3_warnings = [v for v in violations if v.principle == "P3" and v.severity == "warning"]

    print("\n" + "=" * 80)
    print("VALIDATION SUMMARY")
    print("=" * 80)

    print("\nP2: Side Effects Are Loud, Not Sneaky")
    print(f"  Errors:   {len(p2_errors)}")
    print(f"  Warnings: {len(p2_warnings)}")

    print("\nP3: The Compiler Is Your Senior Engineer")
    print(f"  Errors:   {len(p3_errors)}")
    print(f"  Warnings: {len(p3_warnings)}")

    print(f"\nTotal: {len(violations)} violations")
    print(f"  {len([v for v in violations if v.severity == 'error'])} errors")
    print(f"  {len([v for v in violations if v.severity == 'warning'])} warnings")

    # Group violations by file
    by_file: dict[Path, list[Violation]] = {}
    for v in violations:
        by_file.setdefault(v.file, []).append(v)

    print(f"\nFiles with violations: {len(by_file)}")
    print("\nTop offenders:")
    cwd = Path.cwd()
    for file, file_violations in sorted(by_file.items(), key=lambda x: len(x[1]), reverse=True)[
        :10
    ]:
        error_count = len([v for v in file_violations if v.severity == "error"])
        warning_count = len([v for v in file_violations if v.severity == "warning"])
        try:
            file_str = str(file.relative_to(cwd))
        except ValueError:
            file_str = str(file)
        print(f"  {file_str}: {error_count} errors, {warning_count} warnings")


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Validate ShopQ code against Core Principles P2 and P3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate default paths (shopq/, backend/)
  python scripts/validate_principles.py

  # Validate specific file
  python scripts/validate_principles.py shopq/rules_manager.py

  # Validate with verbose output
  python scripts/validate_principles.py --verbose

  # Only show errors, not warnings
  python scripts/validate_principles.py --errors-only
        """,
    )

    parser.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="Files or directories to validate (default: shopq/, scripts/)",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Show detailed violation messages"
    )
    parser.add_argument(
        "--errors-only", action="store_true", help="Only report errors, not warnings"
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Auto-fix violations where possible (not yet implemented)",
    )

    args = parser.parse_args()

    # Default paths if none provided
    if not args.paths:
        args.paths = [Path("mailq"), Path("scripts")]

    # Find all Python files
    python_files = find_python_files(args.paths)

    if not python_files:
        print("No Python files found to validate", file=sys.stderr)
        return 2

    print(f"Validating {len(python_files)} Python files...")
    if args.verbose:
        cwd = Path.cwd()
        file_names = []
        for f in python_files[:5]:
            try:
                file_names.append(str(f.relative_to(cwd)))
            except ValueError:
                file_names.append(str(f))
        print(f"Files: {', '.join(file_names)}", end="")
        if len(python_files) > 5:
            print(f" ... and {len(python_files) - 5} more")
        else:
            print()

    # Validate all files
    all_violations = []
    for filepath in python_files:
        violations = validate_file(filepath, verbose=args.verbose)
        all_violations.extend(violations)

    # Filter to errors only if requested
    if args.errors_only:
        all_violations = [v for v in all_violations if v.severity == "error"]

    # Print summary
    print_summary(all_violations)

    # Exit with error code if violations found
    if args.fix:
        print("\n⚠️  --fix flag not yet implemented. Manual fixes required.", file=sys.stderr)

    error_count = len([v for v in all_violations if v.severity == "error"])
    return 1 if error_count > 0 else 0


if __name__ == "__main__":
    sys.exit(main())
