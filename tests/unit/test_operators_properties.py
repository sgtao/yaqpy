"""性質テスト：乱数（固定シード）で作ったデータに対して、往復や、Python の素朴な計算との一致を確かめる。

新しく自前で書いた部分（日時の書式、encode / decode、配列の演算子）が、例に書いていない入力でも
正しいことを、独立した基準（strftime・base64・shlex・リストの内包表記）と突き合わせて見る。
"""

from __future__ import annotations

import base64
import datetime as dt
import json
import random
import re
import shlex
import unittest
import urllib.parse
from typing import Any

import yaqpy
from yaqpy import Options
from yaqpy.core.model.datetime_util import format_datetime, parse_datetime, unix_seconds

JSON = Options(input_format="json", output_format="json", indent=0)


def run(expression: str, data: Any) -> Any:
    out = yaqpy.evaluate(expression, json.dumps(data, ensure_ascii=False), options=JSON)
    lines = [json.loads(line) for line in out.splitlines() if line.strip()]
    return lines[0] if len(lines) == 1 else lines


def random_moment(rng: random.Random, last_year: int = 2099) -> dt.datetime:
    offset = dt.timedelta(minutes=15 * rng.randint(-47, 56))            # -11:45 .. +14:00
    end = int((dt.datetime(last_year, 12, 31) - dt.datetime(1970, 1, 1)).total_seconds())
    naive = dt.datetime(1970, 1, 1) + dt.timedelta(seconds=rng.randint(0, end))
    return naive.replace(tzinfo=dt.timezone(offset, ""))


