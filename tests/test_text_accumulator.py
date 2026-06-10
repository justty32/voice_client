"""TextAccumulator 重構後的行為對照測試（buffer 工作區）。

執行：python3 -m unittest tests.test_text_accumulator
"""

import configparser
import os
import sys
import tempfile
import time
import unittest
from queue import Empty, Queue

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from text_accumulator import TextAccumulator


class TextAccumulatorTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        cfg = configparser.ConfigParser()
        cfg["WORKSPACE"] = {"export_file": os.path.join(self._tmp.name, "export.json")}
        self.input_q: Queue = Queue()
        self.cmd_q: Queue = Queue()
        self.out_q: Queue = Queue()
        self.acc = TextAccumulator(cfg, self.input_q, self.cmd_q, self.out_q)

    def tearDown(self):
        self._tmp.cleanup()

    def seed(self, *texts):
        for t in texts:
            self.acc._ws.append(t)

    def drain(self):
        msgs = []
        while True:
            try:
                msgs.append(self.out_q.get_nowait())
            except Empty:
                break
        return msgs

    def last_text(self):
        msgs = self.drain()
        return msgs[-1]["text"] if msgs else None


class TestFlush(TextAccumulatorTestBase):
    def test_flush_joins_with_space(self):
        self.seed("hello", "world")
        self.acc._flush()
        msg = self.out_q.get_nowait()
        self.assertEqual(msg["type"], "payload")
        self.assertEqual(msg["payload"]["Content"], "hello world")
        self.assertTrue(self.acc._ws.is_empty())

    def test_flush_empty_no_output(self):
        self.acc._flush()
        self.assertEqual(self.drain(), [])

    def test_flush_whitespace_only_no_payload(self):
        self.seed("   ", "")
        self.acc._flush()
        # 全空白 → 不送出 payload；buffer 仍被清空
        self.assertEqual(self.drain(), [])
        self.assertTrue(self.acc._ws.is_empty())


class TestPeek(TextAccumulatorTestBase):
    def test_peek_format(self):
        self.seed("a", "b")
        self.acc._peek()
        text = self.last_text()
        self.assertIn("[暫存區 · 2 筆]", text)
        self.assertIn("[1] a", text)
        self.assertIn("[2] b", text)

    def test_peek_empty(self):
        self.acc._peek()
        self.assertEqual(self.last_text(), "[暫存區是空的]")


class TestClearConcatToTop(TextAccumulatorTestBase):
    def test_clear(self):
        self.seed("a", "b")
        self.acc._clear()
        self.assertIn("原含 2 筆", self.last_text())
        self.assertTrue(self.acc._ws.is_empty())

    def test_concat(self):
        self.seed("a", "b", "c")
        self.acc._concat()
        self.assertIn("將 3 筆壓縮為 1 筆", self.last_text())
        self.assertEqual(self.acc._ws.count(), 1)
        self.assertEqual(self.acc._ws.lines(), ["a b c"])

    def test_concat_empty_no_output(self):
        self.acc._concat()
        self.assertEqual(self.drain(), [])

    def test_to_top(self):
        self.seed("a", "b", "c")
        self.acc._to_top()
        self.assertIn("移至最前方", self.last_text())
        self.assertEqual(self.acc._ws.lines(), ["c", "a", "b"])

    def test_to_top_fewer_than_two_no_output(self):
        self.seed("a")
        self.acc._handle_cmd({"cmd": "to_top"})
        self.assertEqual(self.drain(), [])

    def test_to_top_with_index(self):
        self.seed("a", "b", "c")
        self.acc._handle_cmd({"cmd": "to_top", "args": ["2"]})
        self.assertIn("第 2 筆", self.last_text())
        self.assertEqual(self.acc._ws.lines(), ["b", "a", "c"])

    def test_to_top_bad_index(self):
        self.seed("a", "b")
        self.acc._handle_cmd({"cmd": "to_top", "args": ["x"]})
        self.assertIn("需為數字", self.last_text())

    def test_delete_by_index(self):
        self.seed("a", "b", "c")
        self.acc._handle_cmd({"cmd": "delete", "args": ["2"]})
        self.assertIn("已刪除暫存區第 2 筆", self.last_text())
        self.assertEqual(self.acc._ws.lines(), ["a", "c"])

    def test_delete_out_of_range(self):
        self.seed("a")
        self.acc._handle_cmd({"cmd": "delete", "args": ["5"]})
        self.assertIn("沒有第 5 筆", self.last_text())

    def test_delete_requires_index(self):
        self.seed("a")
        self.acc._handle_cmd({"cmd": "delete", "args": []})
        self.assertIn("用法: /del", self.last_text())

    def test_move_by_index(self):
        self.seed("a", "b", "c")
        self.acc._handle_cmd({"cmd": "move", "args": ["1", "3"]})
        self.assertIn("第 1 筆移到第 3 位", self.last_text())
        self.assertEqual(self.acc._ws.lines(), ["b", "c", "a"])

    def test_move_out_of_range(self):
        self.seed("a", "b")
        self.acc._handle_cmd({"cmd": "move", "args": ["1", "9"]})
        self.assertIn("超出範圍", self.last_text())

    def test_move_needs_two_args(self):
        self.seed("a", "b")
        self.acc._handle_cmd({"cmd": "move", "args": ["1"]})
        self.assertIn("用法: /move", self.last_text())


