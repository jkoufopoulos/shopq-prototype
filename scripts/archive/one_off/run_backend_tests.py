#!/usr/bin/env python3
"""Backend test runner with offline fallback.

Tries to invoke real pytest. If unavailable, falls back to a minimal
pytest-compatible runner implemented in tests/_mini_pytest.py.
"""

from __future__ import annotations

import importlib
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]

    try:
        pytest = importlib.import_module("pytest")
        print("Using system pytest")
        return pytest.main(args)
    except ModuleNotFoundError:
        from tests import _mini_pytest

        # Register stub so imports inside tests succeed
        sys.modules.setdefault("pytest", _mini_pytest)
        print("pytest not available; using minimal fallback runner")
        return _mini_pytest.main(args)


if __name__ == "__main__":
    sys.exit(main())
