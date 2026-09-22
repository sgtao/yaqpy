"""巨大な文書のデコード中でも中止・タイムアウトが効くこと（改修計画 5-4 節 U1）。

これまで ``StepBudget`` は評価ステップの境界でしか見られず、デコード中は効かなかった
（設計書 R4）。各デコーダの主要な走査ループに ``budget.tick()`` を入れたので、
デコードの途中で ``max_steps`` に達したら（＝中止・タイムアウトと同じ経路で）
即座に ``EvaluationLimitError`` になることを確かめる。1 文書ぶんの評価を待たずに
止まることが眼目なので、要素数は ``max_steps`` よりずっと多くしてある。
"""

from __future__ import annotations

import pytest

from yaqpy.core.engine.limits import StepBudget
from yaqpy.errors import EvaluationLimitError
from yaqpy.formats.csv_codec import CsvDecoder
from yaqpy.formats.json_codec import JsonDecoder
from yaqpy.formats.props_codec import PropertiesDecoder
from yaqpy.formats.toml_codec import TomlDecoder
from yaqpy.formats.toon_codec import ToonDecoder
from yaqpy.formats.xml_codec import XmlDecoder
from yaqpy.formats.yaml.codec import YamlDecoder
from yaqpy.options import Options

N = 2000        # budget の上限よりずっと多い件数
MAX_STEPS = 3


def _big_yaml_mapping() -> str:
    return "".join(f"key{i}: {i}\n" for i in range(N))


def _big_yaml_sequence() -> str:
    return "".join(f"- {i}\n" for i in range(N))


def _big_json_array() -> str:
    import json

    return json.dumps(list(range(N)))


def _big_csv() -> str:
    return "name\n" + "".join(f"item{i}\n" for i in range(N))


def _big_toml() -> str:
    return "".join(f"key{i} = {i}\n" for i in range(N))


def _big_props() -> str:
    return "".join(f"key{i}={i}\n" for i in range(N))


def _big_xml() -> str:
    items = "".join(f"<item>{i}</item>" for i in range(N))
    return f"<root>{items}</root>"


def _big_toon_object() -> str:
    return "".join(f"key{i}: {i}\n" for i in range(N))


CASES = (
    ("yaml (mapping)", lambda: YamlDecoder(Options()), _big_yaml_mapping),
    ("yaml (sequence)", lambda: YamlDecoder(Options()), _big_yaml_sequence),
    ("json", lambda: JsonDecoder(Options()), _big_json_array),
    ("csv", lambda: CsvDecoder(Options()), _big_csv),
    ("toml", lambda: TomlDecoder(Options()), _big_toml),
    ("props", lambda: PropertiesDecoder(Options()), _big_props),
    ("xml", lambda: XmlDecoder(Options()), _big_xml),
    ("toon", lambda: ToonDecoder(Options()), _big_toon_object),
)


class DecodeBudgetTests:
    @pytest.mark.parametrize("name,make_decoder,make_text", CASES, ids=[c[0] for c in CASES])
    def test_a_low_step_limit_stops_decoding_before_it_finishes(
        self, name: str, make_decoder, make_text) -> None:
        budget = StepBudget(max_steps=MAX_STEPS)
        with pytest.raises(EvaluationLimitError) as excinfo:
            list(make_decoder().decode_documents(make_text(), budget=budget))
        assert excinfo.value.limit == "max_steps"

    @pytest.mark.parametrize("name,make_decoder,make_text", CASES, ids=[c[0] for c in CASES])
    def test_cancelling_the_budget_stops_decoding(
        self, name: str, make_decoder, make_text) -> None:
        budget = StepBudget()
        budget.cancel()
        with pytest.raises(EvaluationLimitError) as excinfo:
            list(make_decoder().decode_documents(make_text(), budget=budget))
        assert excinfo.value.limit == "cancelled"

    @pytest.mark.parametrize("name,make_decoder,make_text", CASES, ids=[c[0] for c in CASES])
    def test_a_generous_budget_still_decodes_everything(
        self, name: str, make_decoder, make_text) -> None:
        budget = StepBudget(max_steps=1_000_000)
        docs = list(make_decoder().decode_documents(make_text(), budget=budget))
        assert docs

    @pytest.mark.parametrize("name,make_decoder,make_text", CASES, ids=[c[0] for c in CASES])
    def test_no_budget_means_no_behaviour_change(
        self, name: str, make_decoder, make_text) -> None:
        docs = list(make_decoder().decode_documents(make_text()))
        assert docs
