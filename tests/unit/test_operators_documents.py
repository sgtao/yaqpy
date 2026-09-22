"""split_doc：一致した節点ごとに別の文書にする。"""

from __future__ import annotations

import yaqpy
from yaqpy import Options


class SplitDocTests:
    def test_each_result_gets_a_separator(self) -> None:
        out = yaqpy.evaluate(".[] | split_doc", "[{a: cat}, {b: dog}]")
        assert out == "{a: cat}\n---\n{b: dog}\n"

    def test_without_separators_when_asked(self) -> None:
        options = Options(yaml=Options().yaml.__class__(print_doc_separators=False))
        out = yaqpy.evaluate(".[] | split_doc", "[{a: cat}, {b: dog}]", options=options)
        assert out == "{a: cat}\n{b: dog}\n"

    def test_document_index(self) -> None:
        out = yaqpy.evaluate(".[] | split_doc | document_index", "[a, b, c]")
        assert out.split() == ["0", "1", "2"]

    def test_a_single_result_stays_in_document_zero(self) -> None:
        assert yaqpy.evaluate("split_doc | document_index", "a: 1").strip() == "0"
