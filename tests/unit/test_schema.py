"""schema 演算子：型の推論、必須キー、統合、format / enum、オプション、生成したスキーマで元データが通ること。"""

from __future__ import annotations

import io
import json
import random
import unittest
from pathlib import Path
from typing import Any

import yaqpy
from yaqpy import EvaluationLimitError, Options, SchemaOptions
from yaqpy.cli.main import main
from yaqpy.core.operators.schema import DIALECT, MAX_DEPTH
from tests.support.jsonschema_mini import check_structure, validate

DATA = Path(__file__).resolve().parent.parent / "data" / "testsets"


def schema_of(text: str, input_format: str = "yaml", expression: str = "schema", **schema: Any) -> Any:
    options = Options(input_format=input_format, output_format="json", indent=0,
                      schema=SchemaOptions(**schema))
    return json.loads(yaqpy.evaluate(expression, text, options=options))


def schema_all(texts: list[str], input_format: str = "yaml", **schema: Any) -> list[Any]:
    options = Options(input_format=input_format, output_format="json", indent=0,
                      schema=SchemaOptions(**schema))
    out = yaqpy.evaluate_all("schema", texts, options=options)
    return [json.loads(line) for line in out.splitlines() if line.strip()]


def body(schema: Any) -> Any:
    """The schema without its $schema line (easier to compare)."""
    return {k: v for k, v in schema.items() if k != "$schema"}


def run_cli(*argv: str) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    code = main(list(argv), stdout=out, stderr=err)
    return code, out.getvalue(), err.getvalue()


class TypeTests(unittest.TestCase):
    def test_the_dialect_is_named_once_at_the_top(self) -> None:
        schema = schema_of("a: {b: 1}\n")
        self.assertEqual(schema["$schema"], DIALECT)
        self.assertNotIn("$schema", schema["properties"]["a"])

    def test_scalar_types(self) -> None:
        schema = schema_of("s: x\ni: 1\nf: 1.5\nb: true\nn: null\nh: 0x1F\nd: 2001-12-14\n")
        types = {k: v["type"] for k, v in schema["properties"].items()}
        self.assertEqual(types, {"s": "string", "i": "integer", "f": "number", "b": "boolean",
                                 "n": "null", "h": "integer", "d": "string"})

    def test_a_top_level_scalar_and_null(self) -> None:
        self.assertEqual(body(schema_of("42\n")), {"type": "integer"})
        self.assertEqual(body(schema_of("null\n")), {"type": "null"})

    def test_quoted_numbers_are_strings(self) -> None:
        self.assertEqual(schema_of('a: "123"\n')["properties"]["a"], {"type": "string"})

    def test_empty_containers_say_nothing_about_their_content(self) -> None:
        schema = schema_of("a: []\nb: {}\n")
        self.assertEqual(schema["properties"], {"a": {"type": "array"}, "b": {"type": "object"}})
        self.assertEqual(schema["required"], ["a", "b"])

    def test_mixed_types_become_a_list_in_a_fixed_order(self) -> None:
        schema = schema_of("a: [x, 1, 2.5, true, null, [1], {k: 1}]\n")
        self.assertEqual(schema["properties"]["a"]["items"]["type"],
                         ["string", "number", "boolean", "object", "array", "null"])

    def test_integers_and_floats_together_are_number(self) -> None:
        self.assertEqual(schema_of("a: [1, 2]\n")["properties"]["a"]["items"], {"type": "integer"})
        self.assertEqual(schema_of("a: [1, 2.5]\n")["properties"]["a"]["items"], {"type": "number"})
        self.assertEqual(schema_of("a: [1.0, 2.5]\n")["properties"]["a"]["items"], {"type": "number"})

    def test_null_next_to_a_type(self) -> None:
        text = "- {a: x}\n- {a: null}\n"
        self.assertEqual(schema_of(text)["items"]["properties"]["a"], {"type": ["string", "null"]})

    def test_keywords_of_one_type_stay_next_to_the_others(self) -> None:
        schema = schema_of("- {k: 1}\n- [x]\n- text\n")
        self.assertEqual(body(schema["items"]), {
            "type": ["string", "object", "array"],
            "properties": {"k": {"type": "integer"}}, "required": ["k"],
            "items": {"type": "string"}})


