"""argparse definition for the ``yaqpy`` command (design doc 12-2)."""

from __future__ import annotations

import argparse
import re
import sys
from typing import NoReturn

from yaqpy.formats.registry import builtin_formats

SUBCOMMANDS = {"eval": "eval", "e": "eval", "eval-all": "eval-all", "ea": "eval-all"}

_SHORT_WITH_EQUALS = re.compile(r"^(-[a-zA-Z0-9])=(.*)$", re.DOTALL)


class ArgumentError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class _Parser(argparse.ArgumentParser):
    """Exit code 1 on bad arguments (Go's behaviour), no automatic sys.exit."""

    def error(self, message: str) -> NoReturn:
        raise ArgumentError(message)


def parse_bool(text: str) -> bool:
    low = text.strip().lower()
    if low in ("true", "t", "1", "yes", "y"):
        return True
    if low in ("false", "f", "0", "no", "n"):
        return False
    raise argparse.ArgumentTypeError(f"invalid boolean value {text!r}")


_OPTIONAL_VALUE_FLAGS = {
    "-r", "--unwrapScalar", "--unwrap-scalar", "--header-preprocess",
    "--yaml-fix-merge-anchor-to-spec",
    "--xml-strict-mode", "--xml-keep-namespace", "--xml-raw-token", "--xml-skip-proc-inst",
    "--xml-skip-directives", "--csv-auto-parse", "--tsv-auto-parse",
}

_SEPARATOR_ESCAPES = (("\\n", "\n"), ("\\t", "\t"), ("\\r", "\r"), ("\\f", "\f"), ("\\v", "\v"))


def parse_separator(text: str) -> str:
    """``--csv-separator``: one character; ``\\t`` and friends are accepted (Go's ``runeValue``)."""
    value = text
    for escaped, real in _SEPARATOR_ESCAPES:
        value = value.replace(escaped, real)
    if len(value) != 1:
        raise argparse.ArgumentTypeError(
            f"[{value}] is not a valid character. Must be length 1 was {len(value)}")
    return value


def normalise_argv(argv: list[str]) -> list[str]:
    """Accept Go/pflag style ``-o=json`` for single-letter flags, and make the
    "optional value" flags (``-r`` / ``-r=false``) never swallow the next argument."""
    out: list[str] = []
    for arg in argv:
        m = _SHORT_WITH_EQUALS.match(arg)
        if m:
            out.append(m.group(1))
            out.append(m.group(2))
        elif arg in _OPTIONAL_VALUE_FLAGS:
            out.append(arg)
            out.append("true")
        else:
            out.append(arg)
    return out


