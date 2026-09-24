"""The lexer rule table (Go's ``lexer_participle.go``).

The order of the rules *is* the precedence of the lexer: the combined regular
expression tries alternatives left to right, exactly like participle's simple
lexer. Keep the order identical to the Go table.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, TypeAlias

from yaqpy.core.lang import prefs as P
from yaqpy.core.lang.ast import Operation
from yaqpy.core.lang.tokens import Token, TokenKind
from yaqpy.core.model.node import Node
from yaqpy.errors import ExpressionSyntaxError

# An action receives the matched text and a registry lookup and returns a Token.
LexAction: TypeAlias = Callable[[str, Callable[[str], Any]], Token] | None


@dataclass(frozen=True, slots=True)
class LexRule:
    name: str
    pattern: str
    action: LexAction


# ----------------------------------------------------------------------------- actions


def _op(name: str, prefs: Any = None, *, assign: str | None = None) -> LexAction:
    def action(text: str, get: Callable[[str], Any]) -> Token:
        spec = get(name)
        op = Operation(spec, value=spec.type, string_value=text, prefs=prefs)
        assign_op = None
        if assign is not None:
            aspec = get(assign)
            assign_op = Operation(aspec, value=aspec.type, string_value=text, prefs=prefs)
        return Token(TokenKind.OPERATION, op, assign_op, spec.check_for_post_traverse, text)

    return action


def _literal(kind: TokenKind, check_for_post: bool) -> LexAction:
    def action(text: str, get: Callable[[str], Any]) -> Token:
        return Token(kind, check_for_post_traverse=check_for_post, match=text)

    return action


def _value(value: Any, text: str, get: Callable[[str], Any]) -> Token:
    op = Operation(get("VALUE"), value=value, string_value=text, node=Node.from_value(value, text))
    return Token(TokenKind.OPERATION, op, match=text)


def _hex(text: str, get: Callable[[str], Any]) -> Token:
    return _value(int(text[2:], 16), text, get)


def _float(text: str, get: Callable[[str], Any]) -> Token:
    return _value(float(text), text, get)


def _number(text: str, get: Callable[[str], Any]) -> Token:
    return _value(int(text, 10), text, get)


def _boolean(flag: bool) -> LexAction:
    def action(text: str, get: Callable[[str], Any]) -> Token:
        return _value(flag, text, get)

    return action


def _null(text: str, get: Callable[[str], Any]) -> Token:
    return _value(None, text, get)


def process_escape_characters(original: str) -> str:
    """Go's ``processEscapeCharacters`` for double-quoted expression strings."""
    if original == "":
        return original
    out: list[str] = []
    i = 0
    n = len(original)
    simple = {
        '"': '"', "n": "\n", "t": "\t", "r": "\r", "f": "\f", "v": "\v", "b": "\b", "a": "\a",
    }
    while i < n:
        ch = original[i]
        if ch == "\\" and i < n - 1:
            nxt = original[i + 1]
            if nxt == "\\":
                if i + 2 < n and original[i + 2] == "(":
                    out.append("\\\\")
                    i += 2
                    continue
                out.append("\\")
                i += 2
                continue
            if nxt in simple:
                out.append(simple[nxt])
                i += 2
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _string(text: str, get: Callable[[str], Any]) -> Token:
    value = process_escape_characters(text[1:-1])
    op = Operation(get("STRING_INT"), value=value, string_value=value,
                   node=Node.from_value(value, value))
    return Token(TokenKind.OPERATION, op, match=text)


def _path(wrapped: bool) -> LexAction:
    def action(text: str, get: Callable[[str], Any]) -> Token:
        value = text
        optional = False
        if value.endswith("?"):
            optional = True
            value = value[:-1]
        value = value[1:]
        if wrapped:
            value = value[1:-1]
        prefs = P.TraversePrefs(optional_traverse=optional)
        op = Operation(get("TRAVERSE_PATH"), value=value, string_value=value, prefs=prefs)
        return Token(TokenKind.OPERATION, op, check_for_post_traverse=True, match=text)

    return action


