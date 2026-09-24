"""Run the test suite on every supported Python (and check the minimum version of the source).

    uv run python tools/check_pythons.py                 # 3.11 / 3.12 / 3.13, the whole suite
    uv run python tools/check_pythons.py 3.11            # only one version
    uv run python tools/check_pythons.py --quick         # only tests/acceptance (the examples/ conversions)

Each version gets its own environment (``.venv-py3.11`` ...), so the development ``.venv`` is left alone.
The versions are downloaded by uv when needed. Python 3.11 is the floor: ``requires-python`` in
pyproject.toml must say the same.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VERSIONS = ["3.11", "3.12", "3.13"]
FLOOR = VERSIONS[0]


def run(cmd: list[str], env: dict[str, str] | None = None) -> int:
    print("$", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=ROOT, env=env).returncode


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("versions", nargs="*", default=VERSIONS, help=f"default: {' '.join(VERSIONS)}")
    ap.add_argument("--quick", action="store_true", help="run tests/acceptance only")
    ap.add_argument("--no-gui", action="store_true", help="do not install the gui extra (Flet)")
    args = ap.parse_args()

    results: list[tuple[str, str, float]] = []

    # 1. The syntax floor: no construct newer than FLOOR may appear in src/ (fast; needs no run).
    t = time.time()
    rc = run(["uvx", "vermin", "--no-tips", f"-t={FLOOR}-", "--eval-annotations", "src"])
    results.append((f"vermin >= {FLOOR}", "ok" if rc == 0 else "FAILED", time.time() - t))

    for version in args.versions:
        t = time.time()
        env = dict(os.environ, UV_PROJECT_ENVIRONMENT=str(ROOT / f".venv-py{version}"))
        cmd = ["uv", "run", "--python", version]
        if not args.no_gui:
            cmd += ["--extra", "gui"]
        cmd += ["pytest", "-q", "-n", "4", "-p", "no:cacheprovider"]
        if args.quick:
            cmd.append("tests/acceptance")
        rc = run(cmd, env)
        results.append((f"pytest on Python {version}", "ok" if rc == 0 else "FAILED", time.time() - t))

    print("\n== summary ==")
    for name, state, sec in results:
        print(f"{state:>7}  {name}  ({sec:.0f}s)")
    return 0 if all(state == "ok" for _, state, _ in results) else 1


if __name__ == "__main__":
    sys.exit(main())
