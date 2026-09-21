"""encode / decode operators: ``to_json`` ``@yaml`` ``@csv`` ``from_xml`` ``@base64d`` ...

(Go's ``operator_encoder_decoder.go``, ``encoder_base64.go``, ``encoder_uri.go``, ``encoder_sh.go``
and the matching decoders.) The registered formats do the work; base64, uri and sh are small
string transformations that live here.
"""

from __future__ import annotations

import base64
import binascii
import io
import re
import urllib.parse
from dataclasses import replace

from yaqpy.core.engine.context import Context
from yaqpy.core.engine.navigator import Navigator
from yaqpy.core.lang.ast import ExprNode
from yaqpy.core.lang.prefs import DecoderPrefs, EncoderPrefs
from yaqpy.core.model.node import Kind, Node
from yaqpy.core.operators.anchors import explode_node
from yaqpy.core.operators.registry import operator
from yaqpy.errors import EvaluationError
from yaqpy.options import Options

_TRAILING_NEWLINES = re.compile(r"\n+\Z")
_SH_SAFE = frozenset("@%+=:,./-_")
_URI_HEX = re.compile(r"[0-9A-Fa-f]{2}")


def _text_bytes(text: str) -> bytes:
    return text.encode("utf-8", "surrogatepass")


def _text(data: bytes) -> str:
    """Go strings are bytes; the closest Python text keeps valid UTF-8 and marks the rest."""
    return data.decode("utf-8", "replace")


def _require_string(node: Node, message: str) -> str:
    if node.guess_tag() != "!!str":
        raise EvaluationError(message.format(node.tag))
    return node.value


# ----------------------------------------------------------------------------- base64 / uri / sh

def encode_base64(node: Node) -> str:
    value = _require_string(node, "cannot encode {} as base64, can only operate on strings")
    return base64.b64encode(_text_bytes(value)).decode("ascii")


def decode_base64(text: str) -> str:
    """Go's decoder: surrounding whitespace is dropped, missing ``=`` padding is added and
    line breaks inside the data are ignored."""
    stripped = text.strip().replace("\r", "").replace("\n", "")
    if len(stripped) % 4:
        stripped += "=" * (4 - len(stripped) % 4)
    try:
        return _text(base64.b64decode(stripped, validate=True))
    except (binascii.Error, ValueError):
        alphabet = set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
        bad = next((i for i, ch in enumerate(stripped) if ch not in alphabet), len(stripped))
        raise EvaluationError(f"illegal base64 data at input byte {bad}") from None


_URI_MESSAGE = ("cannot encode {} as URI, can only operate on strings. Please first pipe through "
                "another encoding operator to convert the value to a string")


def encode_uri(node: Node) -> str:
    return urllib.parse.quote_plus(_require_string(node, _URI_MESSAGE), safe="")


def decode_uri(text: str) -> str:
    """Go's ``url.QueryUnescape``: ``+`` is a space and a bad ``%`` escape is an error."""
    out = bytearray()
    data = _text_bytes(text)
    i = 0
    while i < len(data):
        byte = data[i]
        if byte == 0x25:                                        # %
            digits = data[i + 1:i + 3].decode("latin-1")
            if not _URI_HEX.fullmatch(digits):
                shown = data[i:i + 3].decode("latin-1")
                raise EvaluationError(f'invalid URL escape "{shown}"')
            out.append(int(digits, 16))
            i += 3
            continue
        out.append(0x20 if byte == 0x2B else byte)              # +
        i += 1
    return _text(bytes(out))


def encode_sh(node: Node) -> str:
    """Quote what a shell would not take literally, using the fewest quote blocks (Go's ``shEncoder``)."""
    value = _require_string(node, _URI_MESSAGE)
    out: list[str] = []
    in_block = False
    for ch in value:
        if ch == "'":
            if in_block:
                out.append("'")
                in_block = False
            out.append("\\")
        elif not (ch.isascii() and (ch.isalnum() or ch in _SH_SAFE)) and not in_block:
            out.append("'")
            in_block = True
        out.append(ch)
    if in_block:
        out.append("'")
    return "".join(out)


# ----------------------------------------------------------------------------- encode

def _with_indent(options: Options, indent: int) -> Options:
    toon = replace(options.toon, indent=indent) if indent >= 1 else options.toon
    return replace(options, indent=indent, yaml=replace(options.yaml, indent=indent),
                   xml=replace(options.xml, indent=indent), toon=toon)


def _encode_with_format(nav: Navigator, node: Node, name: str, indent: int) -> str:
    formats = nav.env.formats
    options = _with_indent(nav.env.options, indent)
    spec = formats.get(name)
    unwrap = False if name == "json" else spec.unwrap_scalar_default
    encoder = formats.encoder_for(name, options, unwrap)
    if not encoder.can_handle_aliases():
        node = node.copy()
        explode_node(node, fix_merge=options.yaml.fix_merge_anchor_to_spec,
                     max_depth=options.limits.max_depth)
    out = io.StringIO()
    encoder.print_leading_content(out, node.leading_content)
    encoder.encode(out, node)
    return out.getvalue()


def _encode(nav: Navigator, node: Node, prefs: EncoderPrefs) -> str:
    if prefs.format == "base64":
        return encode_base64(node)
    if prefs.format == "uri":
        return encode_uri(node)
    if prefs.format == "sh":
        return encode_sh(node)
    return _encode_with_format(nav, node, prefs.format, prefs.indent)


def _decoded_key(node: Node) -> str:
    return "decoded: " + node.identity_key()


@operator("ENCODE")
def encode_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    prefs = expr.operation.prefs
    assert isinstance(prefs, EncoderPrefs)
    results: list[Node] = []
    for candidate in ctx.nodes:
        text = _encode(nav, candidate, prefs)
        # If this value was decoded from a string, and that string had no trailing newline, give
        # the encoded string the same shape (so a round trip does not add a newline).
        original = ctx.get_variable(_decoded_key(candidate))
        if (original and text.endswith("\n") and not text.endswith("\n\n") and len(text) > 1
                and not original[0].value.endswith("\n")):
            text = _TRAILING_NEWLINES.sub("", text)
        # a single line of JSON, and CSV / TSV, do not end with a newline
        if (prefs.format == "json" and prefs.indent == 0) or prefs.format in ("csv", "tsv"):
            text = _TRAILING_NEWLINES.sub("", text)
        results.append(candidate.create_replacement(Kind.SCALAR, "!!str", text))
    return ctx.child(results)


# ----------------------------------------------------------------------------- decode

def _decode_with_format(nav: Navigator, text: str, name: str) -> Node:
    decoder = nav.env.formats.decoder_for(name, nav.env.options)
    for document in decoder.decode_documents(text):
        return document
    return Node.null(value="")


@operator("DECODE")
def decode_operator(nav: Navigator, ctx: Context, expr: ExprNode) -> Context:
    prefs = expr.operation.prefs
    assert isinstance(prefs, DecoderPrefs)
    results: list[Node] = []
    for candidate in ctx.nodes:
        ctx.remember(_decoded_key(candidate), (candidate,))
        if prefs.format == "base64":
            node = Node.string(decode_base64(candidate.value))
        elif prefs.format == "uri":
            node = Node.string(decode_uri(candidate.value))
        else:
            node = _decode_with_format(nav, candidate.value, prefs.format)
        node.key = candidate.key
        node.parent = candidate.parent
        if candidate.parent is None:                 # a root has no parent to tell it its document
            node.document_index = candidate.document_index
            node.file_index = candidate.file_index
            node.filename = candidate.filename
        results.append(node)
    return ctx.child(results)