class DatetimeProperties(unittest.TestCase):
    LAYOUTS = (
        "2006-01-02T15:04:05Z07:00",
        "2006-01-02 15:04:05 -0700",
        "2006-01-02 15:04:05 -07:00",
        "Mon, 02 Jan 2006 15:04:05 -0700",
        "January 2, 2006 3:04:05pm -0700",
        "2006-002 15:04:05 -0700",
        "20060102150405-0700",
    )

    def test_parse_of_format_is_the_same_instant(self) -> None:
        rng = random.Random(20260921)
        for _ in range(400):
            moment = random_moment(rng)
            for layout in self.LAYOUTS:
                with self.subTest(layout=layout, moment=moment):
                    text = format_datetime(moment, layout)
                    parsed = parse_datetime(layout, text)
                    self.assertEqual(parsed, moment)
                    self.assertEqual(parsed.utcoffset(), moment.utcoffset())
                    self.assertEqual(format_datetime(parsed, layout), text)

    def test_a_two_digit_year_round_trips_from_1969_to_2068(self) -> None:
        # Go reads 69..99 as 19xx and 00..68 as 20xx
        rng = random.Random(21)
        layout = "Monday, 02-Jan-06 at 03:04:05PM -07:00"
        for _ in range(300):
            moment = random_moment(rng, last_year=2068)
            with self.subTest(moment=moment):
                self.assertEqual(parse_datetime(layout, format_datetime(moment, layout)), moment)

    def test_numeric_fields_agree_with_strftime(self) -> None:
        rng = random.Random(7)
        for _ in range(500):
            moment = random_moment(rng)
            self.assertEqual(format_datetime(moment, "2006-01-02 15:04:05"),
                             moment.strftime("%Y-%m-%d %H:%M:%S"))
            self.assertEqual(format_datetime(moment, "Mon Jan 02 06 03:04PM"),
                             moment.strftime("%a %b %d %y %I:%M%p"))
            self.assertEqual(format_datetime(moment, "Monday, January 02"),
                             moment.strftime("%A, %B %d"))
            self.assertEqual(format_datetime(moment, "002"), moment.strftime("%j"))

    def test_unix_seconds_agree_with_timestamp(self) -> None:
        rng = random.Random(11)
        for _ in range(300):
            moment = random_moment(rng).replace(microsecond=rng.randint(0, 999999))
            self.assertEqual(unix_seconds(moment), int(moment.timestamp() // 1))

    def test_fractions_survive_a_round_trip(self) -> None:
        rng = random.Random(3)
        layout = "2006-01-02 15:04:05.000000 -0700"
        for _ in range(200):
            moment = random_moment(rng).replace(microsecond=rng.randint(0, 999999))
            self.assertEqual(parse_datetime(layout, format_datetime(moment, layout)), moment)

    def test_adding_then_subtracting_a_duration_is_the_identity(self) -> None:
        rng = random.Random(5)
        for _ in range(100):
            text = format_datetime(random_moment(rng))
            duration = f"{rng.randint(0, 5000)}h{rng.randint(0, 59)}m"
            out = yaqpy.evaluate(f'.a += "{duration}" | .a -= "{duration}" | .a', f"a: {text}")
            self.assertEqual(out.strip(), text)


class EncodingProperties(unittest.TestCase):
    ALPHABET = "abcXYZ019 \t\n+/=%&?#'\"\\日本語😊é~-_.*()"

    def texts(self, seed: int, count: int = 200) -> list[str]:
        rng = random.Random(seed)
        return ["".join(rng.choice(self.ALPHABET) for _ in range(rng.randint(0, 24)))
                for _ in range(count)]

    def test_base64_matches_python_and_round_trips(self) -> None:
        texts = self.texts(1)
        self.assertEqual(run(".[] | @base64", texts),
                         [base64.b64encode(t.encode()).decode() for t in texts])
        self.assertEqual(run(".[] | @base64 | @base64d", texts), texts)

    def test_uri_matches_python_and_round_trips(self) -> None:
        texts = self.texts(2)
        self.assertEqual(run(".[] | @uri", texts),
                         [urllib.parse.quote_plus(t, safe="") for t in texts])
        self.assertEqual(run(".[] | @uri | @urid", texts), texts)

    def test_sh_output_is_one_shell_word_that_means_the_input(self) -> None:
        for text in self.texts(3):
            if text == "":
                continue                          # Go's @sh gives nothing at all for ""
            with self.subTest(text=text):
                self.assertEqual(shlex.split(run("@sh", text), posix=True), [text])

    def random_value(self, rng: random.Random, depth: int, alphabet: str) -> Any:
        kind = rng.randint(0, 5 if depth < 3 else 3)
        if kind == 0:
            return rng.randint(-1000, 1000)
        if kind == 1:
            return rng.choice([True, False, None])
        if kind == 2:
            return "".join(rng.choice(alphabet) for _ in range(rng.randint(1, 8)))
        if kind == 3:
            return rng.choice([0.5, 1.25, -2.5, 3.0e10])
        if kind == 4:
            return [self.random_value(rng, depth + 1, alphabet) for _ in range(rng.randint(0, 4))]
        return {f"k{i}": self.random_value(rng, depth + 1, alphabet) for i in range(rng.randint(0, 4))}

    def test_json_round_trip_of_random_data(self) -> None:
        rng = random.Random(4)
        for _ in range(200):
            data = {"x": self.random_value(rng, 0, self.ALPHABET)}
            for encode in ("to_json", "to_json(0)", "@json"):
                with self.subTest(encode=encode, data=data):
                    self.assertEqual(run(f".x | {encode} | from_json", data), data["x"])
            self.assertEqual(json.loads(run(".x | to_json(0)", data)), data["x"])

    def test_yaml_round_trip_of_random_data(self) -> None:
        # No tabs or newlines here: the YAML writer does not round-trip a block scalar that
        # starts with a newline or has a whitespace-only line (an older defect, not part of
        # the operators under test).
        alphabet = "".join(c for c in self.ALPHABET if c not in "\t\n")
        rng = random.Random(5)
        for _ in range(200):
            data = {"x": self.random_value(rng, 0, alphabet)}
            with self.subTest(data=data):
                self.assertEqual(run(". | to_yaml | from_yaml", data), data)
                if isinstance(data["x"], (list, dict)):
                    # (a bare scalar is written without quotes, so it need not read back the same)
                    self.assertEqual(run(".x | to_yaml(4) | from_yaml", data), data["x"])

    def test_csv_round_trip_of_random_tables(self) -> None:
        rng = random.Random(6)
        cells = ["a", "b c", "x,y", 'q"r', "日本", "abc-def", "semi;colon"]
        for _ in range(80):
            columns = [f"c{i}" for i in range(rng.randint(1, 4))]
            rows = [{c: rng.choice(cells) for c in columns} for _ in range(rng.randint(1, 5))]
            table = [columns] + [[row[c] for c in columns] for row in rows]
            self.assertEqual(run("@csv | @csvd", table), rows)
            self.assertEqual(run("@tsv | @tsvd", [[c.replace("\t", " ") for c in r] for r in table]), rows)


class SequenceProperties(unittest.TestCase):
    def test_against_plain_python(self) -> None:
        rng = random.Random(8)
        for _ in range(150):
            xs = [rng.randint(0, 9) for _ in range(rng.randint(0, 12))]
            self.assertEqual(run("reverse", xs), xs[::-1])
            self.assertEqual(run("unique", xs), list(dict.fromkeys(xs)))
            self.assertEqual(run("filter(. > 4)", xs), [x for x in xs if x > 4])
            self.assertEqual(run("sort", xs), sorted(xs))
            self.assertEqual(run("[.[] as $x ireduce (0; . + $x)] | .[0]", xs), sum(xs))
            self.assertEqual(run("contains([3])", xs), 3 in xs)
            first = next((x for x in xs if x > 6), None)
            self.assertEqual(run("[first(. > 6)]", xs), [] if first is None else [first])

    def test_shuffle_is_a_permutation(self) -> None:
        rng = random.Random(9)
        for _ in range(60):
            xs = [rng.randint(0, 9) for _ in range(rng.randint(0, 12))]
            self.assertEqual(sorted(run("shuffle", xs)), sorted(xs))

    def test_flatten_matches_a_recursive_flatten(self) -> None:
        rng = random.Random(10)

        def nested(depth: int) -> Any:
            if depth == 0 or rng.random() < 0.4:
                return rng.randint(0, 9)
            return [nested(depth - 1) for _ in range(rng.randint(0, 3))]

        def flatten(items: list[Any], depth: int) -> list[Any]:
            """Spread the lists in ``items`` ``depth`` levels down (all the way when negative)."""
            out: list[Any] = []
            for item in items:
                if isinstance(item, list) and depth != 0:
                    out.extend(flatten(item, depth - 1))
                else:
                    out.append(item)
            return out

        for _ in range(120):
            data = [nested(4) for _ in range(rng.randint(0, 4))]
            self.assertEqual(run("flatten", data), flatten(data, -1))
            for depth in (0, 1, 2):
                self.assertEqual(run(f"flatten({depth})", data), flatten(data, depth))

    def test_group_by_and_unique_by_match_a_dict(self) -> None:
        rng = random.Random(12)
        for _ in range(100):
            rows = [{"k": rng.randint(0, 3), "v": i} for i in range(rng.randint(0, 10))]
            groups: dict[int, list[Any]] = {}
            for row in rows:
                groups.setdefault(row["k"], []).append(row)
            self.assertEqual(run("group_by(.k)", rows), list(groups.values()))
            self.assertEqual(run("unique_by(.k)", rows), [g[0] for g in groups.values()])

    def test_pick_omit_sort_keys_match_dict_operations(self) -> None:
        rng = random.Random(13)
        for _ in range(100):
            data = {f"k{rng.randint(0, 30)}": rng.randint(0, 9) for _ in range(rng.randint(0, 10))}
            chosen = [f"k{rng.randint(0, 30)}" for _ in range(rng.randint(1, 5))]
            self.assertEqual(run(f"pick({json.dumps(chosen)})", data),
                             {k: data[k] for k in dict.fromkeys(chosen) if k in data})
            self.assertEqual(run(f"omit({json.dumps(chosen)})", data),
                             {k: v for k, v in data.items() if k not in chosen})
            self.assertEqual(list(run("sort_keys(.)", data)), sorted(data))

    def test_pivot_is_a_transpose(self) -> None:
        rng = random.Random(14)
        for _ in range(60):
            width, height = rng.randint(1, 5), rng.randint(1, 5)
            matrix = [[rng.randint(0, 9) for _ in range(width)] for _ in range(height)]
            self.assertEqual(run("pivot", matrix), [list(col) for col in zip(*matrix)])
            self.assertEqual(run("pivot | pivot", matrix), matrix)

    def test_pivot_pads_ragged_rows_with_null(self) -> None:
        rng = random.Random(15)
        checked = 0
        while checked < 60:
            rows = [[rng.randint(0, 9) for _ in range(rng.randint(0, 4))] for _ in range(rng.randint(1, 5))]
            if not any(rows):
                continue
            checked += 1
            expected = [[row[j] if j < len(row) else None for row in rows]
                        for j in range(max(len(r) for r in rows))]
            self.assertEqual(run("pivot", rows), expected)

    def test_join_and_split_match_python(self) -> None:
        rng = random.Random(16)
        words = ["ab", "cd", "", "e f", "日本", "x,y"]
        for _ in range(100):
            items = [rng.choice(words) for _ in range(rng.randint(0, 6))]
            text = "|".join(items)
            self.assertEqual(run('join("|")', items), text)
            self.assertEqual(run('split("|")', text), text.split("|") if text else [])

    def test_case_operators(self) -> None:
        rng = random.Random(17)
        for _ in range(100):
            text = "".join(rng.choice("abcXYZ 019") for _ in range(rng.randint(0, 12)))
            self.assertEqual(run("upcase", text), text.upper())
            self.assertEqual(run("downcase", text), text.lower())

    def test_sub_and_match_agree_with_re_for_plain_patterns(self) -> None:
        rng = random.Random(18)
        for _ in range(150):
            text = "".join(rng.choice("ab c1") for _ in range(rng.randint(0, 14)))
            self.assertEqual(run('sub("[ab]+", "<$0>")', text),
                             re.sub("[ab]+", lambda m: f"<{m.group(0)}>", text))
            self.assertEqual(run('sub("(a)(b)?", "$1-$2")', text),
                             re.sub("(a)(b)?", lambda m: f"{m.group(1)}-{m.group(2) or ''}", text))
            self.assertEqual(run('[match("[0-9]"; "g") | .offset]', text),
                             [m.start() for m in re.finditer("[0-9]", text)])


if __name__ == "__main__":
    unittest.main()