def build_parser() -> _Parser:
    formats = builtin_formats()
    parser = _Parser(
        prog="yaqpy",
        description="yaqpy is a lightweight and portable command-line data file processor "
                    "(a pure-Python implementation of mikefarah/yq).",
        epilog="""examples:
  yaqpy '.stuff' < myfile.yml
  yaqpy -i '.stuff = "foo"' myfile.yml
  yaqpy -P -oy sample.json
  yaqpy eval-all 'select(fi == 0) * select(fi == 1)' f1.yml f2.yml""",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        add_help=True,
    )
    parser.add_argument("args", nargs="*", metavar="[eval|eval-all] [expression] [files...]")
    g = parser.add_argument_group("output")
    g.add_argument("-o", "--output-format", default="auto",
                   help=f"[auto|a|{formats.available_string()}] output format type.")
    g.add_argument("-p", "--input-format", default="auto",
                   help=f"[auto|a|{'|'.join(formats.input_formats())}] parse format for input.")
    g.add_argument("-I", "--indent", type=int, default=2, help="sets indent level for output")
    g.add_argument("-r", "--unwrapScalar", "--unwrap-scalar", dest="unwrap_scalar", nargs="?",
                   const=True, default=None, type=parse_bool,
                   help="unwrap scalar, print the value with no quotes, colours or comments. "
                        "Defaults to true for yaml")
    g.add_argument("-N", "--no-doc", action="store_true", help="Don't print document separators (---)")
    g.add_argument("-P", "--prettyPrint", "--pretty-print", dest="pretty_print", action="store_true",
                   help="pretty print, shorthand for '... style = \"\"'")
    g.add_argument("-0", "--nul-output", action="store_true",
                   help="Use NUL char to separate values. If unwrap scalar is also set, fail if "
                        "unwrapped scalar contains NUL char.")
    g.add_argument("-C", "--colors", action="store_true", help="force print with colors (not implemented)")
    g.add_argument("-M", "--no-colors", action="store_true", help="force print with no colors")
    g.add_argument("-c", "--yaml-compact-seq-indent", action="store_true",
                   help="Use compact sequence indentation where '- ' is considered part of the indentation.")
    g.add_argument("--properties-separator", default=" = ",
                   help="separator to use between keys and values")
    g.add_argument("--properties-array-brackets", action="store_true",
                   help="use [x] in array paths (e.g. for SpringBoot)")
    g.add_argument("--toon", action="store_true",
                   help="print to stdout in TOON (Token-Oriented Object Notation); same as -o toon")
    g.add_argument("--toon-delimiter", choices=["comma", "tab", "pipe"], default="comma",
                   help="delimiter for TOON arrays and table rows (default: comma)")
    f = parser.add_argument_group("format options")
    f.add_argument("--xml-attribute-prefix", default="+@", help="prefix for xml attributes")
    f.add_argument("--xml-content-name", default="+content",
                   help="name for xml content (if no attribute name is present).")
    f.add_argument("--xml-strict-mode", nargs="?", const=True, default=False, type=parse_bool,
                   help="enables strict parsing of XML.")
    f.add_argument("--xml-keep-namespace", nargs="?", const=True, default=True, type=parse_bool,
                   help="enables keeping namespace after parsing attributes")
    f.add_argument("--xml-raw-token", nargs="?", const=True, default=True, type=parse_bool,
                   help="use the raw token names (namespace prefixes are not translated)")
    f.add_argument("--xml-proc-inst-prefix", default="+p_",
                   help='prefix for xml processing instructions (e.g. <?xml version="1"?>)')
    f.add_argument("--xml-directive-name", default="+directive",
                   help="name for xml directives (e.g. <!DOCTYPE thing cat>)")
    f.add_argument("--xml-skip-proc-inst", nargs="?", const=True, default=False, type=parse_bool,
                   help='skip over process instructions (e.g. <?xml version="1"?>)')
    f.add_argument("--xml-skip-directives", nargs="?", const=True, default=False, type=parse_bool,
                   help="skip over directives (e.g. <!DOCTYPE thing cat>)")
    f.add_argument("--csv-auto-parse", nargs="?", const=True, default=True, type=parse_bool,
                   help="parse CSV YAML/JSON values")
    f.add_argument("--csv-separator", default=",", type=parse_separator, help="CSV Separator character")
    f.add_argument("--tsv-auto-parse", nargs="?", const=True, default=True, type=parse_bool,
                   help="parse TSV YAML/JSON values")
    f.add_argument("--toml-allow-lossy", action="store_true",
                   help="allow -i to rewrite a TOML file although its comments are not kept "
                        "(yaqpy extension)")
    sc = parser.add_argument_group("schema (yaqpy extension)")
    sc.add_argument("--schema", action="store_true",
                    help="print a JSON Schema (Draft 2020-12) of the data; shorthand for the "
                         "expression 'schema' (or '<expression> | schema')")
    sc.add_argument("--schema-strict", action="store_true",
                    help="write additionalProperties: false on every object")
    sc.add_argument("--schema-enum-max", type=int, default=0, metavar="N",
                    help="a string that takes at most N different values (and repeats) becomes an enum")
    sc.add_argument("--schema-per-doc", action="store_true",
                    help="one schema per document (or node) instead of one merged schema")
    i = parser.add_argument_group("input")
    i.add_argument("-i", "--inplace", action="store_true",
                   help="update the file in place of first file given.")
    i.add_argument("-n", "--null-input", action="store_true",
                   help="Don't read input, simply evaluate the expression given. "
                        "Useful for creating docs from scratch.")
    i.add_argument("--from-file", default="", help="Load expression from specified file.")
    i.add_argument("--expression", default="",
                   help="forcibly set the expression argument. Useful when yq argument detection "
                        "thinks your expression is a file.")
    i.add_argument("--header-preprocess", nargs="?", const=True, default=True, type=parse_bool,
                   help="Slurp any header comments and separators before processing expression.")
    i.add_argument("--yaml-fix-merge-anchor-to-spec", nargs="?", const=True, default=False,
                   type=parse_bool, help="Fix merge anchor to match YAML spec.")
    i.add_argument("-s", "--split-exp", default="", help="(phase 2) print each result into a file named (exp)")
    i.add_argument("-f", "--front-matter", default="", help="(phase 2) (extract|process) first input as yaml front-matter")
    s = parser.add_argument_group("security")
    s.add_argument("--security-disable-env-ops", action="store_true", help="Disable env related operations.")
    s.add_argument("--security-disable-file-ops", action="store_true",
                   help="Disable file related operations (e.g. load)")
    s.add_argument("--security-enable-system-operator", action="store_true",
                   help="Enable system operator to allow execution of external commands.")
    m = parser.add_argument_group("misc")
    m.add_argument("-e", "--exit-status", action="store_true",
                   help="set exit status if there are no matches or null or false is returned")
    m.add_argument("-v", "--verbose", action="store_true", help="verbose mode")
    m.add_argument("-V", "--version", action="store_true", help="Print version information and quit")
    m.add_argument("--gui", action="store_true",
                   help="Launch the desktop GUI (needs the optional 'flet' package; see the README)")
    return parser


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = build_parser()
    ns = parser.parse_intermixed_args(normalise_argv(argv))
    ns.command = "eval"
    if ns.args and ns.args[0] in SUBCOMMANDS:
        ns.command = SUBCOMMANDS[ns.args.pop(0)]
    return ns


def print_help(stream=sys.stdout) -> None:
    build_parser().print_help(stream)
