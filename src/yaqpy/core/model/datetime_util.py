"""Timestamp helpers shared by ``+``, ``-``, comparison, sort and the date-time operators.

Go describes a time format by writing the reference time ``Mon Jan 2 15:04:05 MST 2006``
in the shape you want (``"Monday, 02-Jan-06 at 3:04PM MST"``). This module reads and writes
those layouts the way Go's ``time.Parse`` / ``Time.Format`` do (``time/format.go``).

Differences from Go: Python's ``datetime`` counts microseconds, not nanoseconds; years must be
in 1..9999; a zone abbreviation Go does not know is given the offset 0 (as Go does when the local
zone does not know it either).
"""

from __future__ import annotations

import datetime as _dt
import re

RFC3339 = "2006-01-02T15:04:05Z07:00"

_DURATION_RE = re.compile(r"([0-9]*(?:\.[0-9]*)?)(ns|us|µs|μs|ms|s|m|h)")
_UNITS = {
    "ns": 1e-9, "us": 1e-6, "µs": 1e-6, "μs": 1e-6, "ms": 1e-3, "s": 1.0, "m": 60.0, "h": 3600.0,
}

_LONG_MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
                "September", "October", "November", "December")
_SHORT_MONTHS = tuple(name[:3] for name in _LONG_MONTHS)
_LONG_DAYS = ("Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday")
_SHORT_DAYS = tuple(name[:3] for name in _LONG_DAYS)
_ZERO_STD = ("01", "02", "03", "04", "05", "06")          # what "0" + "1".."6" stands for

_NUMERIC_ZONES = ("-070000", "-07:00:00", "-0700", "-07:00", "-07")
_ISO_ZONES = ("Z070000", "Z07:00:00", "Z0700", "Z07:00", "Z07")


# ----------------------------------------------------------------------------- layout chunks

def _starts_with_lower(text: str) -> bool:
    return bool(text) and "a" <= text[0] <= "z"


def _next_std_chunk(layout: str) -> tuple[str, str, str]:
    """Go's ``nextStdChunk``: (literal prefix, the layout element, the rest). The element is
    ``""`` when the layout has no more elements."""
    n = len(layout)
    for i, c in enumerate(layout):
        rest = layout[i:]
        if c == "J":
            if rest.startswith("Jan"):
                if rest.startswith("January"):
                    return layout[:i], "January", layout[i + 7:]
                if not _starts_with_lower(layout[i + 3:]):
                    return layout[:i], "Jan", layout[i + 3:]
        elif c == "M":
            if rest.startswith("Mon"):
                if rest.startswith("Monday"):
                    return layout[:i], "Monday", layout[i + 6:]
                if not _starts_with_lower(layout[i + 3:]):
                    return layout[:i], "Mon", layout[i + 3:]
            if rest.startswith("MST"):
                return layout[:i], "MST", layout[i + 3:]
        elif c == "0":
            if n >= i + 2 and "1" <= layout[i + 1] <= "6":
                return layout[:i], _ZERO_STD[int(layout[i + 1]) - 1], layout[i + 2:]
            if rest.startswith("002"):
                return layout[:i], "002", layout[i + 3:]
        elif c == "1":
            if rest.startswith("15"):
                return layout[:i], "15", layout[i + 2:]
            return layout[:i], "1", layout[i + 1:]
        elif c == "2":
            if rest.startswith("2006"):
                return layout[:i], "2006", layout[i + 4:]
            return layout[:i], "2", layout[i + 1:]
        elif c == "_":
            if n >= i + 2 and layout[i + 1] == "2":
                if layout[i + 1:i + 5] == "2006":        # "_2006" is a literal _ then the year
                    return layout[:i + 1], "2006", layout[i + 5:]
                return layout[:i], "_2", layout[i + 2:]
            if rest.startswith("__2"):
                return layout[:i], "__2", layout[i + 3:]
        elif c in "345":
            return layout[:i], c, layout[i + 1:]
        elif c == "P":
            if rest.startswith("PM"):
                return layout[:i], "PM", layout[i + 2:]
        elif c == "p":
            if rest.startswith("pm"):
                return layout[:i], "pm", layout[i + 2:]
        elif c == "-":
            for element in _NUMERIC_ZONES:
                if rest.startswith(element):
                    return layout[:i], element, layout[i + len(element):]
        elif c == "Z":
            for element in _ISO_ZONES:
                if rest.startswith(element):
                    return layout[:i], element, layout[i + len(element):]
        elif c in ".,":
            if i + 1 < n and layout[i + 1] in "09":
                digit = layout[i + 1]
                j = i + 1
                while j < n and layout[j] == digit:
                    j += 1
                if not (j < n and layout[j].isdigit() and layout[j].isascii()):
                    return layout[:i], layout[i:j], layout[j:]
    return layout, "", ""


