"""Tests for the principles validation script.

Tests cover:
- P2: Side Effects Are Loud, Not Sneaky
- P3: The Compiler Is Your Senior Engineer
- False positive prevention
"""

# Import the validator
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "scripts"))
from validate_principles import PrincipleValidator, find_python_files, validate_file


class TestP3TypeHints:
    """Tests for P3: The Compiler Is Your Senior Engineer."""

    def test_missing_return_type_is_error(self) -> None:
        """Functions without return type hints should be flagged."""
        code = """
def get_data():
    return {"key": "value"}
"""
        violations = self._validate_code(code)
        p3_errors = [v for v in violations if v.principle == "P3" and v.severity == "error"]
        assert len(p3_errors) >= 1
        assert any("Missing return type" in v.message for v in p3_errors)

    def test_missing_param_type_is_error(self) -> None:
        """Parameters without type hints should be flagged."""
        code = """
def process(data) -> str:
    return str(data)
"""
        violations = self._validate_code(code)
        p3_errors = [v for v in violations if v.principle == "P3" and v.severity == "error"]
        assert len(p3_errors) >= 1
        assert any("missing type hint" in v.message for v in p3_errors)

    def test_bare_dict_return_is_error(self) -> None:
        """Bare dict return type should be flagged (should use dict[str, Any])."""
        code = """
def get_config() -> dict:
    return {}
"""
        violations = self._validate_code(code)
        p3_errors = [v for v in violations if v.principle == "P3" and v.severity == "error"]
        assert len(p3_errors) >= 1
        assert any("should be parameterized" in v.message for v in p3_errors)

    def test_bare_list_return_is_error(self) -> None:
        """Bare list return type should be flagged (should use list[T])."""
        code = """
def get_items() -> list:
    return []
"""
        violations = self._validate_code(code)
        p3_errors = [v for v in violations if v.principle == "P3" and v.severity == "error"]
        assert len(p3_errors) >= 1
        assert any("should be parameterized" in v.message for v in p3_errors)

    def test_properly_typed_function_passes(self) -> None:
        """Properly typed functions should not be flagged."""
        code = """
def get_user(user_id: str) -> dict[str, str]:
    return {"id": user_id}
"""
        violations = self._validate_code(code)
        p3_errors = [v for v in violations if v.principle == "P3"]
        assert len(p3_errors) == 0

    def test_self_and_cls_excluded(self) -> None:
        """self and cls parameters should not require type hints."""
        code = """
class MyClass:
    def method(self, data: str) -> str:
        return data

    @classmethod
    def class_method(cls, data: str) -> str:
        return data
"""
        violations = self._validate_code(code)
        p3_errors = [v for v in violations if v.principle == "P3"]
        assert len(p3_errors) == 0

    def test_private_functions_excluded(self) -> None:
        """Private functions (starting with _) should be excluded."""
        code = """
def _private_helper():
    return "helper"
"""
        violations = self._validate_code(code)
        p3_errors = [v for v in violations if v.principle == "P3"]
        assert len(p3_errors) == 0

    def test_magic_methods_excluded(self) -> None:
        """Magic methods (__x__) should be excluded except __init__."""
        code = """
class MyClass:
    def __str__(self):
        return "MyClass"

    def __repr__(self):
        return "MyClass()"
"""
        violations = self._validate_code(code)
        p3_errors = [v for v in violations if v.principle == "P3"]
        assert len(p3_errors) == 0

    def _validate_code(self, code: str) -> list:
        """Helper to validate code string."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            return validate_file(Path(f.name))


class TestP2SideEffects:
    """Tests for P2: Side Effects Are Loud, Not Sneaky."""

    def test_db_write_without_docstring_is_error(self) -> None:
        """Functions with DB writes but no docstring should be errors."""
        code = """
def save_user(user_id: str) -> None:
    cursor.execute("INSERT INTO users VALUES (?)", (user_id,))
