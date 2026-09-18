"""Timestamp helpers shared by ``+``, ``-``, comparison and sort.

Only the Go ``time.RFC3339`` layout (and the date-only fallback yq uses) is
supported in phase 1; ``with_dtf`` / ``format_datetime`` come in phase 2.
"""

from __future__ import annotations

import datetime as _dt
import re

RFC3339 = "2006-01-02T15:04:05Z07:00"

_DURATION_RE = re.compile(r"([0-9]*(?:\.[0-9]*)?)(ns|us|µs|μs|ms|s|m|h)")
_UNITS = {
    "ns": 1e-9, "us": 1e-6, "µs": 1e-6, "μs": 1e-6, "ms": 1e-3, "s": 1.0, "m": 60.0, "h": 3600.0,
}


def parse_datetime(layout: str, text: str) -> _dt.datetime:
    """Go's ``parseDateTime`` for the RFC3339 layout (with the date-only fallback)."""
    if layout != RFC3339:
        raise ValueError(f"unsupported datetime layout {layout!r}")
    t = text.strip()
    try:
        if t.endswith("Z"):
            t = t[:-1] + "+00:00"
        parsed = _dt.datetime.fromisoformat(t)
    except ValueError:
        try:
            date = _dt.date.fromisoformat(t)
        except ValueError:
            raise ValueError(f"cannot parse {text!r} as a datetime") from None
        return _dt.datetime(date.year, date.month, date.day, tzinfo=_dt.timezone.utc)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed


def format_datetime(value: _dt.datetime, layout: str = RFC3339) -> str:
    if layout != RFC3339:
        raise ValueError(f"unsupported datetime layout {layout!r}")
    if value.tzinfo is None:
        value = value.replace(tzinfo=_dt.timezone.utc)
    offset = value.utcoffset() or _dt.timedelta(0)
    base = value.strftime("%Y-%m-%dT%H:%M:%S")
    if offset == _dt.timedelta(0):
        return base + "Z"
    total = int(offset.total_seconds())
    sign = "+" if total >= 0 else "-"
    total = abs(total)
    return f"{base}{sign}{total // 3600:02d}:{(total % 3600) // 60:02d}"


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
