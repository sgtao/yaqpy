"""日時の演算子（now・tz・from_unix・to_unix・format_datetime・with_dtf）と、その周辺（加減算・比較・ソート）。"""

from __future__ import annotations

import unittest
import zoneinfo
from datetime import datetime, timedelta, timezone
from unittest import mock

import yaqpy
from yaqpy import EvaluationError, Options
from yaqpy.core.operators.datetime_ops import load_zone

NOW = datetime(2021, 5, 19, 1, 2, 3, tzinfo=timezone.utc)
YQ = yaqpy.Yq(clock=lambda: NOW)


def run(expression: str, text: str = "", **options: object) -> str:
    return YQ.evaluate(expression, text, options=Options(**options)).strip()  # type: ignore[arg-type]


def fails(expression: str, text: str = "") -> str:
    with unittest.TestCase().assertRaises(EvaluationError) as raised:
        run(expression, text)
    return str(raised.exception)


def has_tz_data() -> bool:
    try:
        zoneinfo.ZoneInfo("Australia/Sydney")
    except zoneinfo.ZoneInfoNotFoundError:
        return False
    return True


class NowTests(unittest.TestCase):
    def test_now_reads_the_clock(self) -> None:
        self.assertEqual(run("now"), "2021-05-19T01:02:03Z")

    def test_now_is_a_timestamp(self) -> None:
        self.assertEqual(run("now | tag"), "!!timestamp")

    def test_now_in_an_assignment(self) -> None:
        self.assertEqual(run(".updated = now", "a: cool"), "a: cool\nupdated: 2021-05-19T01:02:03Z")

    def test_the_clock_can_have_an_offset(self) -> None:
        tokyo = datetime(2021, 5, 19, 10, 2, 3, tzinfo=timezone(timedelta(hours=9)))
        out = yaqpy.Yq(clock=lambda: tokyo).evaluate("now")
        self.assertEqual(out.strip(), "2021-05-19T10:02:03+09:00")

    def test_the_default_clock_is_the_system_clock(self) -> None:
        out = yaqpy.evaluate("now | to_unix").strip()
        self.assertAlmostEqual(int(out), datetime.now(timezone.utc).timestamp(), delta=5)


class UnixTests(unittest.TestCase):
    def test_from_unix_then_utc(self) -> None:
        self.assertEqual(run('1675301929 | from_unix | tz("UTC")'), "2023-02-02T01:38:49Z")

    def test_from_unix_keeps_milliseconds_only(self) -> None:
        self.assertEqual(run('1675301929.999 | from_unix | to_unix'), "1675301929")

    def test_from_unix_is_in_the_local_zone(self) -> None:
        with mock.patch("yaqpy.core.operators.datetime_ops._local_zone",
                        return_value=timezone.utc):
            self.assertEqual(run("0 | from_unix"), "1970-01-01T00:00:00Z")

    def test_from_unix_only_numbers(self) -> None:
        self.assertEqual(fails("from_unix", "abc"), "from_unix only works on numbers, found !!str instead")

    def test_to_unix(self) -> None:
        self.assertEqual(run("now | to_unix"), "1621386123")
        self.assertEqual(run('"2023-02-02T10:38:49+09:00" | to_unix'), "1675301929")
        self.assertEqual(run('"2023-02-02" | to_unix'), "1675296000")

    def test_to_unix_needs_a_datetime(self) -> None:
        self.assertIn("could not parse datetime of []", fails('"nope" | to_unix'))


class FormatTests(unittest.TestCase):
    def test_format_from_rfc3339(self) -> None:
        self.assertEqual(run('.a |= format_datetime("Monday, 02-Jan-06 at 3:04PM")',
                             "a: 2001-12-15T02:59:43.1Z"), "a: Saturday, 15-Dec-01 at 2:59AM")

    def test_the_result_is_read_as_yaml(self) -> None:
        self.assertEqual(run('.a | format_datetime("2006-01-02") | tag', "a: 2001-12-15"), "!!timestamp")
        self.assertEqual(run('.a | format_datetime("Monday") | tag', "a: 2001-12-15"), "!!str")
        self.assertEqual(run('.a | format_datetime("2") | tag', "a: 2001-12-15"), "!!int")

    def test_a_result_that_is_not_a_scalar_stays_a_string(self) -> None:
        self.assertEqual(run('.a | format_datetime("2006: 01") | tag', "a: 2001-12-15"), "!!str")

    def test_a_custom_layout_with_with_dtf(self) -> None:
        self.assertEqual(run('.a |= with_dtf("Monday, 02-Jan-06 at 3:04PM"; format_datetime("2006-01-02"))',
                             "a: Saturday, 15-Dec-01 at 2:59AM"), "a: 2001-12-15")

    def test_with_dtf_needs_both_arguments(self) -> None:
        self.assertIn("must provide a date time format string and an expression", fails("with_dtf(.a)", "a: 1"))

    def test_with_dtf_accepts_a_comma(self) -> None:
        self.assertEqual(run('with_dtf("2006", .a | to_unix)', 'a: "2001"'), "978307200")

    def test_a_bad_value(self) -> None:
        self.assertIn('could not parse datetime of [a]: parsing time "x"', fails('.a | format_datetime("2006")', "a: x"))