"""
        violations = self._validate_code(code)
        p2_errors = [v for v in violations if v.principle == "P2" and v.severity == "error"]
        assert len(p2_errors) >= 1
        assert any("missing docstring" in v.message for v in p2_errors)

    def test_db_write_without_side_effects_doc_is_warning(self) -> None:
        """Functions with DB writes but no Side Effects section should be warnings."""
        code = '''
def save_user(user_id: str) -> None:
    """Save a user to the database."""
    cursor.execute("INSERT INTO users VALUES (?)", (user_id,))
'''
        violations = self._validate_code(code)
        p2_warnings = [v for v in violations if v.principle == "P2" and v.severity == "warning"]
        assert len(p2_warnings) >= 1
        assert any("doesn't document them" in v.message for v in p2_warnings)

    def test_db_write_with_side_effects_doc_passes(self) -> None:
        """Functions with DB writes and Side Effects section should pass."""
        code = '''
def save_user(user_id: str) -> None:
    """Save a user to the database.

    Side Effects:
        - Writes to users table
    """
    cursor.execute("INSERT INTO users VALUES (?)", (user_id,))
'''
        violations = self._validate_code(code)
        p2_violations = [v for v in violations if v.principle == "P2"]
        assert len(p2_violations) == 0

    def test_select_query_not_flagged(self) -> None:
        """SELECT queries should not be flagged as side effects."""
        code = '''
def get_user(user_id: str) -> dict[str, str]:
    """Get user by ID."""
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    return cursor.fetchone()
'''
        violations = self._validate_code(code)
        p2_violations = [v for v in violations if v.principle == "P2"]
        # Should not flag SELECT as a side effect
        db_write_violations = [v for v in p2_violations if "database writes" in v.message]
        assert len(db_write_violations) == 0

    def _validate_code(self, code: str) -> list:
        """Helper to validate code string."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            return validate_file(Path(f.name))


class TestP2FalsePositives:
    """Tests to ensure false positives are prevented."""

    def test_post_init_not_flagged(self) -> None:
        """__post_init__ should not be flagged (dataclass hook)."""
        code = """
from dataclasses import dataclass

@dataclass
class User:
    name: str

    def __post_init__(self) -> None:
        self.name = self.name.strip()
"""
        violations = self._validate_code(code)
        p2_violations = [v for v in violations if v.principle == "P2"]
        assert len(p2_violations) == 0

    def test_validate_function_not_flagged(self) -> None:
        """validate_* functions should not be flagged (pure validators)."""
        code = '''
def validate_email(email: str) -> bool:
    """Check if email is valid."""
    return "@" in email
'''
        violations = self._validate_code(code)
        p2_violations = [v for v in violations if v.principle == "P2"]
        assert len(p2_violations) == 0

    def test_compute_function_not_flagged(self) -> None:
        """compute_* functions should not be flagged (pure computation)."""
        code = '''
def compute_hash(data: str) -> str:
    """Compute hash of data."""
    return hash(data)
'''
        violations = self._validate_code(code)
        p2_violations = [v for v in violations if v.principle == "P2"]
        assert len(p2_violations) == 0

    def test_dispatch_not_flagged(self) -> None:
        """dispatch methods should not be flagged (middleware routing)."""
        code = '''
class Middleware:
    async def dispatch(self, request: object, call_next: object) -> object:
        """Handle request dispatch."""
        return await call_next(request)
'''
        violations = self._validate_code(code)
        p2_violations = [v for v in violations if v.principle == "P2"]
        assert len(p2_violations) == 0

    def test_sanitize_not_flagged(self) -> None:
        """sanitize_* functions should not be flagged (pure transformation)."""
        code = '''
def sanitize_input(text: str) -> str:
    """Sanitize user input."""
    return text.strip().lower()
'''
        violations = self._validate_code(code)
        p2_violations = [v for v in violations if v.principle == "P2"]
        assert len(p2_violations) == 0

    def test_get_function_not_flagged(self) -> None:
        """get_* functions should not be flagged (getters)."""
        code = '''
def get_config() -> dict[str, str]:
    """Get configuration."""
    return {"key": "value"}
'''
        violations = self._validate_code(code)
        p2_violations = [v for v in violations if v.principle == "P2"]
        assert len(p2_violations) == 0

    def test_real_save_still_caught_when_detected(self) -> None:
        """save_* functions WITH detectable side effects should still be flagged."""
        code = '''
def save_to_db(data: str) -> None:
    """Save data."""
    conn.execute("INSERT INTO table VALUES (?)", (data,))
    conn.commit()
'''
        violations = self._validate_code(code)
        p2_violations = [v for v in violations if v.principle == "P2"]
        # Should catch the commit() as a side effect
        assert len(p2_violations) >= 1

    def _validate_code(self, code: str) -> list:
        """Helper to validate code string."""
        with tempfile.NamedTemporaryFile(mode="w", suffix=".py", delete=False) as f:
            f.write(code)
            f.flush()
            return validate_file(Path(f.name))


