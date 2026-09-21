"""The path-by-path comparison of a document before and after a conversion."""

from __future__ import annotations

import unittest

from yaqpy.recipes.diff import ADDED, CHANGED, MOVED, REMOVED, Change, diff, flatten


class FlattenTests(unittest.TestCase):
    def test_paths_of_maps_and_arrays(self) -> None:
        self.assertEqual(flatten({"a": {"b": 1}, "c": [10, {"d": "x"}]}),
                         {".a.b": 1, ".c[0]": 10, ".c[1].d": "x"})

    def test_empty_containers_and_scalars_are_leaves(self) -> None:
        self.assertEqual(flatten({"a": {}, "b": [], "c": None}), {".a": {}, ".b": [], ".c": None})
        self.assertEqual(flatten(5), {".": 5})


class DiffTests(unittest.TestCase):
    def test_identical_documents_have_no_changes(self) -> None:
        self.assertEqual(diff({"a": [1, 2]}, {"a": [1, 2]}), [])

    def test_added_removed_changed(self) -> None:
        got = diff({"a": 1, "b": 2, "c": 3}, {"a": 1, "b": 20, "d": 4})
        self.assertEqual(got, [
            Change(CHANGED, ".b", before=2, after=20),
            Change(REMOVED, ".c", before=3),
            Change(ADDED, ".d", after=4),
        ])

    def test_a_value_that_turns_up_elsewhere_is_a_move(self) -> None:
        got = diff({"max_tokens": 1024, "model": "m"}, {"generationConfig": {"maxOutputTokens": 1024}})
        self.assertEqual(got, [
            Change(MOVED, ".max_tokens", ".generationConfig.maxOutputTokens", before=1024, after=1024),
            Change(REMOVED, ".model", before="m"),
        ])

    def test_a_value_that_occurs_twice_is_not_paired(self) -> None:
        got = diff({"a": 7, "b": 7}, {"x": 7})
        self.assertEqual([c.kind for c in got], [REMOVED, REMOVED, ADDED])

    def test_booleans_null_and_empty_strings_are_never_paired(self) -> None:
        got = diff({"a": True, "b": None, "c": ""}, {"x": True, "y": None, "z": ""})
        self.assertEqual({c.kind for c in got}, {REMOVED, ADDED})

    def test_message_text_is_followed_through_a_restructure(self) -> None:
        before = {"messages": [{"role": "user", "content": "Hello"}]}
        after = {"contents": [{"role": "user", "parts": [{"text": "Hello"}]}]}
        moved = [c for c in diff(before, after) if c.kind == MOVED]
        self.assertIn((".messages[0].content", ".contents[0].parts[0].text"),
                      [(c.path, c.to_path) for c in moved])


if __name__ == "__main__":
    unittest.main()
