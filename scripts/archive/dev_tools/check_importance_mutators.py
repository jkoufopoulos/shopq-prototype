from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

MARKDOWN_PATH = Path("docs/importance_deciders.md")
PATTERN = re.compile(r"importance\s*=")


def allowed_files_from_doc() -> set[str]:
    allowed: set[str] = set()
    if not MARKDOWN_PATH.exists():
        return allowed

    for line in MARKDOWN_PATH.read_text(encoding="utf-8").splitlines():
        if "`" not in line:
            continue
        matches = re.findall(r"`([^`]+)`", line)
        for match in matches:
            path = match.split(":")[0]
            if path:
                allowed.add(str(Path(path).as_posix()))
    return allowed


def find_mutations() -> Iterable[tuple[str, int, str]]:
    from subprocess import run

    result = run(
        ["rg", "--line-number", "--no-heading", "importance\\s*=", "--glob", "*.py"],
        capture_output=True,
        text=True,
    )
    for line in result.stdout.strip().splitlines():
        if not line:
            continue
        path, line_num, content = line.split(":", 2)
        yield path, int(line_num), content.strip()


def main() -> int:
    allowed = allowed_files_from_doc()
    violations = []
    for path, line_num, content in find_mutations():
        normalized = Path(path).as_posix()
        if normalized not in allowed and not any(
            normalized.startswith(allowed_path) for allowed_path in allowed if allowed_path
        ):
            violations.append((normalized, line_num, content))

    if violations:
        print("Detected new importance mutators outside approved files:")
        for path, line_num, content in violations:
            print(f"  {path}:{line_num}: {content}")
        return 1

    print("Importance mutation guard passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