class ObjectTests(unittest.TestCase):
    def test_properties_keep_the_order_of_first_appearance(self) -> None:
        self.assertEqual(list(schema_of("z: 1\na: 2\nm: 3\n")["properties"]), ["z", "a", "m"])

    def test_required_are_the_keys_every_sample_has(self) -> None:
        text = "- {a: 1, b: 2}\n- {a: 3}\n- {a: 4, c: 5}\n"
        schema = schema_of(text)["items"]
        self.assertEqual(list(schema["properties"]), ["a", "b", "c"])
        self.assertEqual(schema["required"], ["a"])

    def test_no_required_when_no_key_is_common(self) -> None:
        schema = schema_of("- {a: 1}\n- {b: 2}\n")["items"]
        self.assertNotIn("required", schema)

    def test_array_elements_are_merged_recursively(self) -> None:
        text = "items:\n  - {n: {x: 1}}\n  - {n: {x: 2, y: t}}\n"
        node = schema_of(text)["properties"]["items"]["items"]["properties"]["n"]
        self.assertEqual(node["properties"], {"x": {"type": "integer"}, "y": {"type": "string"}})
        self.assertEqual(node["required"], ["x"])

    def test_strict_closes_every_object(self) -> None:
        schema = schema_of("a: {b: 1}\nc: [{d: 1}]\n", strict=True)
        self.assertIs(schema["additionalProperties"], False)
        self.assertIs(schema["properties"]["a"]["additionalProperties"], False)
        self.assertIs(schema["properties"]["c"]["items"]["additionalProperties"], False)
        self.assertNotIn("additionalProperties", schema_of("a: {b: 1}\n"))

    def test_merge_keys_are_expanded_on_a_copy(self) -> None:
        text = "base: &b {x: 1}\nchild:\n  <<: *b\n  y: 2\n"
        schema = schema_of(text)
        self.assertEqual(list(schema["properties"]["child"]["properties"]), ["x", "y"])
        self.assertNotIn("<<", json.dumps(schema))

    def test_the_input_is_not_changed(self) -> None:
        options = Options(output_format="yaml")
        text = "base: &b {x: 1}\nchild:\n  <<: *b\n"
        out = yaqpy.evaluate('. as $d | ($d | schema) | ($d | .child | keys)', text, options=options)
        self.assertEqual(out, "- <<\n")


class StringTests(unittest.TestCase):
    def test_timestamps_get_a_format_when_all_agree(self) -> None:
        schema = schema_of("a: 2001-12-14T21:59:43Z\nb: 2001-12-14\nc: 2001-12-14t21:59:43.10-05:00\n")
        self.assertEqual(schema["properties"]["a"], {"type": "string", "format": "date-time"})
        self.assertEqual(schema["properties"]["b"], {"type": "string", "format": "date"})
        self.assertEqual(schema["properties"]["c"], {"type": "string", "format": "date-time"})

    def test_no_format_when_the_samples_differ(self) -> None:
        schema = schema_of("- 2001-12-14\n- 2001-12-14T21:59:43Z\n- plain\n")
        self.assertEqual(schema["items"], {"type": "string"})

    def test_enum_is_off_by_default(self) -> None:
        self.assertNotIn("enum", schema_of("- a\n- b\n- a\n")["items"])

    def test_enum_for_repeating_values(self) -> None:
        schema = schema_of("- a\n- b\n- a\n", enum_max=5)
        self.assertEqual(schema["items"], {"type": "string", "enum": ["a", "b"]})

    def test_enum_needs_a_repeated_value_and_a_small_set(self) -> None:
        self.assertNotIn("enum", schema_of("- a\n- b\n- c\n", enum_max=5)["items"])       # all different
        self.assertNotIn("enum", schema_of("- a\n- b\n- a\n- c\n", enum_max=2)["items"])   # too many
        self.assertNotIn("enum", schema_of("- a\n- 1\n- a\n", enum_max=5)["items"])         # not only strings

    def test_enum_tracking_gives_up_on_many_values(self) -> None:
        text = "".join(f"- v{i}\n- v{i}\n" for i in range(300))
        self.assertNotIn("enum", schema_of(text, enum_max=1000)["items"])


class MultipleNodesTests(unittest.TestCase):
    DOCS = ["a: 1\nb: x\n", "a: 2\nc: true\n"]

    def test_eval_all_merges_the_documents(self) -> None:
        (merged,) = schema_all(self.DOCS)
        self.assertEqual(list(merged["properties"]), ["a", "b", "c"])
        self.assertEqual(merged["required"], ["a"])

    def test_per_doc_gives_one_schema_each(self) -> None:
        schemas = schema_all(self.DOCS, per_doc=True)
        self.assertEqual([list(s["properties"]) for s in schemas], [["a", "b"], ["a", "c"]])

    def test_eval_gives_one_schema_per_document(self) -> None:
        options = Options(output_format="json", indent=0)
        out = yaqpy.evaluate("schema", "a: 1\n---\nb: x\n", options=options)
        self.assertEqual(len([ln for ln in out.splitlines() if ln.strip()]), 2)

    def test_it_can_sit_in_a_pipe(self) -> None:
        text = "items:\n  - {n: 1}\n  - {n: 2, m: x}\n"
        schema = schema_of(text, expression=".items[] | schema")
        self.assertEqual(schema["required"], ["n"])
        self.assertEqual(list(schema["properties"]), ["n", "m"])
        self.assertEqual(schema_of(text, expression=".items | schema")["type"], "array")

    def test_the_result_can_be_processed_further(self) -> None:
        options = Options(output_format="yaml", indent=0)
        self.assertEqual(yaqpy.evaluate("schema | .properties | keys | .[]", "a: 1\nb: 2\n",
                                        options=options), "a\nb\n")

    def test_nothing_in_nothing_out(self) -> None:
        options = Options(output_format="json")
        self.assertEqual(yaqpy.evaluate(".nothing[] | schema", "a: 1\n", options=options), "")

    def test_schema_is_a_key_name_too(self) -> None:
        text = "schema: 1\nx:\n  schema: y\n"
        options = Options(output_format="yaml")
        self.assertEqual(yaqpy.evaluate(".x.schema", text, options=options), "y\n")
        self.assertEqual(yaqpy.evaluate("{\"schema\": .schema}", text, options=options), "schema: 1\n")