def _is_fraction(element: str) -> bool:
    return len(element) > 1 and element[0] in ".," and element[1] in "09"


# ----------------------------------------------------------------------------- format

def _pad(value: int, width: int, fill: str = "0") -> str:
    return str(value).rjust(width, fill)


def _zone_text(element: str, offset: int, iso: bool) -> str:
    """``-0700`` and friends; with ``iso`` (the ``Z`` forms) a zero offset is written ``Z``."""
    if iso and offset == 0:
        return "Z"
    kind = element[1:]                            # 07, 0700, 07:00, 070000 or 07:00:00
    total = abs(offset)
    hours, minutes, seconds = total // 3600, total % 3600 // 60, total % 60
    colon = ":" if ":" in kind else ""
    text = ("-" if offset < 0 else "+") + _pad(hours, 2)
    if kind == "07":
        return text
    text += colon + _pad(minutes, 2)
    if kind in ("070000", "07:00:00"):
        text += colon + _pad(seconds, 2)
    return text


def _format_element(dt: _dt.datetime, element: str) -> str:
    if element == "January":
        return _LONG_MONTHS[dt.month - 1]
    if element == "Jan":
        return _SHORT_MONTHS[dt.month - 1]
    if element == "Monday":
        return _LONG_DAYS[(dt.weekday() + 1) % 7]
    if element == "Mon":
        return _SHORT_DAYS[(dt.weekday() + 1) % 7]
    if element == "01":
        return _pad(dt.month, 2)
    if element == "1":
        return str(dt.month)
    if element == "02":
        return _pad(dt.day, 2)
    if element == "_2":
        return _pad(dt.day, 2, " ")
    if element == "2":
        return str(dt.day)
    yday = dt.timetuple().tm_yday
    if element == "002":
        return _pad(yday, 3)
    if element == "__2":
        return _pad(yday, 3, " ")
    if element == "15":
        return _pad(dt.hour, 2)
    hour12 = dt.hour % 12 or 12
    if element == "03":
        return _pad(hour12, 2)
    if element == "3":
        return str(hour12)
    if element == "04":
        return _pad(dt.minute, 2)
    if element == "4":
        return str(dt.minute)
    if element == "05":
        return _pad(dt.second, 2)
    if element == "5":
        return str(dt.second)
    if element == "2006":
        return _pad(dt.year, 4)
    if element == "06":
        return _pad(dt.year % 100, 2)
    if element == "PM":
        return "PM" if dt.hour >= 12 else "AM"
    if element == "pm":
        return "pm" if dt.hour >= 12 else "am"
    offset = int((dt.utcoffset() or _dt.timedelta(0)).total_seconds())
    if element == "MST":
        return dt.tzname() or _zone_text("-0700", offset, False)
    if element in _ISO_ZONES:
        return _zone_text(element, offset, True)
    if element in _NUMERIC_ZONES:
        return _zone_text(element, offset, False)
    if _is_fraction(element):                     # .000 or .999
        digits = len(element) - 1
        fraction = _pad(dt.microsecond, 6) + "000"
        text = fraction[:digits].ljust(digits, "0")
        if element[1] == "9":
            text = text.rstrip("0")
            return element[0] + text if text else ""
        return element[0] + text
    raise ValueError(f"unsupported layout element {element!r}")


def format_datetime(value: _dt.datetime, layout: str = RFC3339) -> str:
    """Go's ``Time.Format``."""
    if value.tzinfo is None:
        value = value.replace(tzinfo=_dt.timezone.utc)
    out: list[str] = []
    while layout:
        prefix, element, layout = _next_std_chunk(layout)
        out.append(prefix)
        if element:
            out.append(_format_element(value, element))
    return "".join(out)


# ----------------------------------------------------------------------------- parse

class _Bad(Exception):
    """The value does not fit the current layout element."""

    def __init__(self, message: str = "") -> None:
        super().__init__(message)
        self.message = message


def _quote(text: str) -> str:
    return '"' + text.replace("\\", "\\\\").replace('"', '\\"') + '"'


