"""プロパティ候補の抽出テスト（GUI 設計書 6-3-2 / 9-2 の T1〜T4）。"""

from __future__ import annotations

import pytest
import yaqpy
from yaqpy.gui.paths import PathCandidate, collect_paths, format_key

SAMPLE = (
    "# サーバー設定\n"
    "server:\n"
    "  port: 8080 # 開発用\n"
    "  hosts: [a, b]\n"
    "  tls: &tls\n"
    "    enabled: true\n"
    "    cert: /etc/cert.pem\n"
    "backup:\n"
    "  <<: *tls\n"
    '  schedule: "0 3 * * *"\n'
    "items:\n"
    "  - name: pen\n"
    "    price: 120\n"
    "  - name: book\n"
    "    price: 980\n"
)

EXPECTED = [
    (".server", "map", "", 1),
    (".server.port", "scalar", "8080", 2),
    (".server.hosts", "seq", "", 2),
    (".server.hosts[]", "scalar", "a", 3),
    (".server.tls", "map", "", 2),
    (".server.tls.enabled", "scalar", "true", 3),
    (".server.tls.cert", "scalar", "/etc/cert.pem", 3),
    (".backup", "map", "", 1),
    (".backup.schedule", "scalar", "0 3 * * *", 2),
    (".items", "seq", "", 1),
    (".items[]", "map", "", 2),
    (".items[].name", "scalar", "pen", 3),
    (".items[].price", "scalar", "120", 3),
]


def paths(text: str, **kwargs) -> list[PathCandidate]:
    return collect_paths(yaqpy.load(text), **kwargs)


class CollectPathsTests:
    def test_sample_document(self) -> None:
        got = [(c.expression, c.kind, c.sample, c.depth) for c in paths(SAMPLE)]
        assert got == EXPECTED

    @pytest.mark.parametrize("candidate", paths(SAMPLE))
    def test_every_candidate_is_a_valid_expression(self, candidate) -> None:
        """作った候補がそのまま実行できること（プルダウンの価値そのもの）。"""
        yaqpy.evaluate(candidate.expression, SAMPLE)

    def test_merge_key_is_skipped(self) -> None:
        expressions = [c.expression for c in paths(SAMPLE)]
        assert '.["<<"]' not in expressions
        assert ".backup.<<" not in expressions

    def test_alias_is_not_traversed(self) -> None:
        got = [c.expression for c in paths("x: &a\n  p: 1\ny: *a\n")]
        assert got == [".x", ".x.p", ".y"]   # .y.p は作らない

    def test_alias_candidate_kind(self) -> None:
        by_expr = {c.expression: c for c in paths("x: &a\n  p: 1\ny: *a\n")}
        assert by_expr[".y"].kind == "alias"

    def test_sequence_is_collapsed(self) -> None:
        expressions = [c.expression for c in paths(SAMPLE)]
        assert ".items[].name" in expressions
        assert ".items[0].name" not in expressions
        assert expressions.count(".items[].name") == 1

    def test_empty_sequence(self) -> None:
        assert [c.expression for c in paths("a: []\n")] == [".a"]

    def test_empty_document(self) -> None:
        assert paths("") == []

    def test_scalar_document(self) -> None:
        assert paths("just a string\n") == []

    def test_multiple_documents_are_merged(self) -> None:
        assert [c.expression for c in paths("a: 1\n---\nb: 2\n")] == [".a", ".b"]

    def test_max_depth(self) -> None:
        deep = "".join(f"{'  ' * i}k{i}:\n" for i in range(10)) + "  " * 10 + "leaf: 1\n"
        assert [c.expression for c in paths(deep, max_depth=3)] == [".k0", ".k0.k1", ".k0.k1.k2"]

    def test_max_items(self) -> None:
        got = paths(SAMPLE, max_items=3)
        assert [c.expression for c in got] == [".server", ".server.port", ".server.hosts"]

    def test_sample_is_truncated(self) -> None:
        long_value = "x" * 100
        candidate = paths(f"a: {long_value}\n")[0]
        assert len(candidate.sample) == 40
        assert candidate.sample.endswith("…")

    def test_label(self) -> None:
        by_expr = {c.expression: c for c in paths(SAMPLE)}
        assert by_expr[".server.port"].label == ".server.port  = 8080"
        assert by_expr[".items"].label == ".items  (seq)"


class FormatKeyTests:
    def test_bare_keys(self) -> None:
        assert format_key("server") == ".server"
        assert format_key("with-dash") == ".with-dash"
        assert format_key("_private") == "._private"
        assert format_key("select") == ".select"   # 演算子名でも素のままで通る

    def test_quoted_keys(self) -> None:
        assert format_key("my key") == '.["my key"]'
        assert format_key("9num") == '.["9num"]'
        assert format_key("a.b") == '.["a.b"]'
        assert format_key("") == '.[""]'

    def test_quotes_are_escaped(self) -> None:
        assert format_key('a"b') == '.["a\\"b"]'
        assert format_key("a\\b") == '.["a\\\\b"]'

    def test_quoted_keys_actually_work(self) -> None:
        document = 'my key: 1\n9num: 2\n'
        assert yaqpy.evaluate(format_key("my key"), document) == "1\n"
        assert yaqpy.evaluate(format_key("9num"), document) == "2\n"
