"""互換テスト（形式）：Go 版の形式シナリオ（XML・CSV/TSV・TOML・properties）を実行する。

まだ実装していない形式は skip として数えるので、このテストは「実装済みの形式が壊れたとき」だけ失敗する。
既知の非互換は ``formats_manifest.json`` に記録する（``tools/golden_report.py --write-formats`` で更新）。
形式ごとの最低合格率は ``MIN_PASS_RATE`` に書き、形式を実装したフェーズで引き上げる。
"""

from __future__ import annotations

import json
import unittest
from pathlib import Path

from tests.support.golden import Outcome
from tests.support.golden_formats import (
    FORMAT_FILES, load_format_scenarios, run_format_scenario, summarize_formats,
)

MANIFEST = Path(__file__).resolve().parent / "formats_manifest.json"

# 形式を実装したフェーズで引き上げる（合格率 = 完全一致＋意味的に一致 ÷ 実行できたシナリオ）。
MIN_PASS_RATE: dict[str, float] = {}


def _known_failures() -> set[str]:
    """Scenario ids recorded in formats_manifest.json as known non-compatibilities."""
    if not MANIFEST.exists():
        return set()
    data = json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {sid for sid, info in data.get("scenarios", {}).items()
            if info.get("status") in ("fail", "error")}


class GoldenFormatTests(unittest.TestCase):
    scenarios = load_format_scenarios()
    known = _known_failures()

    def test_scenarios(self) -> None:
        outcomes: list[Outcome] = []
        for scenario in self.scenarios:
            outcome = run_format_scenario(scenario)
            outcomes.append(outcome)
            with self.subTest(id=outcome.id):
                if outcome.status in ("unsupported", "unresolved", "skipped"):
                    self.skipTest(outcome.detail)
                if outcome.status in ("fail", "error") and outcome.id in self.known:
                    self.skipTest("known non-compatibility: " + outcome.detail)
                self.assertIn(outcome.status, ("exact", "semantic"),
                              f"{outcome.id}: {outcome.detail}\nexpected={outcome.expected}\n"
                              f"actual={outcome.actual}")
        summary = summarize_formats(outcomes)
        for name, minimum in MIN_PASS_RATE.items():
            rate = summary[name]["pass_rate"]
            self.assertIsNotNone(rate, f"{name}: no scenario could run")
            self.assertGreaterEqual(rate, minimum,
                                    f"{name} pass rate is below {minimum:.0%}: {summary[name]}")

    def test_every_format_file_is_present(self) -> None:
        sources = {s["source"][:-len("_test.go")] for s in self.scenarios}
        self.assertEqual(sources, set(FORMAT_FILES))

    def test_every_scenario_type_is_known(self) -> None:
        unknown = [s["id"] for s in self.scenarios
                   if run_format_scenario(s).detail.startswith("unknown scenario type")]
        self.assertEqual(unknown, [])


if __name__ == "__main__":
    unittest.main()
