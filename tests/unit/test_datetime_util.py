"""Go の時刻レイアウト（Monday, 02-Jan-06 at 3:04PM MST など）の読み書き。

期待値は Go の time パッケージの定数と文書（pkg.go.dev/time）にある値。
"""

from __future__ import annotations

import datetime as dt
import unittest

from yaqpy.core.model.datetime_util import (
    RFC3339, format_datetime, parse_datetime, parse_go_duration, unix_seconds,
)

UTC = dt.timezone.utc
# the reference moment used in Go's documentation: Tue Nov 10 23:00:00 2009 UTC
DOC_TIME = dt.datetime(2009, 11, 10, 23, 0, 0, tzinfo=UTC)

GO_CONSTANTS = {
    "ANSIC": ("Mon Jan _2 15:04:05 2006", "Tue Nov 10 23:00:00 2009"),
    "UnixDate": ("Mon Jan _2 15:04:05 MST 2006", "Tue Nov 10 23:00:00 UTC 2009"),
    "RFC822": ("02 Jan 06 15:04 MST", "10 Nov 09 23:00 UTC"),
    "RFC822Z": ("02 Jan 06 15:04 -0700", "10 Nov 09 23:00 +0000"),
    "RFC850": ("Monday, 02-Jan-06 15:04:05 MST", "Tuesday, 10-Nov-09 23:00:00 UTC"),
    "RFC1123": ("Mon, 02 Jan 2006 15:04:05 MST", "Tue, 10 Nov 2009 23:00:00 UTC"),
    "RFC1123Z": ("Mon, 02 Jan 2006 15:04:05 -0700", "Tue, 10 Nov 2009 23:00:00 +0000"),
    "RFC3339": (RFC3339, "2009-11-10T23:00:00Z"),
    "RFC3339Nano": ("2006-01-02T15:04:05.999999999Z07:00", "2009-11-10T23:00:00Z"),
    "Kitchen": ("3:04PM", "11:00PM"),
    "Stamp": ("Jan _2 15:04:05", "Nov 10 23:00:00"),
    "StampMilli": ("Jan _2 15:04:05.000", "Nov 10 23:00:00.000"),
    "DateTime": ("2006-01-02 15:04:05", "2009-11-10 23:00:00"),
    "DateOnly": ("2006-01-02", "2009-11-10"),
    "TimeOnly": ("15:04:05", "23:00:00"),
}


class FormatTests(unittest.TestCase):
    def test_go_constants(self) -> None:
        for name, (layout, expected) in GO_CONSTANTS.items():
            with self.subTest(name=name):
                self.assertEqual(format_datetime(DOC_TIME, layout), expected)

    def test_the_custom_layout_from_the_yq_docs(self) -> None:
        moment = dt.datetime(2001, 12, 15, 2, 59, 43, 100000, tzinfo=UTC)
        self.assertEqual(format_datetime(moment, "Monday, 02-Jan-06 at 3:04PM"),
                         "Saturday, 15-Dec-01 at 2:59AM")
        self.assertEqual(format_datetime(moment, "Monday"), "Saturday")

    def test_twelve_hour_clock(self) -> None:
        for hour, text in ((0, "12:00AM"), (1, "1:00AM"), (12, "12:00PM"), (13, "1:00PM")):
            with self.subTest(hour=hour):
                moment = dt.datetime(2020, 1, 1, hour, 0, tzinfo=UTC)
                self.assertEqual(format_datetime(moment, "3:04PM"), text)
        self.assertEqual(format_datetime(dt.datetime(2020, 1, 1, 13, 5, tzinfo=UTC), "03:04pm"), "01:05pm")

    def test_offsets(self) -> None:
        tokyo = dt.timezone(dt.timedelta(hours=9), "JST")
        moment = dt.datetime(2020, 1, 2, 3, 4, 5, tzinfo=tokyo)
        self.assertEqual(format_datetime(moment, "-0700"), "+0900")
        self.assertEqual(format_datetime(moment, "-07:00"), "+09:00")
        self.assertEqual(format_datetime(moment, "-07"), "+09")
        self.assertEqual(format_datetime(moment, "-070000"), "+090000")
        self.assertEqual(format_datetime(moment, "-07:00:00"), "+09:00:00")
        self.assertEqual(format_datetime(moment, "Z07:00"), "+09:00")
        self.assertEqual(format_datetime(moment, "MST"), "JST")
        self.assertEqual(format_datetime(moment.astimezone(UTC), "Z07:00"), "Z")
        self.assertEqual(format_datetime(moment, RFC3339), "2020-01-02T03:04:05+09:00")

    def test_an_unnamed_zone_is_written_as_its_offset(self) -> None:
        moment = dt.datetime(2020, 1, 2, tzinfo=dt.timezone(dt.timedelta(hours=-5, minutes=-30), ""))
        self.assertEqual(format_datetime(moment, "MST"), "-0530")

    def test_fractions(self) -> None:
        moment = dt.datetime(2020, 1, 2, 3, 4, 5, 120000, tzinfo=UTC)
        self.assertEqual(format_datetime(moment, "05.000"), "05.120")
        self.assertEqual(format_datetime(moment, "05.000000"), "05.120000")
        self.assertEqual(format_datetime(moment, "05.999"), "05.12")
        self.assertEqual(format_datetime(dt.datetime(2020, 1, 2, tzinfo=UTC), "05.999"), "00")
        self.assertEqual(format_datetime(moment, "05,000"), "05,120")

    def test_day_and_year_forms(self) -> None:
        moment = dt.datetime(2021, 3, 4, tzinfo=UTC)
        self.assertEqual(format_datetime(moment, "2 _2 02 1 01 Jan January 06 2006"),
                         "4  4 04 3 03 Mar March 21 2021")
        self.assertEqual(format_datetime(moment, "002 __2"), "063  63")

    def test_literal_text_is_kept(self) -> None:
        moment = dt.datetime(2021, 3, 4, tzinfo=UTC)
        self.assertEqual(format_datetime(moment, "Year: 2006!"), "Year: 2021!")
        # "Janet" is not a month: the J is followed by a lowercase letter
        self.assertEqual(format_datetime(moment, "Janet"), "Janet")


