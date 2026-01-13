"""
Minimal pytest-compatible runner for offline environments.

Supports:
  - @pytest.fixture(autouse=True) with optional yield teardown
  - pytest.mark.parametrize
  - pytest.raises

This is intentionally lightweight and only covers the APIs used by the current test suite.
"""

from __future__ import annotations

import contextlib
import importlib.util
import inspect
import os
import sys
import traceback
from collections.abc import Callable, Iterable, Iterator, Sequence
from dataclasses import dataclass
from types import ModuleType

# -----------------------
# Pytest-compatible APIs
# -----------------------


@dataclass
class _FixtureInfo:
    autouse: bool


def fixture(*, autouse: bool = False):
    def decorator(func: Callable) -> Callable:
        func._pytest_fixture = _FixtureInfo(autouse=autouse)
        return func

    return decorator


class raises(contextlib.AbstractContextManager):
    def __init__(self, expected_exception: type[BaseException], match: str | None = None):
        self.expected_exception = expected_exception
        self.match = match
        self._caught = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> bool:
        if exc_type is None:
            raise AssertionError(f"Expected {self.expected_exception.__name__} to be raised")
        if not issubclass(exc_type, self.expected_exception):
            return False
        if self.match and self.match not in str(exc_val):
            raise AssertionError(f"Exception message '{exc_val}' does not contain '{self.match}'")
        self._caught = exc_val
        return True


class _Mark:
    @staticmethod
    def parametrize(argnames: str, argvalues: Sequence) -> Callable:
        names = [name.strip() for name in argnames.split(",")]

        def decorator(func: Callable) -> Callable:
            func._pytest_parametrize = names, list(argvalues)
            return func

        return decorator


mark = _Mark()


# -----------------------
# Runner implementation
# -----------------------


@dataclass
class _TestCase:
    module: ModuleType
    func: Callable
    fixtures: list[Callable]
    case_index: int | None = None
    args: tuple = ()
    kwargs: dict = None

    @property
    def name(self) -> str:
        base = f"{self.module.__name__}.{self.func.__name__}"
        if self.case_index is not None:
            base += f"[{self.case_index}]"
        return base


_SKIP_DIRS = {"manual", "outputs", "playwright-report", "__pycache__"}


def _iter_test_files(start_paths: Iterable[str]) -> Iterable[str]:
    for start in start_paths:
        if os.path.isfile(start) and start.endswith(".py"):
            yield os.path.abspath(start)
            continue
        for root, dirs, files in os.walk(start):
            dirs[:] = [d for d in dirs if d not in _SKIP_DIRS]
            for file in files:
                if file.startswith("test_") and file.endswith(".py"):
                    yield os.path.join(root, file)


def _import_module_from_path(path: str) -> ModuleType:
    module_name = f"_mini_pytest_{hash(path)}"
    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot import module from {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _collect_autouse_fixtures(module: ModuleType) -> list[Callable]:
    fixtures = []
    for obj in module.__dict__.values():
        info = getattr(obj, "_pytest_fixture", None)
        if isinstance(info, _FixtureInfo) and info.autouse:
            fixtures.append(obj)
    return fixtures


def _iter_test_cases(module: ModuleType, fixtures: list[Callable]) -> Iterable[_TestCase]:
    for name, obj in module.__dict__.items():
        if not name.startswith("test_") or not callable(obj):
            continue
        param = getattr(obj, "_pytest_parametrize", None)
        if param:
            names, values = param
            for index, value in enumerate(values):
                if len(names) == 1:
                    args = (value[0],) if isinstance(value, (list, tuple)) else (value,)
                else:
                    if not isinstance(value, (list, tuple)):
                        raise AssertionError(
                            f"Parametrized data for {obj.__name__} must be sequence"
                        )
                    args = tuple(value)
                yield _TestCase(module, obj, fixtures, case_index=index, args=args, kwargs={})
        else:
            yield _TestCase(module, obj, fixtures, args=(), kwargs={})


def _run_fixture(func: Callable) -> Iterator | None:
    result = func()
    if inspect.isgenerator(result):
        try:
            next(result)
        except StopIteration:
            return None
        return result
    return None


def _finalize_fixture(generator: Iterator) -> None:
    try:
        next(generator)
    except StopIteration:
        return


def _run_test_case(case: _TestCase) -> tuple[bool, str | None]:
    finalizers: list[Iterator] = []
    try:
        for fixture_func in case.fixtures:
            gen = _run_fixture(fixture_func)
            if gen is not None:
                finalizers.append(gen)

        case.func(*case.args, **(case.kwargs or {}))
        return True, None
    except AssertionError as exc:
        return False, f"AssertionError: {exc}"
    except Exception as exc:
        tb = "".join(traceback.format_exception(exc.__class__, exc, exc.__traceback__))
        return False, tb
    finally:
        for gen in reversed(finalizers):
            _finalize_fixture(gen)


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    start_paths = args or ["tests"]

    cases: list[_TestCase] = []
    for path in _iter_test_files(start_paths):
        module = _import_module_from_path(path)
        fixtures = _collect_autouse_fixtures(module)
        cases.extend(list(_iter_test_cases(module, fixtures)))

    total = len(cases)
    failures = 0

    print(f"Collected {total} tests\n")
    for case in cases:
        success, info = _run_test_case(case)
        if success:
            print(f"✅ {case.name}")
        else:
            failures += 1
            print(f"❌ {case.name}")
            if info:
                print(info)

    print("\n==============================")
    print(f"TOTAL: {total}, PASSED: {total - failures}, FAILED: {failures}")
    print("==============================")
    return 0 if failures == 0 else 1