class OutputTests(unittest.TestCase):
    def test_json_and_yaml_say_the_same(self) -> None:
        text = "a: 1\nb: [x, null]\nc: {d: 2001-12-14}\n"
        as_json = json.loads(yaqpy.evaluate("schema", text, options=Options(output_format="json")))
        as_yaml = yaqpy.evaluate("schema", text, options=Options(output_format="yaml"))
        self.assertEqual(json.loads(yaqpy.evaluate(".", as_yaml, options=Options(output_format="json"))),
                         as_json)

    def test_yaml_output_keeps_type_lists_on_one_line_and_quotes_null(self) -> None:
        out = yaqpy.evaluate("schema", "- {a: x}\n- {a: null}\n", options=Options(output_format="yaml"))
        self.assertIn('type: [string, "null"]', out)

    def test_other_formats(self) -> None:
        out = yaqpy.evaluate("schema", "a: 1\n", options=Options(output_format="toml"))
        self.assertIn('"$schema" = "https://json-schema.org/draft/2020-12/schema"', out)


class LimitTests(unittest.TestCase):
    def test_too_deep_data_is_refused_not_truncated(self) -> None:
        depth = MAX_DEPTH + 10
        text = '{"a":' * depth + "1" + "}" * depth
        with self.assertRaises(EvaluationLimitError):
            schema_of(text, input_format="json")

    def test_negative_enum_max(self) -> None:
        with self.assertRaises(ValueError):
            SchemaOptions(enum_max=-1)

    def test_step_limit_applies(self) -> None:
        from yaqpy import Limits

        text = "".join(f"- {{a: {i}}}\n" for i in range(200))
        options = Options(output_format="json", limits=Limits(max_steps=50))
        with self.assertRaises(yaqpy.EvaluationError):
            yaqpy.evaluate("schema", text, options=options)


class ValidityTests(unittest.TestCase):
    """The schema of some data must accept that data, and be a well-formed Draft 2020-12 schema."""

    def samples(self) -> list[tuple[str, list[str]]]:
        """(file name, its documents as JSON texts)."""
        out = []
        for path in sorted(DATA.glob("*")):
            fmt = "json" if path.suffix == ".json" else "yaml"
            text = path.read_text(encoding="utf-8")
            options = Options(input_format=fmt, output_format="json", indent=0)
            rendered = yaqpy.evaluate(".", text, options=options)
            docs = [ln for ln in rendered.splitlines() if ln.strip()]
            out.append((path.name, docs))
        return out

    def test_every_test_set_gets_a_schema_that_accepts_it(self) -> None:
        checked = 0
        for name, docs in self.samples():
            with self.subTest(name=name):
                options = Options(input_format="json", output_format="json", indent=0)
                merged = json.loads(yaqpy.evaluate_all("schema", docs, options=options)) if docs else None
                if merged is None:
                    continue
                self.assertEqual(check_structure(merged), [])
                for doc in docs:
                    self.assertEqual(validate(json.loads(doc), merged), [], f"{name}: {doc[:80]}")
                checked += 1
        self.assertGreaterEqual(checked, 9)

    def test_each_test_set_file_gives_a_schema_from_the_cli(self) -> None:
        files = sorted(DATA.glob("*"))
        self.assertEqual(len(files), 10)
        for path in files:
            with self.subTest(name=path.name):
                code, out, err = run_cli("--schema", "-o", "json", "-I", "0", str(path))
                self.assertEqual((code, err), (0, ""))
                for line in out.splitlines():
                    self.assertEqual(json.loads(line)["$schema"], DIALECT)

    def test_data_that_does_not_fit_is_rejected(self) -> None:
        schema = schema_of("a: 1\nb: [x]\nc: {d: true}\n", strict=True)
        for bad in ({"a": "1", "b": ["x"], "c": {"d": True}}, {"a": 1, "b": [1], "c": {"d": True}},
                    {"a": 1, "b": ["x"], "c": {"d": True}, "extra": 1}, {"a": 1, "b": ["x"]},
                    {"a": 1, "b": ["x"], "c": {"d": "yes"}}):
            with self.subTest(bad=bad):
                self.assertNotEqual(validate(bad, schema), [])

    def test_random_data_validates_against_its_own_schema(self) -> None:
        rng = random.Random(20260921)

        def value(depth: int) -> Any:
            kinds = ["str", "int", "float", "bool", "null"] + (["obj", "arr"] if depth < 4 else [])
            kind = rng.choice(kinds)
            if kind == "str":
                return rng.choice(["a", "b", "c", "x y", "", "2001-12-14", "日本語"])
            if kind == "int":
                return rng.randint(-5, 5)
            if kind == "float":
                return rng.choice([0.5, 2.0, -1.25])
            if kind == "bool":
                return rng.random() < 0.5
            if kind == "null":
                return None
            if kind == "arr":
                return [value(depth + 1) for _ in range(rng.randint(0, 4))]
            return {rng.choice("abcdef"): value(depth + 1) for _ in range(rng.randint(0, 4))}

        for round_ in range(40):
            docs = [json.dumps({"k": value(0), "j": value(0)}) for _ in range(rng.randint(1, 4))]
            for strict in (False, True):
                with self.subTest(round=round_, strict=strict):
                    options = Options(input_format="json", output_format="json", indent=0,
                                      schema=SchemaOptions(strict=strict, enum_max=3))
                    merged = json.loads(yaqpy.evaluate_all("schema", docs, options=options))
                    self.assertEqual(check_structure(merged), [], docs)
                    for doc in docs:
                        self.assertEqual(validate(json.loads(doc), merged), [], f"{docs} / {merged}")


