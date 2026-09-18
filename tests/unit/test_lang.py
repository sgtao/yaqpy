"""Lexer / postfix / tree tests (design doc 6)."""

from __future__ import annotations

import unittest

from yaqpy.core.lang.lex_rules import process_escape_characters
from yaqpy.core.lang.lexer import tokenize
from yaqpy.core.lang.parser import ExpressionCompiler, parse_expression
from yaqpy.core.operators import builtin_registry
from yaqpy.errors import ExpressionSyntaxError

REG = builtin_registry()


def types(expression: str) -> list[str]:
    return [t.operation.spec.type if t.operation else t.kind.value
            for t in tokenize(expression, REG.get)]


class LexerTests(unittest.TestCase):
    def test_path_is_split_with_short_pipes(self) -> None:
        self.assertEqual(types(".a.b"), ["TRAVERSE_PATH", "SHORT_PIPE", "TRAVERSE_PATH"])

    def test_index_inserts_traverse_array(self) -> None:
        self.assertEqual(types(".a[0]"),
                         ["TRAVERSE_PATH", "TRAVERSE_ARRAY", "[", "VALUE", "]"])

    def test_dot_bracket_becomes_self_traverse(self) -> None:
        self.assertEqual(types(".[]"), ["SELF", "TRAVERSE_ARRAY", "[", "EMPTY", "]"])

    def test_longest_name_first(self) -> None:
        # `keys` must not be lexed as `key` + `s`
        self.assertEqual(types("keys"), ["KEYS"])
        self.assertEqual(types("sort_by(.a)"), ["SORT_BY", "(", "TRAVERSE_PATH", ")"])

    def test_assign_tag_merges_tokens(self) -> None:
        self.assertEqual(types('tag = "!!str"'), ["ASSIGN_TAG", "STRING_INT"])
        self.assertEqual(types("tag |= ."), ["ASSIGN_TAG", "SELF"])

    def test_slice_implicit_bounds(self) -> None:
        self.assertEqual(types(".[1:]"),
                         ["SELF", "TRAVERSE_ARRAY", "[", "VALUE", "CREATE_MAP", "LENGTH", "]"])
        self.assertEqual(types(".[:2]"),
                         ["SELF", "TRAVERSE_ARRAY", "[", "VALUE", "CREATE_MAP", "VALUE", "]"])

    def test_literals(self) -> None:
        toks = tokenize('0x1F, 1.5, -2, true, null, "s"', REG.get)
        values = [t.operation.node.value for t in toks if t.is_op("VALUE") or t.is_op("STRING_INT")]
        self.assertEqual(values, ["0x1F", "1.5", "-2", "true", "null", "s"])
        tags = [t.operation.node.tag for t in toks if t.is_op("VALUE") or t.is_op("STRING_INT")]
        self.assertEqual(tags, ["!!int", "!!float", "!!int", "!!bool", "!!null", "!!str"])

    def test_multiply_flags(self) -> None:
        tok = tokenize(".a *+ .b", REG.get)[1]
        self.assertTrue(tok.operation.prefs.append_arrays)
        tok = tokenize(".a *=nc .b", REG.get)[1]
        self.assertTrue(tok.operation.prefs.assign.only_write_null)
        self.assertTrue(tok.operation.prefs.assign.clobber_custom_tags)

    def test_unknown_character(self) -> None:
        with self.assertRaises(ExpressionSyntaxError) as ctx:
            tokenize(".a ^ 1", REG.get)
        self.assertEqual(ctx.exception.position, 3)

    def test_escape_characters(self) -> None:
        self.assertEqual(process_escape_characters(r"a\nb\"c\\d"), 'a\nb"c\\d')
        self.assertEqual(process_escape_characters(r"\\(x)"), r"\\(x)")


class ParserTests(unittest.TestCase):
    def test_precedence_assign_binds_tighter_than_pipe(self) -> None:
        root = parse_expression('.a = "cat" | .b = "dog"', REG.get)
        self.assertEqual(root.operation.spec.type, "PIPE")
        self.assertEqual(root.lhs.operation.spec.type, "ASSIGN")
        self.assertEqual(root.rhs.operation.spec.type, "ASSIGN")

    def test_union_is_lowest(self) -> None:
        root = parse_expression(".a, .b | .c", REG.get)
        self.assertEqual(root.operation.spec.type, "UNION")

    def test_collect_object(self) -> None:
        root = parse_expression('{"a": .b}', REG.get)
        self.assertEqual(root.operation.spec.type, "SHORT_PIPE")
        self.assertEqual(root.lhs.operation.spec.type, "CREATE_MAP")
        self.assertEqual(root.rhs.operation.spec.type, "COLLECT_OBJECT")

    def test_missing_bracket(self) -> None:
        with self.assertRaises(ExpressionSyntaxError):
            parse_expression("(.a", REG.get)
        with self.assertRaises(ExpressionSyntaxError):
            parse_expression(".a]", REG.get)
        with self.assertRaises(ExpressionSyntaxError):
            parse_expression("[.a", REG.get)

    def test_arity_error(self) -> None:
        with self.assertRaises(ExpressionSyntaxError) as ctx:
            parse_expression(".a =", REG.get)
        self.assertIn("expects 2 args", ctx.exception.message)

    def test_empty_expression(self) -> None:
        self.assertIsNone(parse_expression("", REG.get))

    def test_compiler_caches(self) -> None:
        compiler = ExpressionCompiler(REG.get)
        self.assertIs(compiler.compile(".a"), compiler.compile(".a"))


if __name__ == "__main__":
    unittest.main()
