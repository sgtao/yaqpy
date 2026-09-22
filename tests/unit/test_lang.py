"""Lexer / postfix / tree tests (design doc 6)."""

from __future__ import annotations

import pytest
from yaqpy.core.lang.lex_rules import process_escape_characters
from yaqpy.core.lang.lexer import tokenize
from yaqpy.core.lang.parser import ExpressionCompiler, parse_expression
from yaqpy.core.operators import builtin_registry
from yaqpy.errors import ExpressionSyntaxError

REG = builtin_registry()


def types(expression: str) -> list[str]:
    return [t.operation.spec.type if t.operation else t.kind.value
            for t in tokenize(expression, REG.get)]


class LexerTests:
    def test_path_is_split_with_short_pipes(self) -> None:
        assert types(".a.b") == ["TRAVERSE_PATH", "SHORT_PIPE", "TRAVERSE_PATH"]

    def test_index_inserts_traverse_array(self) -> None:
        assert types(".a[0]") == ["TRAVERSE_PATH", "TRAVERSE_ARRAY", "[", "VALUE", "]"]

    def test_dot_bracket_becomes_self_traverse(self) -> None:
        assert types(".[]") == ["SELF", "TRAVERSE_ARRAY", "[", "EMPTY", "]"]

    def test_longest_name_first(self) -> None:
        # `keys` must not be lexed as `key` + `s`
        assert types("keys") == ["KEYS"]
        assert types("sort_by(.a)") == ["SORT_BY", "(", "TRAVERSE_PATH", ")"]

    def test_assign_tag_merges_tokens(self) -> None:
        assert types('tag = "!!str"') == ["ASSIGN_TAG", "STRING_INT"]
        assert types("tag |= .") == ["ASSIGN_TAG", "SELF"]

    def test_slice_implicit_bounds(self) -> None:
        assert types(".[1:]") == ["SELF", "TRAVERSE_ARRAY", "[", "VALUE", "CREATE_MAP", "LENGTH", "]"]
        assert types(".[:2]") == ["SELF", "TRAVERSE_ARRAY", "[", "VALUE", "CREATE_MAP", "VALUE", "]"]

    def test_literals(self) -> None:
        toks = tokenize('0x1F, 1.5, -2, true, null, "s"', REG.get)
        values = [t.operation.node.value for t in toks if t.is_op("VALUE") or t.is_op("STRING_INT")]
        assert values == ["0x1F", "1.5", "-2", "true", "null", "s"]
        tags = [t.operation.node.tag for t in toks if t.is_op("VALUE") or t.is_op("STRING_INT")]
        assert tags == ["!!int", "!!float", "!!int", "!!bool", "!!null", "!!str"]

    def test_multiply_flags(self) -> None:
        tok = tokenize(".a *+ .b", REG.get)[1]
        assert tok.operation.prefs.append_arrays
        tok = tokenize(".a *=nc .b", REG.get)[1]
        assert tok.operation.prefs.assign.only_write_null
        assert tok.operation.prefs.assign.clobber_custom_tags

    def test_unknown_character(self) -> None:
        with pytest.raises(ExpressionSyntaxError) as ctx:
            tokenize(".a ^ 1", REG.get)
        assert ctx.value.position == 3

    def test_escape_characters(self) -> None:
        assert process_escape_characters(r"a\nb\"c\\d") == 'a\nb"c\\d'
        assert process_escape_characters(r"\\(x)") == r"\\(x)"


class ParserTests:
    def test_precedence_assign_binds_tighter_than_pipe(self) -> None:
        root = parse_expression('.a = "cat" | .b = "dog"', REG.get)
        assert root.operation.spec.type == "PIPE"
        assert root.lhs.operation.spec.type == "ASSIGN"
        assert root.rhs.operation.spec.type == "ASSIGN"

    def test_union_is_lowest(self) -> None:
        root = parse_expression(".a, .b | .c", REG.get)
        assert root.operation.spec.type == "UNION"

    def test_collect_object(self) -> None:
        root = parse_expression('{"a": .b}', REG.get)
        assert root.operation.spec.type == "SHORT_PIPE"
        assert root.lhs.operation.spec.type == "CREATE_MAP"
        assert root.rhs.operation.spec.type == "COLLECT_OBJECT"

    def test_missing_bracket(self) -> None:
        with pytest.raises(ExpressionSyntaxError):
            parse_expression("(.a", REG.get)
        with pytest.raises(ExpressionSyntaxError):
            parse_expression(".a]", REG.get)
        with pytest.raises(ExpressionSyntaxError):
            parse_expression("[.a", REG.get)

    def test_arity_error(self) -> None:
        with pytest.raises(ExpressionSyntaxError) as ctx:
            parse_expression(".a =", REG.get)
        assert "expects 2 args" in ctx.value.message

    def test_empty_expression(self) -> None:
        assert parse_expression("", REG.get) is None

    def test_compiler_caches(self) -> None:
        compiler = ExpressionCompiler(REG.get)
        assert compiler.compile(".a") is compiler.compile(".a")