def _parse_error(layout: str, value: str, layout_elem: str, value_elem: str, message: str = "") -> ValueError:
    if not message:
        return ValueError(f"parsing time {_quote(value)} as {_quote(layout)}: cannot parse "
                          f"{_quote(value_elem)} as {_quote(layout_elem)}")
    return ValueError(f"parsing time {_quote(value)}{message}")


def _is_digit(text: str, i: int) -> bool:
    return i < len(text) and "0" <= text[i] <= "9"


def _getnum(text: str, fixed: bool) -> tuple[int, str]:
    if not _is_digit(text, 0):
        raise _Bad
    if not _is_digit(text, 1):
        if fixed:
            raise _Bad
        return int(text[0]), text[1:]
    return int(text[:2]), text[2:]


def _getnum3(text: str, fixed: bool) -> tuple[int, str]:
    count = 0
    while count < 3 and _is_digit(text, count):
        count += 1
    if count == 0 or (fixed and count != 3):
        raise _Bad
    return int(text[:count]), text[count:]


def _lookup(names: tuple[str, ...], text: str) -> tuple[int, str]:
    for index, name in enumerate(names):
        if len(text) >= len(name) and text[:len(name)].lower() == name.lower():
            return index, text[len(name):]
    raise _Bad


def _skip(value: str, prefix: str) -> str:
    """Go's ``skip``: a space in the layout matches a run of spaces in the value."""
    while prefix:
        if prefix[0] == " ":
            if value and value[0] != " ":
                raise _Bad
            prefix = prefix.lstrip(" ")
            value = value.lstrip(" ")
            continue
        if not value or value[0] != prefix[0]:
            raise _Bad
        prefix, value = prefix[1:], value[1:]
    return value


def _leading_int(text: str) -> tuple[int, str]:
    end = 0
    while _is_digit(text, end):
        end += 1
    if end == 0:
        raise _Bad
    return int(text[:end]), text[end:]


def _parse_signed_offset(value: str) -> int:
    if value[:1] not in ("-", "+"):
        return 0
    try:
        hours, rest = _leading_int(value[1:])
    except _Bad:
        return 0
    if hours > 23:
        return 0
    return len(value) - len(rest)


def _parse_time_zone(value: str) -> int:
    """Go's ``parseTimeZone``: the length of a zone abbreviation at the start of ``value``."""
    if len(value) < 3:
        return 0
    if value[:4] in ("ChST", "MeST"):
        return 4
    if value[:3] == "GMT":
        return 3 + (_parse_signed_offset(value[3:]) if len(value) > 3 else 0)
    if value[0] in "+-":
        return _parse_signed_offset(value)
    upper = 0
    while upper < 6 and upper < len(value) and "A" <= value[upper] <= "Z":
        upper += 1
    if upper == 5:
        return 5 if value[4] == "T" else 0
    if upper == 4:
        return 4 if value[3] == "T" or value[:4] == "WITA" else 0
    return 3 if upper == 3 else 0


def _parse_nanoseconds(value: str, width: int) -> tuple[int, str]:
    """``value[0]`` is the separator; ``value[1:width]`` are the digits. Returns microseconds."""
    if not value[0] in ".,":
        raise _Bad
    digits = value[1:width]
    if not digits.isdigit() or not digits.isascii():
        raise _Bad
    return int((digits + "000000")[:6]), value[width:]


def _days_in(month: int, year: int) -> int:
    if month == 2:
        leap = year % 4 == 0 and (year % 100 != 0 or year % 400 == 0)
        return 29 if leap else 28
    return 30 if month in (4, 6, 9, 11) else 31