def _recursive_descent(include_map_keys: bool) -> LexAction:
    prefs = P.RecursiveDescentPrefs(
        traverse=P.TraversePrefs(dont_follow_alias=True, include_map_keys=include_map_keys),
        recurse_array=True,
    )
    return _op("RECURSIVE_DESCENT", prefs)


def _get_variable(text: str, get: Callable[[str], Any]) -> Token:
    name = text[1:]
    op = Operation(get("GET_VARIABLE"), value=name, string_value=name,
                   node=Node.from_value(name, name))
    return Token(TokenKind.OPERATION, op, check_for_post_traverse=True, match=text)


def _assign(update: bool) -> LexAction:
    def action(text: str, get: Callable[[str], Any]) -> Token:
        prefs = P.AssignPrefs(dont_overwrite_anchor=True, clobber_custom_tags="c" in text)
        op = Operation(get("ASSIGN"), value="ASSIGN", string_value=text, prefs=prefs,
                       update_assign=update)
        return Token(TokenKind.OPERATION, op, match=text)

    return action


def _multiply(name: str) -> LexAction:
    def action(text: str, get: Callable[[str], Any]) -> Token:
        traverse = P.TraversePrefs(
            dont_auto_create="?" in text, dont_follow_alias=True, exact_key_match=True
        )
        assign = P.AssignPrefs(only_write_null="n" in text, clobber_custom_tags="c" in text)
        prefs = P.MultiplyPrefs(
            append_arrays="+" in text, deep_merge_arrays="d" in text,
            traverse=traverse, assign=assign,
        )
        op = Operation(get(name), value="MULTIPLY", string_value=text, prefs=prefs)
        return Token(TokenKind.OPERATION, op, match=text)

    return action


def _all_comments(update: bool) -> LexAction:
    def action(text: str, get: Callable[[str], Any]) -> Token:
        prefs = P.CommentPrefs(line_comment=True, head_comment=True, foot_comment=True)
        op = Operation(get("ASSIGN_COMMENT"), value="ASSIGN_COMMENT", string_value=text,
                       update_assign=update, prefs=prefs)
        return Token(TokenKind.OPERATION, op, match=text)

    return action


def _comment(**kw: bool) -> LexAction:
    return _op("GET_COMMENT", P.CommentPrefs(**kw), assign="ASSIGN_COMMENT")


def _env(strenv: bool) -> LexAction:
    def action(text: str, get: Callable[[str], Any]) -> Token:
        name = text[7:-1] if strenv else text[4:-1]
        op = Operation(get("ENV"), value=name, string_value=name,
                       node=Node.from_value(name, name), prefs=P.EnvPrefs(string_value=strenv))
        return Token(TokenKind.OPERATION, op, check_for_post_traverse=True, match=text)

    return action


_NUMBER_PARAM = re.compile(r".*\((-?[0-9]+)\)")


def _extract_number(text: str) -> int:
    m = _NUMBER_PARAM.match(text)
    if m is None:
        raise ExpressionSyntaxError(f"could not parse number parameter in {text}")
    return int(m.group(1))


def _parent_with_level(text: str, get: Callable[[str], Any]) -> Token:
    prefs = P.ParentPrefs(level=_extract_number(text))
    op = Operation(get("GET_PARENT"), value="GET_PARENT", string_value=text, prefs=prefs)
    return Token(TokenKind.OPERATION, op, check_for_post_traverse=True, match=text)


def _parent_default(text: str, get: Callable[[str], Any]) -> Token:
    op = Operation(get("GET_PARENT"), value="GET_PARENT", string_value="GET_PARENT",
                   prefs=P.ParentPrefs(level=1))
    return Token(TokenKind.OPERATION, op, check_for_post_traverse=True, match=text)


