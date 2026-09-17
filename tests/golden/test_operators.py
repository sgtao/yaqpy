"""Compatibility tests: the Go yq scenarios extracted into tests/golden/operators/.

Scenarios for operators that are not implemented yet are reported as skipped,
so this file only fails when an *implemented* operator regresses.
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests.support.golden import MVP_FILES, load_scenarios, run_scenario, summarize

MANIFEST = Path(__file__).resolve().parent / "manifest.json"


def _known_failures() -> set[str]:
    """Scenario ids recorded in manifest.json as known non-compatibilities."""
    if not MANIFEST.exists():
        return set()
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {sid for sid, info in data.get("scenarios", {}).items()
            if info.get("status") in ("fail", "error")}


class GoldenOperatorTests(unittest.TestCase):
    scenarios = load_scenarios()
    known = _known_failures()

    def test_scenarios(self) -> None:
        outcomes = []
        for scenario in self.scenarios:
            outcome = run_scenario(scenario)
            outcomes.append(outcome)
            with self.subTest(id=outcome.id):
                if outcome.status in ("unsupported", "unresolved", "skipped"):
                    self.skipTest(outcome.detail)
                if outcome.status in ("fail", "error") and outcome.id in self.known:
                    self.skipTest("known non-compatibility: " + outcome.detail)
                self.assertIn(outcome.status, ("exact", "semantic"),
                              f"{outcome.id}: {outcome.detail}\nexpected={outcome.expected}\n"
                              f"actual={outcome.actual}")
        summary = summarize(outcomes)
        self.assertGreaterEqual(summary["mvp"]["pass_rate"], 0.90,
                                f"MVP pass rate below the phase 1 exit bar: {summary['mvp']}")

    def test_mvp_files_exist(self) -> None:
        sources = {s["source"][:-len("_test.go")] for s in self.scenarios}
        missing = MVP_FILES - sources
        self.assertFalse(missing, f"golden files missing for {sorted(missing)}")


if __name__ == "__main__":
    unittest.main()