def _parse_zone_offset(element: str, value: str) -> tuple[int, str]:
    """A numeric zone (``-0700`` and friends); returns (seconds east of UTC, the rest)."""
    kind = element[1:]                            # 07, 0700, 07:00, 070000 or 07:00:00
    if kind == "07:00":
        if len(value) < 6 or value[3] != ":":
            raise _Bad
        sign, hour, minute, second, rest = value[0], value[1:3], value[4:6], "00", value[6:]
    elif kind == "07":
        if len(value) < 3:
            raise _Bad
        sign, hour, minute, second, rest = value[0], value[1:3], "00", "00", value[3:]
    elif kind == "07:00:00":
        if len(value) < 9 or value[3] != ":" or value[6] != ":":
            raise _Bad
        sign, hour, minute, second, rest = value[0], value[1:3], value[4:6], value[7:9], value[9:]
    elif kind == "070000":
        if len(value) < 7:
            raise _Bad
        sign, hour, minute, second, rest = value[0], value[1:3], value[3:5], value[5:7], value[7:]
    else:
        if len(value) < 5:
            raise _Bad
        sign, hour, minute, second, rest = value[0], value[1:3], value[3:5], "00", value[5:]
    hours, _ = _getnum(hour, True)
    minutes, _ = _getnum(minute, True)
    seconds, _ = _getnum(second, True)
    if hours > 24:
        raise _Bad(": time zone offset hour out of range")
    if minutes > 60:
        raise _Bad(": time zone offset minute out of range")
    if seconds > 60:
        raise _Bad(": time zone offset second out of range")
    total = (hours * 60 + minutes) * 60 + seconds
    if sign == "+":
        return total, rest
    if sign == "-":
        return -total, rest
    raise _Bad


def _parse_layout(layout: str, value: str) -> _dt.datetime:
    """Go's ``time.Parse``."""
    original_layout, original_value = layout, value
    year, month, day, yday = 0, -1, -1, -1
    hour = minute = second = micro = 0
    pm_set = am_set = False
    zone: _dt.tzinfo | None = None
    zone_offset: int | None = None
    zone_name = ""
    remaining_layout = layout
    while True:
        prefix, element, suffix = _next_std_chunk(remaining_layout)
        try:
            value = _skip(value, prefix)
        except _Bad:
            raise _parse_error(original_layout, original_value, prefix, value) from None
        if not element:
            if value:
                raise _parse_error(original_layout, original_value, "", value,
                                   f": extra text: {_quote(value)}")
            break
        remaining_layout = suffix
        before = value
        try:
            if element == "2006":
                if len(value) < 4 or not _is_digit(value, 0):
                    raise _Bad
                year, value = int(value[:4]), value[4:]
            elif element == "06":
                if len(value) < 2 or not value[:2].isdigit():
                    raise _Bad
                year, value = int(value[:2]), value[2:]
                year += 1900 if year >= 69 else 2000
            elif element in ("Jan", "January"):
                index, value = _lookup(_SHORT_MONTHS if element == "Jan" else _LONG_MONTHS, value)
                month = index + 1
            elif element in ("1", "01"):
                month, value = _getnum(value, element == "01")
                if month <= 0 or month > 12:
                    raise _Bad(": month out of range")
            elif element in ("Mon", "Monday"):
                _, value = _lookup(_SHORT_DAYS if element == "Mon" else _LONG_DAYS, value)
            elif element in ("2", "_2", "02"):
                if element == "_2" and value[:1] == " ":
                    value = value[1:]
                day, value = _getnum(value, element == "02")
            elif element in ("__2", "002"):
                if element == "__2" and len(value) >= 1 and value[0] == " ":
                    value = value[1:]
                yday, value = _getnum3(value, element == "002")
            elif element == "15":
                hour, value = _getnum(value, False)
                if hour < 0 or hour >= 24:
                    raise _Bad(": hour out of range")
            elif element in ("3", "03"):
                hour, value = _getnum(value, element == "03")
                if hour < 0 or hour > 12:
                    raise _Bad(": hour out of range")
            elif element in ("4", "04"):
                minute, value = _getnum(value, element == "04")
                if minute < 0 or minute >= 60:
                    raise _Bad(": minute out of range")
            elif element in ("5", "05"):
                second, value = _getnum(value, element == "05")
                if second < 0 or second >= 60:
                    raise _Bad(": second out of range")
                # a fraction in the value that the layout does not ask for is still read
                if len(value) >= 2 and value[0] in ".," and _is_digit(value, 1):
                    _, next_element, _ = _next_std_chunk(suffix)
                    if not _is_fraction(next_element):
                        width = 2
                        while width < len(value) and _is_digit(value, width):
                            width += 1
                        micro, value = _parse_nanoseconds(value, width)
            elif element in ("PM", "pm"):
                if len(value) < 2:
                    raise _Bad
                token, value = value[:2], value[2:]
                if token == ("PM" if element == "PM" else "pm"):
                    pm_set = True
                elif token == ("AM" if element == "PM" else "am"):
                    am_set = True
                else:
                    raise _Bad
            elif element in _ISO_ZONES or element in _NUMERIC_ZONES:
                if element in _ISO_ZONES and value[:1] == "Z":
                    value = value[1:]
                    zone = _dt.timezone.utc
                else:
                    zone_offset, value = _parse_zone_offset(element, value)
            elif element == "MST":
                if value[:3] == "UTC":
                    zone, value = _dt.timezone.utc, value[3:]
                else:
                    length = _parse_time_zone(value)
                    if length == 0:
                        raise _Bad
                    zone_name, value = value[:length], value[length:]
            elif _is_fraction(element):
                if element[1] == "0":
                    width = len(element)
                    if len(value) < width:
                        raise _Bad
                    micro, value = _parse_nanoseconds(value, width)
                else:                              # .999: optional
                    if len(value) < 2 or value[0] not in ".," or not _is_digit(value, 1):
                        continue
                    width = 1
                    while width < len(value) and _is_digit(value, width):
                        width += 1
                    micro, value = _parse_nanoseconds(value, width)
        except _Bad as bad:
            if bad.message:
                raise _parse_error(original_layout, original_value, element, before,
                                   bad.message) from None
            raise _parse_error(original_layout, original_value, element, before) from None
    if pm_set and hour < 12:
        hour += 12
    elif am_set and hour == 12:
        hour = 0
    if yday >= 0:
        if not 1 <= yday <= (366 if _days_in(2, year) == 29 else 365):
            raise _parse_error(original_layout, original_value, "", value, ": day-of-year out of range")
        start = _dt.date(year or 1, 1, 1) + _dt.timedelta(days=yday - 1)
        month, day = start.month, start.day
    else:
        month = 1 if month < 0 else month
        day = 1 if day < 0 else day
    if day < 1 or day > _days_in(month, year):
        raise _parse_error(original_layout, original_value, "", value, ": day out of range")
    if not 1 <= (year or 1) <= 9999:
        raise _parse_error(original_layout, original_value, "", value, ": year out of range")
    if zone is None:
        if zone_offset is not None:
            zone = _dt.timezone(_dt.timedelta(seconds=zone_offset), "")    # unnamed, like Go's fake zone
        elif zone_name:
            offset = 0
            if len(zone_name) > 3 and zone_name[:3] == "GMT":
                offset = int(zone_name[3:]) * 3600 if zone_name[3:].lstrip("+-").isdigit() else 0
            zone = _dt.timezone(_dt.timedelta(seconds=offset), zone_name)
        else:
            zone = _dt.timezone.utc
    return _dt.datetime(year or 1, month, day, hour, minute, second, micro, tzinfo=zone)