class CliTests(unittest.TestCase):
    def write(self, name: str, text: str) -> str:
        import os
        import tempfile

        directory = tempfile.mkdtemp()
        self.addCleanup(lambda: __import__("shutil").rmtree(directory, ignore_errors=True))
        path = os.path.join(directory, name)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        return path

    def test_the_short_flag_is_the_operator(self) -> None:
        path = self.write("a.yaml", "a: 1\n")
        code, short, _ = run_cli("--schema", path)
        code2, long, _ = run_cli("schema", path)
        self.assertEqual((code, code2), (0, 0))
        self.assertEqual(short, long)

    def test_the_flag_can_follow_an_expression(self) -> None:
        path = self.write("a.yaml", "a: {b: 1}\n")
        code, out, _ = run_cli("--schema", "-o", "json", "-I", "0", ".a", path)
        self.assertEqual(json.loads(out)["required"], ["b"])

    def test_output_follows_the_input_format_or_o(self) -> None:
        path = self.write("a.json", '{"a": 1}')
        code, out, _ = run_cli("--schema", "-I", "0", path)
        self.assertEqual(json.loads(out)["type"], "object")
        code, out, _ = run_cli("--schema", "-o", "yaml", path)
        self.assertTrue(out.startswith("$schema: "))

    def test_option_flags(self) -> None:
        path = self.write("a.yaml", "- {k: a}\n- {k: a}\n- {k: b}\n")
        code, out, _ = run_cli("--schema", "--schema-strict", "--schema-enum-max", "3", "-o", "json",
                               "-I", "0", path)
        schema = json.loads(out)
        self.assertIs(schema["items"]["additionalProperties"], False)
        self.assertEqual(schema["items"]["properties"]["k"]["enum"], ["a", "b"])

    def test_per_doc_flag_with_eval_all(self) -> None:
        path = self.write("a.yaml", "a: 1\n---\nb: 2\n")
        code, out, _ = run_cli("ea", "--schema-per-doc", "schema", "-o", "json", "-I", "0", path)
        self.assertEqual(len([ln for ln in out.splitlines() if ln.strip()]), 2)
        code, out, _ = run_cli("ea", "schema", "-o", "json", "-I", "0", path)
        self.assertEqual(len([ln for ln in out.splitlines() if ln.strip()]), 1)

    def test_negative_enum_max_is_an_error(self) -> None:
        path = self.write("a.yaml", "a: 1\n")
        code, _, err = run_cli("--schema", "--schema-enum-max=-1", path)
        self.assertEqual(code, 1)
        self.assertIn("must not be negative", err)

    def test_help_documents_the_flags(self) -> None:
        from yaqpy.cli.parser import build_parser

        text = build_parser().format_help()
        for flag in ("--schema ", "--schema-strict", "--schema-enum-max", "--schema-per-doc"):
            self.assertIn(flag, text)


if __name__ == "__main__":
    unittest.main()