class TestFindPythonFiles:
    """Tests for file discovery logic."""

    def test_excludes_pycache(self) -> None:
        """__pycache__ directories should be excluded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            pycache = Path(tmpdir) / "__pycache__"
            pycache.mkdir()
            (pycache / "module.py").write_text("x = 1")

            files = find_python_files([Path(tmpdir)])
            assert len(files) == 0

    def test_excludes_test_files(self) -> None:
        """test_* files should be excluded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "test_module.py").write_text("x = 1")
            (Path(tmpdir) / "module.py").write_text("x = 1")

            files = find_python_files([Path(tmpdir)])
            assert len(files) == 1
            assert files[0].name == "module.py"

    def test_excludes_archive(self) -> None:
        """scripts/archive/ should be excluded."""
        with tempfile.TemporaryDirectory() as tmpdir:
            archive = Path(tmpdir) / "scripts" / "archive"
            archive.mkdir(parents=True)
            (archive / "old_script.py").write_text("x = 1")

            files = find_python_files([Path(tmpdir)])
            assert len(files) == 0

    def test_includes_regular_scripts(self) -> None:
        """Regular scripts should be included."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scripts = Path(tmpdir) / "scripts"
            scripts.mkdir()
            (scripts / "util.py").write_text("x = 1")

            files = find_python_files([Path(tmpdir)])
            assert len(files) == 1


class TestValidatorKeywords:
    """Tests for keyword configuration."""

    def test_side_effect_keywords_are_conservative(self) -> None:
        """SIDE_EFFECT_KEYWORDS should only contain high-confidence keywords."""
        # These should NOT be in SIDE_EFFECT_KEYWORDS (too many false positives)
        false_positive_prone = {
            "update",  # Often used in pure dict updates
            "execute",  # Often abstract methods
            "send",  # Often stubs/mocks
            "post",  # Often HTTP method names
            "put",  # Often cache operations
            "patch",  # Often HTTP method names
            "set",  # Setters are often not side effects
            "remove",  # Often list operations
            "clear",  # Often cache clearing (in-memory)
            "reset",  # Often state reset (in-memory)
            "create",  # Often creates objects, not DB records
        }

        for keyword in false_positive_prone:
            assert keyword not in PrincipleValidator.SIDE_EFFECT_KEYWORDS, (
                f"'{keyword}' should not be in SIDE_EFFECT_KEYWORDS (prone to false positives)"
            )

    def test_pure_function_keywords_exist(self) -> None:
        """PURE_FUNCTION_KEYWORDS should contain common pure function patterns."""
        expected = {"validate", "compute", "parse", "sanitize", "get", "dispatch"}
        for keyword in expected:
            assert keyword in PrincipleValidator.PURE_FUNCTION_KEYWORDS, (
                f"'{keyword}' should be in PURE_FUNCTION_KEYWORDS"
            )

    def test_false_positive_patterns_exist(self) -> None:
        """FALSE_POSITIVE_PATTERNS should contain known false positive function names."""
        expected = {"__post_init__", "_post_checks"}
        for pattern in expected:
            assert pattern in PrincipleValidator.FALSE_POSITIVE_PATTERNS, (
                f"'{pattern}' should be in FALSE_POSITIVE_PATTERNS"
            )