def parse_datetime(layout: str, text: str) -> _dt.datetime:
    """Go's ``parseDateTime``: ``time.Parse`` with a date-only fallback for RFC3339."""
    try:
        return _parse_layout(layout, text)
    except ValueError:
        if layout == RFC3339:
            try:
                return _parse_layout("2006-01-02", text)
            except ValueError:
                pass
        raise


def unix_seconds(value: _dt.datetime) -> int:
    """``Time.Unix()``: whole seconds since the epoch, rounded down."""
    return (value - _dt.datetime(1970, 1, 1, tzinfo=_dt.timezone.utc)) // _dt.timedelta(seconds=1)


# ----------------------------------------------------------------------------- durations

def parse_go_duration(text: str) -> _dt.timedelta:
    """Go's ``time.ParseDuration``: ``"3h10m"``, ``"-1.5h"``, ``"300ms"``."""
    t = text.strip()
    if t in ("0", "+0", "-0"):
        return _dt.timedelta(0)
    sign = 1
    if t[:1] in "+-":
        sign = -1 if t[0] == "-" else 1
        t = t[1:]
    if t == "":
        raise ValueError(f"invalid duration {text!r}")
    pos = 0
    seconds = 0.0
    while pos < len(t):
        m = _DURATION_RE.match(t, pos)
        if m is None or m.group(1) in ("", "."):
            raise ValueError(f"invalid duration {text!r}")
        seconds += float(m.group(1)) * _UNITS[m.group(2)]
        pos = m.end()
    return _dt.timedelta(seconds=sign * seconds)


def looks_like_datetime(tag: str, value: str, layout: str) -> bool:
    if tag == "!!timestamp":
        return True
    if tag == "!!str" and layout != RFC3339:
        try:
            parse_datetime(layout, value)
            return True
        except ValueError:
            return False
    return False
