"""Node / tags / convert tests (design doc 5)."""

from __future__ import annotations

import pytest
from yaqpy.core.model import Kind, Node, Style, from_python, to_python
from yaqpy.core.model import tags
from yaqpy.core.model.datetime_util import format_datetime, parse_datetime, parse_go_duration


class TagTests:
    def test_core_schema(self) -> None:
        cases = {
            "": "!!null", "~": "!!null", "null": "!!null", "NULL": "!!null",
            "true": "!!bool", "False": "!!bool", "yes": "!!str", "on": "!!str",
            "12": "!!int", "-3": "!!int", "0x1F": "!!int", "0o17": "!!int", "1_000": "!!int",
            "1.5": "!!float", ".5": "!!float", "1e3": "!!float", ".inf": "!!float", "-.Inf": "!!float",
            ".nan": "!!float", "1.": "!!float",
            "hello": "!!str", "1.2.3": "!!str", "0x": "!!str", "+": "!!str",
        }
        for text, tag in cases.items():
            assert tags.resolve_plain(text) == tag

    def test_parse_int_keeps_base(self) -> None:
        assert tags.parse_int("0x1F") == ("hex", 31)
        assert tags.parse_int("0o17") == ("oct", 15)
        assert tags.parse_int("1_000") == ("dec", 1000)
        assert tags.format_int("hex", 32) == "0x20"

    def test_format_float_like_go(self) -> None:
        assert tags.format_float(3.5) == "3.5"
        assert tags.format_float(6.0) == "6"
        assert tags.format_float(1000000.0) == "1e+06"
        assert tags.format_float(123456.0) == "123456"
        assert tags.format_float(0.00001) == "1e-05"
        assert tags.format_float(0.0001) == "0.0001"
        assert tags.format_float(float("inf")) == "+Inf"


class NodeTests:
    def test_path_and_nice_path(self) -> None:
        root = Node.mapping()
        seq = Node.sequence()
        seq.add_child(Node.string("x"))
        root.add_key_value(Node.string("a"), seq)
        item = root.content[1].content[0]
        assert item.path() == ["a", 0]
        assert item.nice_path() == "a[0]"

    def test_update_from_keeps_comments_and_style(self) -> None:
        target = Node.scalar("1", "!!int", line_comment="# keep")
        target.style = Style.DOUBLE_QUOTED
        target.update_from(Node.scalar("2", "!!int"))
        assert target.value == "2"
        assert target.line_comment == "# keep"
        assert target.style == Style.DOUBLE_QUOTED
        # tag change resets style
        target.update_from(Node.string("x"))
        assert target.style == Style.NONE

    def test_custom_tag_not_clobbered(self) -> None:
        target = Node.scalar("1", "!custom")
        target.update_from(Node.scalar("2", "!!int"))
        assert target.tag == "!custom"
        target.update_from(Node.scalar("3", "!!int"), clobber_custom_tags=True)
        assert target.tag == "!!int"

    def test_deep_equal(self) -> None:
        a = from_python({"x": [1, 2, {"y": None}]})
        b = from_python({"x": [1, 2, {"y": None}]})
        assert a.deep_equal(b)
        assert not a.deep_equal(from_python({"x": [1, 2]}))

    def test_alias_cycle_detected(self) -> None:
        a = Node(Kind.ALIAS, value="a")
        b = Node(Kind.ALIAS, value="b", alias=a)
        a.alias = b
        with pytest.raises(Exception):
            a.resolve_alias()

    def test_truthy(self) -> None:
        assert not Node.null().is_truthy()
        assert not Node.boolean(False).is_truthy()
        assert Node.string("").is_truthy()
        assert Node.mapping().is_truthy()


class ConvertTests:
    def test_round_trip(self) -> None:
        data = {"a": [1, 2.5, "x", True, None], "b": {"c": "123"}}
        assert to_python(from_python(data)) == data

    def test_string_that_looks_like_number_is_quoted(self) -> None:
        node = from_python("123")
        assert node.tag == "!!str"
        assert node.style == Style.DOUBLE_QUOTED


class DateTimeTests:
    def test_parse_and_format(self) -> None:
        dt = parse_datetime("2006-01-02T15:04:05Z07:00", "2021-01-01T00:00:00Z")
        assert format_datetime(dt) == "2021-01-01T00:00:00Z"
        dt = parse_datetime("2006-01-02T15:04:05Z07:00", "2021-01-01")
        assert format_datetime(dt + parse_go_duration("24h")) == "2021-01-02T00:00:00Z"

    def test_go_duration(self) -> None:
        assert parse_go_duration("3h10m").total_seconds() == 11400
        assert parse_go_duration("-1.5h").total_seconds() == -5400
        assert parse_go_duration("300ms").total_seconds() == 0.3
        with pytest.raises(ValueError):
            parse_go_duration("3 hours")
