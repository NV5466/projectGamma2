from __future__ import annotations

import re
import subprocess
import sys


BLOCKED_PATTERNS = [
    re.compile(r"(^|/)__pycache__/"),
    re.compile(r"\.pyc$"),
    re.compile(r"\.pyo$"),
    re.compile(r"\.pyd$"),
    re.compile(r"(^|/)\.pytest_cache/"),
]


def main() -> int:
    result = subprocess.run(
        ["git", "ls-files"],
        check=True,
        capture_output=True,
        text=True,
    )
    tracked = [line.strip().replace("\\", "/") for line in result.stdout.splitlines() if line.strip()]
    bad = [path for path in tracked if any(pattern.search(path) for pattern in BLOCKED_PATTERNS)]
    if bad:
        print("Generated/local Python artifacts are tracked:", file=sys.stderr)
        for path in bad:
            print(f"  {path}", file=sys.stderr)
        return 1
    print("repo hygiene ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