class TestExportImport(TextAccumulatorTestBase):
    def test_export_requires_filename(self):
        self.seed("a")
        self.acc._handle_cmd({"cmd": "export", "args": []})
        self.assertIn("請指定匯出檔名", self.last_text())

    def test_export_import_json_roundtrip(self):
        self.seed("alpha", "beta")
        self.acc._handle_cmd({"cmd": "export", "args": ["mydata"]})
        self.assertIn("已匯出至", self.last_text())
        # 清空後再匯入
        self.acc._ws.clear()
        self.acc._handle_cmd({"cmd": "import", "args": ["mydata"]})
        self.assertIn("匯入 2 筆資料", self.last_text())
        self.assertEqual(self.acc._ws.lines(), ["alpha", "beta"])

    def test_export_import_txt(self):
        self.seed("line1", "line2")
        self.acc._handle_cmd({"cmd": "export", "args": ["notes.txt"]})
        self.acc._ws.clear()
        self.acc._handle_cmd({"cmd": "import", "args": ["notes.txt"]})
        self.assertIn("匯入 2 行文字", self.last_text())
        self.assertEqual(self.acc._ws.lines(), ["line1", "line2"])

    def test_import_old_flat_json_compatible(self):
        # 舊扁平格式 ["a","b"] 仍可匯入
        path = os.path.join(self._tmp.name, "old.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write('["a", "b"]')
        self.acc._handle_cmd({"cmd": "import", "args": ["old.json"]})
        self.assertEqual(self.acc._ws.lines(), ["a", "b"])

    def test_import_missing_file(self):
        self.acc._handle_cmd({"cmd": "import", "args": ["nope.json"]})
        self.assertIn("找不到檔案", self.last_text())

    def test_import_bad_json_format_message(self):
        path = os.path.join(self._tmp.name, "bad.json")
        with open(path, "w", encoding="utf-8") as f:
            f.write('{"not": "a list"}')
        self.acc._handle_cmd({"cmd": "import", "args": ["bad.json"]})
        self.assertIn("應為 JSON 陣列", self.last_text())


class TestAutoSaveAndInput(TextAccumulatorTestBase):
    def test_stop_autosaves_buffer_temp(self):
        self.seed("keep", "this")
        self.acc.stop()
        temp = os.path.join(self._tmp.name, "_buffer_temp.json")
        self.assertTrue(os.path.exists(temp))
        # 預設 import（無參數）讀取暫存檔
        self.acc._ws.clear()
        self.acc._handle_cmd({"cmd": "import", "args": []})
        self.assertEqual(self.acc._ws.lines(), ["keep", "this"])

    def test_input_queue_appends_and_filters_blank(self):
        self.acc.start()
        try:
            self.input_q.put({"type": "text", "text": "real"})
            self.input_q.put({"type": "text", "text": "   "})  # 應被忽略
            self.input_q.put({"type": "other", "text": "ignored"})  # 非 text 型別
            # 輪詢等待背景執行緒處理
            deadline = time.time() + 2.0
            while time.time() < deadline and self.acc._ws.count() < 1:
                time.sleep(0.02)
        finally:
            self.acc.stop()
        self.assertEqual(self.acc._ws.lines(), ["real"])


if __name__ == "__main__":
    unittest.main()