class DateArithmeticTests(unittest.TestCase):
    def test_add_and_subtract_a_duration(self) -> None:
        self.assertEqual(run('.a += "3h10m"', "a: 2021-01-01T00:00:00Z"), "a: 2021-01-01T03:10:00Z")
        self.assertEqual(run('.a -= "3h10m"', "a: 2021-01-01T03:10:00Z"), "a: 2021-01-01T00:00:00Z")

    def test_add_in_a_custom_layout(self) -> None:
        text = "a: Saturday, 15-Dec-01 at 2:59AM GMT"
        self.assertEqual(run('with_dtf("Monday, 02-Jan-06 at 3:04PM MST"; .a += "3h1m")', text),
                         "a: Saturday, 15-Dec-01 at 6:00AM GMT")

    def test_add_keeps_the_offset(self) -> None:
        self.assertEqual(run('.a += "1h"', "a: 2021-01-01T00:00:00+09:00"), "a: 2021-01-01T01:00:00+09:00")

    def test_a_bad_duration(self) -> None:
        self.assertIn("unable to parse duration [soon]", fails('.a += "soon"', "a: 2021-01-01T00:00:00Z"))

    def test_compare_in_a_custom_layout(self) -> None:
        text = "a: Saturday, 15-Dec-01 at 2:59AM GMT\nb: Sunday, 16-Dec-01 at 2:59AM GMT"
        self.assertEqual(run('with_dtf("Monday, 02-Jan-06 at 3:04PM MST"; .a < .b)', text), "true")

    def test_sort_by_a_custom_date(self) -> None:
        text = '[{a: "12-Jun-2011"}, {a: "23-Dec-2010"}, {a: "10-Aug-2011"}]'
        out = run('with_dtf("02-Jan-2006"; sort_by(.a) | .[].a)', text)
        self.assertEqual(out.split(), ["23-Dec-2010", "12-Jun-2011", "10-Aug-2011"])

    def test_sort_falls_back_to_the_text_when_a_value_is_not_a_date(self) -> None:
        out = run('with_dtf("02-Jan-2006"; sort_by(.a) | .[].a)', '[{a: "b"}, {a: "a"}]')
        self.assertEqual(out.split(), ["a", "b"])


class TimeZoneTests(unittest.TestCase):
    @unittest.skipUnless(has_tz_data(), "no time zone database (install the dev group: tzdata)")
    def test_now_in_sydney(self) -> None:
        self.assertEqual(run('now | tz("Australia/Sydney")'), "2021-05-19T11:02:03+10:00")

    @unittest.skipUnless(has_tz_data(), "no time zone database (install the dev group: tzdata)")
    def test_the_zone_abbreviation_is_the_database_name(self) -> None:
        text = "a: Saturday, 15-Dec-01 at 2:59AM GMT"
        self.assertEqual(run('.a |= with_dtf("Monday, 02-Jan-06 at 3:04PM MST"; tz("Australia/Sydney"))', text),
                         "a: Saturday, 15-Dec-01 at 1:59PM AEDT")
        self.assertEqual(run('.a |= with_dtf("Monday, 02-Jan-06 at 3:04PM MST"; tz("Australia/Perth"))', text),
                         "a: Saturday, 15-Dec-01 at 10:59AM AWST")

    def test_utc_and_the_empty_name(self) -> None:
        self.assertEqual(run('"2021-01-01T09:00:00+09:00" | tz("UTC")'), "2021-01-01T00:00:00Z")
        self.assertEqual(run('"2021-01-01T09:00:00+09:00" | tz("")'), "2021-01-01T00:00:00Z")

    def test_local_uses_this_machines_zone(self) -> None:
        with mock.patch("yaqpy.core.operators.datetime_ops._local_zone",
                        return_value=timezone(timedelta(hours=2))):
            self.assertEqual(run('"2021-01-01T00:00:00Z" | tz("Local")'), "2021-01-01T02:00:00+02:00")

    def test_a_missing_zone_is_reported(self) -> None:
        self.assertIn("could not load tz [Nowhere/Land]: unknown time zone Nowhere/Land",
                      fails('now | tz("Nowhere/Land")'))

    def test_a_missing_database_gives_a_hint(self) -> None:
        with mock.patch("zoneinfo.ZoneInfo", side_effect=zoneinfo.ZoneInfoNotFoundError("x")), \
                mock.patch("zoneinfo.TZPATH", ()):
            with self.assertRaises(EvaluationError) as raised:
                load_zone("Asia/Tokyo")
        self.assertIn("install the tzdata package", str(raised.exception))

    def test_lowercase_utc_is_not_special_like_in_go(self) -> None:
        # Go's LoadLocation("utc") is looked up as a name, and there is no such zone
        self.assertIn("could not load tz [nowhere]", fails('now | tz("nowhere")'))

    def test_the_layout_is_kept(self) -> None:
        self.assertEqual(run('"2021-01-01T00:00:00Z" | tz("UTC") | tag'), "!!str")


if __name__ == "__main__":
    unittest.main()