def _flatten_with_depth(text: str, get: Callable[[str], Any]) -> Token:
    prefs = P.FlattenPrefs(depth=_extract_number(text))
    spec = get("FLATTEN_BY")
    op = Operation(spec, value=spec.type, string_value=text, prefs=prefs)
    return Token(TokenKind.OPERATION, op, check_for_post_traverse=spec.check_for_post_traverse,
                 match=text)


def _expression(expression: str) -> LexAction:
    def action(text: str, get: Callable[[str], Any]) -> Token:
        op = Operation(get("EXP"), prefs=P.ExpressionPrefs(expression))
        return Token(TokenKind.OPERATION, op, match=text)

    return action


def _encode(fmt: str, indent: int) -> LexAction:
    return _op("ENCODE", P.EncoderPrefs(fmt, indent))


def _encode_parse_indent(fmt: str) -> LexAction:
    def action(text: str, get: Callable[[str], Any]) -> Token:
        op = Operation(get("ENCODE"), value="ENCODE", string_value=text,
                       prefs=P.EncoderPrefs(fmt, _extract_number(text)))
        return Token(TokenKind.OPERATION, op, match=text)

    return action


def _decode(fmt: str) -> LexAction:
    return _op("DECODE", P.DecoderPrefs(fmt))


def _load(fmt: str) -> LexAction:
    return _op("LOAD", P.DecoderPrefs(fmt))


def _simple(name: str, op_type: str) -> LexRule:
    return LexRule(name[0].upper() + name[1:], name, _op(op_type))


def _assignable(name: str, get_type: str, assign_type: str) -> LexRule:
    return LexRule(name[0].upper() + name[1:], name, _op(get_type, assign=assign_type))


# ----------------------------------------------------------------------------- the table

