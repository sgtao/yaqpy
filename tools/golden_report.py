"""Run the golden scenarios and print a pass-rate report.

Usage:
    uv run python tools/golden_report.py [--fails] [--file operator_add] [--write tests/golden/manifest.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from tests.support.golden import MVP_FILES, load_scenarios, run_scenario, summarize  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fails", action="store_true", help="print failing scenarios")
    ap.add_argument("--file", default="", help="only scenarios from this Go test file (without _test.go)")
    ap.add_argument("--write", default="", help="write the manifest JSON to this path")
    ap.add_argument("--mvp-only", action="store_true")
    args = ap.parse_args()

    scenarios = load_scenarios()
    if args.file:
        scenarios = [s for s in scenarios if s["source"] == args.file + "_test.go"]
    if args.mvp_only:
        scenarios = [s for s in scenarios if s["source"][:-len("_test.go")] in MVP_FILES]
    outcomes = [run_scenario(s) for s in scenarios]
    summary = summarize(outcomes)

    by_file: dict[str, dict[str, int]] = {}
    for o in outcomes:
        counts = by_file.setdefault(o.source, {})
        counts[o.status] = counts.get(o.status, 0) + 1
    print(f"{'file':40} {'exact':>6} {'sem':>5} {'fail':>5} {'err':>5} {'unsup':>6} {'other':>6}")
    for name, counts in sorted(by_file.items()):
        other = counts.get("unresolved", 0) + counts.get("skipped", 0)
        mark = "*" if name[:-len("_test.go")] in MVP_FILES else " "
        print(f"{mark}{name:39} {counts.get('exact', 0):6} {counts.get('semantic', 0):5} "
              f"{counts.get('fail', 0):5} {counts.get('error', 0):5} {counts.get('unsupported', 0):6} {other:6}")
    print()
    print(f"MVP  scenarios: {summary['mvp']['total']:4}  pass rate {summary['mvp']['pass_rate']:.1%}  {summary['mvp']['counts']}")
    print(f"ALL  scenarios: {summary['all']['total']:4}  pass rate {summary['all']['pass_rate']:.1%}  {summary['all']['counts']}")

    if args.fails:
        for o in outcomes:
            if o.status in ("fail", "error"):
                print("-" * 70)
                print(f"{o.status.upper()} {o.id}: {o.detail}")
                if o.expected is not None:
                    print("expected:", json.dumps(o.expected, ensure_ascii=False))
                if o.actual is not None:
                    print("actual:  ", json.dumps(o.actual, ensure_ascii=False))
    if args.write:
        manifest = {
            "summary": summary,
            "scenarios": {o.id: {"status": o.status, "detail": o.detail} for o in outcomes},
        }
        Path(args.write).write_text(json.dumps(manifest, ensure_ascii=False, indent=1) + "\n",
                                    encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