class ParseTests(unittest.TestCase):
    def test_go_constants_round_trip(self) -> None:
        for name, (layout, text) in GO_CONSTANTS.items():
            if name in ("Stamp", "StampMilli", "Kitchen", "TimeOnly", "DateOnly"):
                continue                       # they do not carry a full date
            with self.subTest(name=name):
                parsed = parse_datetime(layout, text)
                self.assertEqual(parsed, DOC_TIME)
                self.assertEqual(format_datetime(parsed, layout), text)

    def test_the_layout_from_the_yq_docs(self) -> None:
        layout = "Monday, 02-Jan-06 at 3:04PM MST"
        parsed = parse_datetime(layout, "Saturday, 15-Dec-01 at 2:59AM GMT")
        self.assertEqual(parsed, dt.datetime(2001, 12, 15, 2, 59, tzinfo=UTC))
        self.assertEqual(parsed.tzname(), "GMT")
        self.assertEqual(format_datetime(parsed, layout), "Saturday, 15-Dec-01 at 2:59AM GMT")

    def test_unknown_abbreviations_keep_their_name_and_offset_zero(self) -> None:
        parsed = parse_datetime("15:04 MST", "10:30 AEDT")
        self.assertEqual((parsed.utcoffset(), parsed.tzname()), (dt.timedelta(0), "AEDT"))

    def test_gmt_with_an_hour_offset(self) -> None:
        parsed = parse_datetime("15:04 MST", "10:30 GMT+5")
        self.assertEqual(parsed.utcoffset(), dt.timedelta(hours=5))

    def test_numeric_zones(self) -> None:
        for layout, text in (("15:04 -0700", "10:30 +0530"), ("15:04 -07:00", "10:30 +05:30"),
                             ("15:04 Z07:00", "10:30 +05:30"), ("15:04 -07:00:00", "10:30 +05:30:00"),
                             ("15:04 -070000", "10:30 +053000")):
            with self.subTest(layout=layout):
                self.assertEqual(parse_datetime(layout, text).utcoffset(),
                                 dt.timedelta(hours=5, minutes=30))
        self.assertEqual(parse_datetime("15:04 -07", "10:30 -08").utcoffset(), dt.timedelta(hours=-8))
        self.assertEqual(parse_datetime("15:04 Z0700", "10:30 Z").utcoffset(), dt.timedelta(0))

    def test_rfc3339_accepts_a_fraction_the_layout_does_not_mention(self) -> None:
        parsed = parse_datetime(RFC3339, "2001-12-15T02:59:43.1Z")
        self.assertEqual(parsed, dt.datetime(2001, 12, 15, 2, 59, 43, 100000, tzinfo=UTC))

    def test_rfc3339_falls_back_to_a_date(self) -> None:
        self.assertEqual(parse_datetime(RFC3339, "2001-12-15"), dt.datetime(2001, 12, 15, tzinfo=UTC))

    def test_twelve_hour_clock(self) -> None:
        self.assertEqual(parse_datetime("3:04PM", "12:15AM").hour, 0)
        self.assertEqual(parse_datetime("3:04PM", "12:15PM").hour, 12)
        self.assertEqual(parse_datetime("3:04PM", "1:15PM").hour, 13)
        self.assertEqual(parse_datetime("3:04pm", "1:15pm").hour, 13)

    def test_two_digit_years(self) -> None:
        self.assertEqual(parse_datetime("06-01-02", "68-01-02").year, 2068)
        self.assertEqual(parse_datetime("06-01-02", "69-01-02").year, 1969)

    def test_month_names_are_case_insensitive(self) -> None:
        self.assertEqual(parse_datetime("02-Jan-2006", "23-dec-2010").month, 12)
        self.assertEqual(parse_datetime("January 2, 2006", "MARCH 4, 2021").month, 3)

    def test_spaces_and_padding(self) -> None:
        self.assertEqual(parse_datetime("Jan _2 2006", "Mar  4 2021").day, 4)
        self.assertEqual(parse_datetime("2006-1-2", "2021-3-4").day, 4)

    def test_day_of_year(self) -> None:
        self.assertEqual(parse_datetime("2006 002", "2021 063"), dt.datetime(2021, 3, 4, tzinfo=UTC))

    def test_fractions(self) -> None:
        self.assertEqual(parse_datetime("05.000", "07.120").microsecond, 120000)
        self.assertEqual(parse_datetime("05.999", "07.12").microsecond, 120000)
        self.assertEqual(parse_datetime("05.999", "07").microsecond, 0)
        self.assertEqual(parse_datetime("05", "07.5").microsecond, 500000)

    def test_errors_read_like_go(self) -> None:
        cases = (
            ("2006-01-02", "2021-13-04", 'parsing time "2021-13-04": month out of range'),
            ("2006-01-02", "2021-02-30", 'parsing time "2021-02-30": day out of range'),
            ("2006-01-02", "2021-01-02 extra", 'parsing time "2021-01-02 extra": extra text: " extra"'),
            ("2006-01-02", "abc", 'parsing time "abc" as "2006-01-02": cannot parse "abc" as "2006"'),
            ("15:04", "24:00", 'parsing time "24:00": hour out of range'),
        )
        for layout, text, message in cases:
            with self.subTest(text=text), self.assertRaises(ValueError) as raised:
                parse_datetime(layout, text)
            self.assertEqual(str(raised.exception), message)

    def test_rfc3339_error_is_from_the_first_layout(self) -> None:
        with self.assertRaises(ValueError) as raised:
            parse_datetime(RFC3339, "nope")
        self.assertIn('as "2006-01-02T15:04:05Z07:00"', str(raised.exception))


class UnixAndDurationTests(unittest.TestCase):
    def test_unix_seconds_round_down(self) -> None:
        self.assertEqual(unix_seconds(dt.datetime(1970, 1, 1, 0, 0, 1, 999999, tzinfo=UTC)), 1)
        self.assertEqual(unix_seconds(dt.datetime(1969, 12, 31, 23, 59, 59, 500000, tzinfo=UTC)), -1)
        tokyo = dt.timezone(dt.timedelta(hours=9))
        self.assertEqual(unix_seconds(dt.datetime(2023, 2, 2, 10, 38, 49, tzinfo=tokyo)), 1675301929)

    def test_durations(self) -> None:
        self.assertEqual(parse_go_duration("3h1m"), dt.timedelta(hours=3, minutes=1))
        self.assertEqual(parse_go_duration("-1.5h"), dt.timedelta(minutes=-90))
        self.assertEqual(parse_go_duration("300ms"), dt.timedelta(milliseconds=300))
        with self.assertRaises(ValueError):
            parse_go_duration("3 hours")


if __name__ == "__main__":
    unittest.main()