DEFAULT_RULES: tuple[LexRule, ...] = (
    LexRule("LINE_COMMENT", r"line_?comment|lineComment", _comment(line_comment=True)),
    LexRule("HEAD_COMMENT", r"head_?comment|headComment", _comment(head_comment=True)),
    LexRule("FOOT_COMMENT", r"foot_?comment|footComment", _comment(foot_comment=True)),
    LexRule("OpenBracket", r"\(", _literal(TokenKind.OPEN_BRACKET, False)),
    LexRule("CloseBracket", r"\)", _literal(TokenKind.CLOSE_BRACKET, True)),
    LexRule("OpenTraverseArrayCollect", r"\.\[", _literal(TokenKind.TRAVERSE_ARRAY_COLLECT, False)),
    LexRule("OpenCollect", r"\[", _literal(TokenKind.OPEN_COLLECT, False)),
    LexRule("CloseCollect", r"\]\??", _literal(TokenKind.CLOSE_COLLECT, True)),
    LexRule("OpenCollectObject", r"\{", _literal(TokenKind.OPEN_COLLECT_OBJECT, False)),
    LexRule("CloseCollectObject", r"\}", _literal(TokenKind.CLOSE_COLLECT_OBJECT, True)),
    LexRule("RecursiveDecentIncludingKeys", r"\.\.\.", _recursive_descent(True)),
    LexRule("RecursiveDecent", r"\.\.", _recursive_descent(False)),
    LexRule("GetVariable", r"\$[a-zA-Z_\-0-9]+", _get_variable),
    # not when a longer word follows: "ascii_downcase" must not start with the keyword "as"
    LexRule("AssignAsVariable", r"as(?![A-Za-z0-9_])", _op("ASSIGN_VARIABLE", P.AssignVarPrefs())),
    LexRule("AssignRefVariable", r"ref(?![A-Za-z0-9_])",
            _op("ASSIGN_VARIABLE", P.AssignVarPrefs(is_reference=True))),
    LexRule("CreateMap", r":\s*", _op("CREATE_MAP")),
    _simple("length", "LENGTH"),
    _simple("schema", "SCHEMA"),
    _simple("prune_?null", "PRUNE_NULL"),
    _simple("prune_?empty", "PRUNE_EMPTY"),
    _simple("line", "LINE"),
    _simple("column", "COLUMN"),
    _simple("eval", "EVAL"),
    _simple("to_?number", "TO_NUMBER"),
    LexRule("MapValues", r"map_?values", _op("MAP_VALUES")),
    _simple("map", "MAP"),
    _simple("filter", "FILTER"),
    _simple("pick", "PICK"),
    _simple("omit", "OMIT"),
    LexRule("FlattenWithDepth", r"flatten\([0-9]+\)", _flatten_with_depth),
    LexRule("Flatten", r"flatten", _op("FLATTEN_BY", P.FlattenPrefs(depth=-1))),
    _simple("format_datetime", "FORMAT_DATE_TIME"),
    _simple("now", "NOW"),
    _simple("tz", "TIMEZONE"),
    _simple("from_?unix", "FROM_UNIX"),
    _simple("to_?unix", "TO_UNIX"),
    _simple("with_dtf", "WITH_DATE_TIME_FORMAT"),
    _simple("error", "ERROR"),
    _simple("shuffle", "SHUFFLE"),
    _simple("sortKeys", "SORT_KEYS"),
    _simple("sort_?keys", "SORT_KEYS"),
    LexRule("ArrayToMap", r"array_?to_?map",
            _expression("(.[] | select(. != null) ) as $i ireduce({}; .[$i | key] = $i)")),
    LexRule("Root", r"root", _expression("parent(-1)")),
    LexRule("YamlEncodeWithIndent", r"to_?yaml\([0-9]+\)", _encode_parse_indent("yaml")),
    LexRule("XMLEncodeWithIndent", r"to_?xml\([0-9]+\)", _encode_parse_indent("xml")),
    LexRule("JSONEncodeWithIndent", r"to_?json\([0-9]+\)", _encode_parse_indent("json")),
    LexRule("YamlDecode", r"from_?yaml|@yamld|from_?json|@jsond", _decode("yaml")),
    LexRule("YamlEncode", r"to_?yaml|@yaml", _encode("yaml", 2)),
    LexRule("JSONEncode", r"to_?json", _encode("json", 2)),
    LexRule("JSONEncodeNoIndent", r"@json", _encode("json", 0)),
    LexRule("PropertiesDecode", r"from_?props|@propsd", _decode("props")),
    LexRule("PropsEncode", r"to_?props|@props", _encode("props", 2)),
    LexRule("XmlDecode", r"from_?xml|@xmld", _decode("xml")),
    LexRule("XMLEncode", r"to_?xml", _encode("xml", 2)),
    LexRule("XMLEncodeNoIndent", r"@xml", _encode("xml", 0)),
    LexRule("CSVDecode", r"from_?csv|@csvd", _decode("csv")),
    LexRule("CSVEncode", r"to_?csv|@csv", _encode("csv", 0)),
    LexRule("TSVDecode", r"from_?tsv|@tsvd", _decode("tsv")),
    LexRule("TSVEncode", r"to_?tsv|@tsv", _encode("tsv", 0)),
    LexRule("Base64d", r"@base64d", _decode("base64")),
    LexRule("Base64", r"@base64", _encode("base64", 0)),
    LexRule("Urid", r"@urid", _decode("uri")),
    LexRule("Uri", r"@uri", _encode("uri", 0)),
    LexRule("SH", r"@sh", _encode("sh", 0)),
    LexRule("LoadXML", r"load_?xml|xml_?load", _load("xml")),
    LexRule("LoadBase64", r"load_?base64", _load("base64")),
    LexRule("LoadProperties", r"load_?props", _load("props")),
    _simple("load_?str|str_?load", "LOAD_STRING"),
    LexRule("LoadYaml", r"load", _load("yaml")),
    _simple("system", "SYSTEM"),
    LexRule("SplitDocument", r"splitDoc|split_?doc", _op("SPLIT_DOC")),
    _simple("select", "SELECT"),
    _simple("has", "HAS"),
    _simple("unique_?by", "UNIQUE_BY"),
    _simple("unique", "UNIQUE"),
    _simple("group_?by", "GROUP_BY"),
    _simple("explode", "EXPLODE"),
    _simple("or", "OR"),
    _simple("and", "AND"),
    _simple("not", "NOT"),
    _simple("ireduce", "REDUCE"),
    _simple("join", "JOIN"),
    _simple("sub", "SUBSTR"),
    _simple("match", "MATCH"),
    _simple("capture", "CAPTURE"),
    _simple("test", "TEST"),
    _simple("sort_?by", "SORT_BY"),
    _simple("sort", "SORT"),
    _simple("first", "FIRST"),
    _simple("reverse", "REVERSE"),
    _simple("any_c", "ANY_CONDITION"),
    _simple("any", "ANY"),
    _simple("all_c", "ALL_CONDITION"),
    _simple("all", "ALL"),
    _simple("contains", "CONTAINS"),
    _simple("split", "SPLIT"),
    _simple("parents", "GET_PARENTS"),
    LexRule("ParentWithLevel", r"parent\(-?[0-9]+\)", _parent_with_level),
    LexRule("ParentWithDefaultLevel", r"parent", _parent_default),
    _simple("keys", "KEYS"),
    _simple("key", "GET_KEY"),
    _simple("is_?key", "IS_KEY"),
    _simple("file_?name|fileName", "GET_FILENAME"),
    _simple("file_?index|fileIndex|fi", "GET_FILE_INDEX"),
    _simple("path", "GET_PATH"),
    _simple("set_?path", "SET_PATH"),
    _simple("del_?paths", "DEL_PATHS"),
    _simple("to_?entries|toEntries", "TO_ENTRIES"),
    _simple("from_?entries|fromEntries", "FROM_ENTRIES"),
    _simple("with_?entries|withEntries", "WITH_ENTRIES"),
    _simple("with", "WITH"),
    _simple("collect", "COLLECT"),
    _simple("del", "DELETE"),
    _assignable("style", "GET_STYLE", "ASSIGN_STYLE"),
    _assignable("tag|type", "GET_TAG", "ASSIGN_TAG"),
    _simple("kind", "GET_KIND"),
    _assignable("anchor", "GET_ANCHOR", "ASSIGN_ANCHOR"),
    _assignable("alias", "GET_ALIAS", "ASSIGN_ALIAS"),
    LexRule("ALL_COMMENTS", r"comments\s*=", _all_comments(False)),
    LexRule("ALL_COMMENTS_ASSIGN_RELATIVE", r"comments\s*\|=", _all_comments(True)),
    LexRule("Block", r";", _op("BLOCK")),
    LexRule("Alternative", r"\/\/", _op("ALTERNATIVE")),
    LexRule("DocumentIndex", r"documentIndex|document_?index|di", _op("GET_DOCUMENT_INDEX")),
    LexRule("Uppercase", r"upcase|ascii_?upcase", _op("CHANGE_CASE", True)),
    LexRule("Downcase", r"downcase|ascii_?downcase", _op("CHANGE_CASE", False)),
    _simple("trim", "TRIM"),
    _simple("to_?string", "TO_STRING"),
    LexRule("HexValue", r"0[xX][0-9A-Fa-f]+", _hex),
    LexRule("FloatValueScientific", r"-?[1-9](\.\d+)?[Ee][-+]?\d+", _float),
    LexRule("FloatValue", r"-?\d+(\.\d+)", _float),
    LexRule("NumberValue", r"-?\d+", _number),
    LexRule("TrueBooleanValue", r"[Tt][Rr][Uu][Ee]", _boolean(True)),
    LexRule("FalseBooleanValue", r"[Ff][Aa][Ll][Ss][Ee]", _boolean(False)),
    LexRule("NullValue", r"[Nn][Uu][Ll][Ll]|~", _null),
    LexRule("QuotedStringValue", r'"([^"\\]*(\\.[^"\\]*)*)"', _string),
    LexRule("StrEnvOp", r"strenv\([^\)]+\)", _env(True)),
    LexRule("EnvOp", r"env\([^\)]+\)", _env(False)),
    LexRule("EnvSubstWithOptions", r"envsubst\((ne|nu|ff| |,)+\)", _op("ENVSUBST")),
    _simple("envsubst", "ENVSUBST"),
    LexRule("Equals", r"\s*==\s*", _op("EQUALS")),
    LexRule("NotEquals", r"\s*!=\s*", _op("NOT_EQUALS")),
    LexRule("GreaterThanEquals", r"\s*>=\s*", _op("COMPARE", P.ComparePrefs(or_equal=True, greater=True))),
    LexRule("LessThanEquals", r"\s*<=\s*", _op("COMPARE", P.ComparePrefs(or_equal=True, greater=False))),
    LexRule("GreaterThan", r"\s*>\s*", _op("COMPARE", P.ComparePrefs(or_equal=False, greater=True))),
    LexRule("LessThan", r"\s*<\s*", _op("COMPARE", P.ComparePrefs(or_equal=False, greater=False))),
    _simple("min", "MIN"),
    _simple("max", "MAX"),
    LexRule("AssignRelative", r"\|=[c]*", _assign(True)),
    LexRule("Assign", r"=[c]*", _assign(False)),
    LexRule("whitespace", r"[ \t\n]+", None),
    LexRule("WrappedPathElement", r'\."[^ "]+"\??', _path(True)),
    LexRule("PathElement", r"\.[^ ;\}\{\:\[\],\|\.\[\(\)=\n!]+\??", _path(False)),
    LexRule("Pipe", r"\|", _op("PIPE")),
    LexRule("Self", r"\.", _op("SELF")),
    LexRule("Union", r",", _op("UNION")),
    LexRule("MultiplyAssign", r"\*=[\+|\?cdn]*", _multiply("MULTIPLY_ASSIGN")),
    LexRule("Multiply", r"\*[\+|\?cdn]*", _multiply("MULTIPLY")),
    LexRule("Divide", r"\/", _op("DIVIDE")),
    LexRule("Modulo", r"%", _op("MODULO")),
    LexRule("AddAssign", r"\+=", _op("ADD_ASSIGN")),
    LexRule("Add", r"\+", _op("ADD")),
    LexRule("SubtractAssign", r"\-=", _op("SUBTRACT_ASSIGN")),
    LexRule("Subtract", r"\-", _op("SUBTRACT")),
    LexRule("Comment", r"#.*", None),
    _simple("pivot", "PIVOT"),
)


class LexRuleSet:
    """A compiled, ordered rule table. Immutable; share freely between threads."""

    def __init__(self, rules: tuple[LexRule, ...] = DEFAULT_RULES) -> None:
        self.rules = rules
        self._pattern = re.compile(
            "|".join(f"(?P<r{i}>(?:{rule.pattern}))" for i, rule in enumerate(rules))
        )

    def with_rules(self, *new_rules: LexRule, before: str | None = None) -> LexRuleSet:
        """Return a new rule set with ``new_rules`` inserted before rule ``before``
        (or appended when ``before`` is None)."""
        rules = list(self.rules)
        if before is None:
            rules.extend(new_rules)
        else:
            for i, rule in enumerate(rules):
                if rule.name == before:
                    rules[i:i] = list(new_rules)
                    break
            else:
                raise KeyError(f"no lex rule named {before}")
        return LexRuleSet(tuple(rules))

    def match(self, text: str, pos: int) -> tuple[LexRule, re.Match[str]] | None:
        m = self._pattern.match(text, pos)
        if m is None or m.end() == pos:
            return None
        assert m.lastgroup is not None
        return self.rules[int(m.lastgroup[1:])], m


DEFAULT_RULESET = LexRuleSet()
