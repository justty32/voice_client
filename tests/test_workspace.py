"""Workspace 抽象的單元測試。執行：python3 -m unittest tests.test_workspace"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from workspace import Workspace


class TestWorkspaceCRUD(unittest.TestCase):
    def test_append_coerces_str_to_entry(self):
        ws = Workspace("t")
        idx = ws.append("hello")
        self.assertEqual(idx, 0)
        self.assertEqual(ws.read(0), ["hello"])
        self.assertEqual(ws.count(), 1)

    def test_append_list_entry(self):
        ws = Workspace("t")
        ws.append(["seg1", "seg2"])
        self.assertEqual(ws.read(0), ["seg1", "seg2"])

    def test_append_coerces_non_str_segments(self):
        ws = Workspace("t")
        ws.append([1, 2, 3])
        self.assertEqual(ws.read(0), ["1", "2", "3"])

    def test_read_out_of_range(self):
        ws = Workspace("t")
        self.assertIsNone(ws.read(0))
        self.assertIsNone(ws.read(-1))

    def test_read_all_returns_copies(self):
        ws = Workspace("t")
        ws.append("a")
        snapshot = ws.read_all()
        snapshot[0].append("mutated")
        self.assertEqual(ws.read(0), ["a"])  # 內部不應被外部複本影響

    def test_extend(self):
        ws = Workspace("t")
        n = ws.extend(["a", "b", ["c", "d"]])
        self.assertEqual(n, 3)
        self.assertEqual(ws.count(), 3)
        self.assertEqual(ws.read(2), ["c", "d"])

    def test_replace(self):
        ws = Workspace("t")
        ws.append("a")
        self.assertTrue(ws.replace(0, "b"))
        self.assertEqual(ws.read(0), ["b"])
        self.assertFalse(ws.replace(5, "x"))

    def test_delete(self):
        ws = Workspace("t", ["a", "b", "c"])
        self.assertTrue(ws.delete(1))
        self.assertEqual(ws.lines(), ["a", "c"])
        self.assertFalse(ws.delete(9))

    def test_clear(self):
        ws = Workspace("t", ["a", "b"])
        self.assertEqual(ws.clear(), 2)
        self.assertTrue(ws.is_empty())


class TestWorkspaceReorder(unittest.TestCase):
    def test_concat_all_matches_old_buffer_behavior(self):
        ws = Workspace("t", ["a", "b", "c"])
        self.assertTrue(ws.concat_all(" "))
        self.assertEqual(ws.count(), 1)
        self.assertEqual(ws.read(0), ["a b c"])

    def test_concat_all_flattens_multisegment_entries(self):
        ws = Workspace("t")
        ws.append(["a", "b"])
        ws.append(["c"])
        ws.concat_all(" ")
        self.assertEqual(ws.read(0), ["a b c"])

    def test_concat_empty_returns_false(self):
        ws = Workspace("t")
        self.assertFalse(ws.concat_all())

    def test_move_to_top_default_last(self):
        ws = Workspace("t", ["a", "b", "c"])
        self.assertTrue(ws.move_to_top())  # 預設移動最後一筆
        self.assertEqual(ws.lines(), ["c", "a", "b"])

    def test_move_to_top_specific(self):
        ws = Workspace("t", ["a", "b", "c"])
        self.assertTrue(ws.move_to_top(1))
        self.assertEqual(ws.lines(), ["b", "a", "c"])

    def test_move_to_top_needs_two(self):
        ws = Workspace("t", ["a"])
        self.assertFalse(ws.move_to_top())

    def test_move(self):
        ws = Workspace("t", ["a", "b", "c"])
        self.assertTrue(ws.move(0, 2))
        self.assertEqual(ws.lines(), ["b", "c", "a"])
        self.assertFalse(ws.move(0, 9))


class TestWorkspaceFlattenAndSerialize(unittest.TestCase):
    def test_flatten(self):
        ws = Workspace("t")
        ws.append(["a", "b"])
        ws.append("c")
        self.assertEqual(ws.flatten(seg_sep="-", entry_sep=" "), "a-b c")

    def test_lines(self):
        ws = Workspace("t")
        ws.append(["a", "b"])
        ws.append("c")
        self.assertEqual(ws.lines("-"), ["a-b", "c"])

    def test_to_from_list_roundtrip(self):
        ws = Workspace("t", [["a", "b"], ["c"]])
        data = ws.to_list()
        ws2 = Workspace.from_list("t2", data)
        self.assertEqual(ws2.to_list(), [["a", "b"], ["c"]])

    def test_from_list_old_flat_format(self):
        # 舊 buffer 格式：List[str]
        ws = Workspace.from_list("t", ["a", "b"])
        self.assertEqual(ws.to_list(), [["a"], ["b"]])


class TestWorkspacePersistence(unittest.TestCase):
    def test_export_import_json_roundtrip(self):
        ws = Workspace("t", [["a", "b"], ["c"]])
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "out.json")
            ws.export(path)
            ws2 = Workspace("t2")
            added = ws2.import_file(path)
            self.assertEqual(added, 2)
            self.assertEqual(ws2.to_list(), [["a", "b"], ["c"]])

    def test_export_import_txt(self):
        ws = Workspace("t", [["a", "b"], ["c"]])
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "out.txt")
            ws.export(path, seg_sep=" ")
            ws2 = Workspace("t2")
            ws2.import_file(path)
            self.assertEqual(ws2.lines(), ["a b", "c"])

    def test_import_old_flat_json(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "old.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write('["a", "b"]')
            ws = Workspace("t")
            ws.import_file(path)
            self.assertEqual(ws.to_list(), [["a"], ["b"]])

    def test_import_appends_by_default(self):
        ws = Workspace("t", ["x"])
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "out.json")
            Workspace("o", ["a", "b"]).export(path)
            ws.import_file(path)  # append
            self.assertEqual(ws.lines(), ["x", "a", "b"])
            ws.import_file(path, append=False)  # replace
            self.assertEqual(ws.lines(), ["a", "b"])

    def test_import_rejects_non_list_json(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "bad.json")
            with open(path, "w", encoding="utf-8") as f:
                f.write('{"not": "a list"}')
            ws = Workspace("t")
            with self.assertRaises(ValueError):
                ws.import_file(path)


if __name__ == "__main__":
    unittest.main()
