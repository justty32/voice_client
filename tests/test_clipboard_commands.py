"""剪貼簿指令 (/copy /paste) 的路由測試。

以 mock 取代實際剪貼簿後端，驗證 WorkspaceController 與 TextAccumulator 的行為。
執行：python3 -m unittest tests.test_clipboard_commands
"""

import configparser
import os
import sys
import tempfile
import unittest
from queue import Empty, Queue
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from session_manager import SessionManager
from text_accumulator import TextAccumulator
from workspace_controller import WorkspaceController


def make_sm(tmp: str) -> SessionManager:
    cfg = configparser.ConfigParser()
    cfg["WORKSPACE"] = {
        "sessions_file": os.path.join(tmp, "output", ".sessions.json"),
        "deleted_sessions_dir": os.path.join(tmp, "output", "deleted"),
    }
    sm = SessionManager(cfg)
    sm.new_session("default")
    return sm


class TestControllerClipboard(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.sm = make_sm(self._tmp.name)
        self.wc = WorkspaceController(self.sm)

    def tearDown(self):
        self._tmp.cleanup()

    def test_copy_buffer_delegates_to_queue(self):
        res = self.wc.handle_copy()  # current = buffer
        self.assertEqual(res.acc_cmds, [{"cmd": "copy"}])

    def test_paste_buffer_delegates_to_queue(self):
        res = self.wc.handle_paste()
        self.assertEqual(res.acc_cmds, [{"cmd": "paste"}])

    @mock.patch("utils.clipboard.copy", return_value=(True, ""))
    def test_copy_stt(self, mock_copy):
        self.wc.set_current("stt")
        self.wc.stt.append("hello")
        self.wc.stt.append(["a", "b"])
        res = self.wc.handle_copy()
        mock_copy.assert_called_once_with("hello\na b")
        self.assertIn("已複製 stt 工作區 2 筆", res.messages[0][1])

    @mock.patch("utils.clipboard.copy", return_value=(False, "找不到工具"))
    def test_copy_failure_message(self, mock_copy):
        self.wc.set_current("stt")
        self.wc.stt.append("x")
        res = self.wc.handle_copy()
        self.assertIn("[錯誤] 找不到工具", res.messages[0][1])

    def test_copy_stt_empty(self):
        self.wc.set_current("stt")
        res = self.wc.handle_copy()
        self.assertIn("空的", res.messages[0][1])

    @mock.patch("utils.clipboard.copy", return_value=(True, ""))
    def test_copy_chat(self, mock_copy):
        self.wc.set_current("chat")
        self.sm.add_message("user", "hi")
        res = self.wc.handle_copy()
        mock_copy.assert_called_once()
        self.assertIn("已複製對話歷史", res.messages[0][1])

    @mock.patch("utils.clipboard.paste", return_value=(True, "line1\n  \nline2\n"))
    def test_paste_stt_splits_lines(self, mock_paste):
        self.wc.set_current("stt")
        res = self.wc.handle_paste()
        self.assertEqual(self.wc.stt.lines(), ["line1", "line2"])
        self.assertIn("貼上 2 筆", res.messages[0][1])

    @mock.patch("utils.clipboard.paste", return_value=(False, "讀取失敗"))
    def test_paste_failure(self, mock_paste):
        self.wc.set_current("stt")
        res = self.wc.handle_paste()
        self.assertIn("[錯誤] 讀取失敗", res.messages[0][1])
        self.assertTrue(self.wc.stt.is_empty())

    def test_paste_chat_unsupported(self):
        self.wc.set_current("chat")
        res = self.wc.handle_paste()
        self.assertIn("不支援貼上", res.messages[0][1])


class TestAccumulatorClipboard(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        cfg = configparser.ConfigParser()
        cfg["WORKSPACE"] = {"export_file": os.path.join(self._tmp.name, "export.json")}
        self.out_q: Queue = Queue()
        self.acc = TextAccumulator(cfg, Queue(), Queue(), self.out_q)

    def tearDown(self):
        self._tmp.cleanup()

    def last_text(self):
        msgs = []
        while True:
            try:
                msgs.append(self.out_q.get_nowait())
            except Empty:
                break
        return msgs[-1]["text"] if msgs else None

    @mock.patch("text_accumulator.clipboard.copy", return_value=(True, ""))
    def test_buffer_copy(self, mock_copy):
        self.acc._ws.append("a")
        self.acc._ws.append("b")
        self.acc._handle_cmd({"cmd": "copy"})
        mock_copy.assert_called_once_with("a\nb")
        self.assertIn("已複製暫存區 2 筆", self.last_text())

    def test_buffer_copy_empty(self):
        self.acc._handle_cmd({"cmd": "copy"})
        self.assertIn("空的", self.last_text())

    @mock.patch("text_accumulator.clipboard.paste", return_value=(True, "x\ny\n"))
    def test_buffer_paste(self, mock_paste):
        self.acc._handle_cmd({"cmd": "paste"})
        self.assertEqual(self.acc._ws.lines(), ["x", "y"])
        self.assertIn("貼上 2 筆", self.last_text())

    @mock.patch("text_accumulator.clipboard.paste", return_value=(False, "失敗"))
    def test_buffer_paste_failure(self, mock_paste):
        self.acc._handle_cmd({"cmd": "paste"})
        self.assertIn("[錯誤] 失敗", self.last_text())
        self.assertTrue(self.acc._ws.is_empty())


if __name__ == "__main__":
    unittest.main()
