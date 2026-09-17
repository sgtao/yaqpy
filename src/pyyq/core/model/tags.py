"""Tag resolution for plain scalars (YAML 1.2 Core Schema) and number helpers.

Values are stored as their original text plus a tag (design doc 5-3), so this
module is the single place that decides what a piece of text *means*.
"""

from __future__ import annotations

import math
import re

NULL_RE = re.compile(r"^(?:~|null|Null|NULL|)$")
BOOL_RE = re.compile(r"^(?:true|True|TRUE|false|False|FALSE)$")
# YAML 1.2 core ints, plus the "_" digit separators go-yaml accepts.
INT_RE = re.compile(r"^(?:[-+]?[0-9](?:_?[0-9])*|0o[0-7](?:_?[0-7])*|0x[0-9a-fA-F](?:_?[0-9a-fA-F])*)$")
FLOAT_RE = re.compile(
    r"^(?:[-+]?(?:\.[0-9](?:_?[0-9])*|[0-9](?:_?[0-9])*(?:\.(?:[0-9](?:_?[0-9])*)?)?)(?:[eE][-+]?[0-9]+)?"
    r"|[-+]?\.(?:inf|Inf|INF)|\.(?:nan|NaN|NAN))$"
)


def resolve_plain(text: str) -> str:
    """Return the tag a *plain* (unquoted) scalar resolves to."""
    if NULL_RE.match(text):
        return "!!null"
    if BOOL_RE.match(text):
        return "!!bool"
    if INT_RE.match(text):
        return "!!int"
    if FLOAT_RE.match(text):
        return "!!float"
    return "!!str"


def parse_int(text: str) -> tuple[str, int]:
    """Parse an integer the way Go's ``parseInt64`` does.

    Returns ``(format, value)`` where *format* is one of ``"dec"``, ``"hex"``
    or ``"oct"`` so that results can be printed in the same base as the input.
    """
    t = text.replace("_", "")
    sign = ""
    digits = t
    if digits[:1] in ("+", "-"):
        sign, digits = digits[0], digits[1:]
    if digits.startswith(("0x", "0X")):
        return "hex", int(sign + digits[2:], 16)
    if digits.startswith("0o"):
        return "oct", int(sign + digits[2:], 8)
    return "dec", int(t, 10)


def format_int(fmt: str, value: int) -> str:
    if fmt == "hex":
        return ("-0x%X" % -value) if value < 0 else ("0x%X" % value)
    if fmt == "oct":
        return ("-0o%o" % -value) if value < 0 else ("0o%o" % value)
    return str(value)


def parse_float(text: str) -> float:
    t = text.replace("_", "")
    low = t.lower()
    if low in (".inf", "+.inf"):
        return math.inf
    if low == "-.inf":
        return -math.inf
    if low == ".nan":
        return math.nan
    return float(t)


def format_float(value: float) -> str:
    """Format a float like Go's ``fmt.Sprintf("%v", f)``.

    Go uses the shortest decimal representation and switches to exponent form
    when the decimal exponent is below -4 or at least 6 (``1e+06``).
    """
    if math.isnan(value):
        return "NaN"
    if math.isinf(value):
        return "+Inf" if value > 0 else "-Inf"
    neg = math.copysign(1.0, value) < 0
    text = repr(abs(value))
    if "e" in text:
        mantissa, exp_text = text.split("e")
        exponent = int(exp_text)
    else:
        mantissa, exponent = text, 0
    int_part, _, frac_part = mantissa.partition(".")
    if int_part.strip("0") == "":
        stripped = frac_part.lstrip("0")
        dp = -(len(frac_part) - len(stripped)) + exponent
        digits = stripped
    else:
        int_part = int_part.lstrip("0")
        digits = int_part + frac_part
        dp = len(int_part) + exponent
    digits = digits.rstrip("0")
    if digits == "":
        return "-0" if neg else "0"
    nd = len(digits)
    exp = dp - 1
    if exp < -4 or exp >= 6:
        mant = digits[0] + ("." + digits[1:] if nd > 1 else "")
        out = f"{mant}e{'+' if exp >= 0 else '-'}{abs(exp):02d}"
    elif dp <= 0:
        out = "0." + "0" * (-dp) + digits
    elif dp >= nd:
        out = digits + "0" * (dp - nd)
    else:
        out = digits[:dp] + "." + digits[dp:]
    return ("-" + out) if neg else out


def is_number_tag(tag: str) -> bool:
    return tag in ("!!int", "!!float")


def guess_tag(tag: str, value: str) -> str:
    """Go's ``guessTagFromCustomType``: for custom tags, guess the real type."""
    if tag.startswith("!!"):
        return tag
    if value == "":
        return tag
    return resolve_plain(value)
