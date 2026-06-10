"""WorkspaceController 指令派發測試。

執行：python3 -m unittest tests.test_workspace_controller
"""

import configparser
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from session_manager import SessionManager
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


class WCTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.sm = make_sm(self._tmp.name)
        self.wc = WorkspaceController(self.sm)

    def tearDown(self):
        self._tmp.cleanup()


class TestCurrentAndWs(WCTestBase):
    def test_default_current_is_buffer(self):
        self.assertEqual(self.wc.current, "buffer")

    def test_set_current(self):
        self.assertTrue(self.wc.set_current("stt"))
        self.assertEqual(self.wc.current, "stt")
        self.assertFalse(self.wc.set_current("nope"))
        self.assertEqual(self.wc.current, "stt")

    def test_ws_listing(self):
        self.wc.stt.append("a")
        self.sm.add_message("user", "hi")
        res = self.wc.handle_ws([], buffer_count=3)
        text = res.messages[0][1]
        self.assertIn("stt", text)
        self.assertIn("buffer (當前) · 3 筆", text)
        self.assertIn("stt · 1 筆", text)
        self.assertIn("chat · 1 筆", text)

    def test_ws_switch(self):
        res = self.wc.handle_ws(["chat"], buffer_count=0)
        self.assertEqual(self.wc.current, "chat")
        self.assertIn("已切換當前工作區至: chat", res.messages[0][1])

    def test_ws_switch_invalid(self):
        res = self.wc.handle_ws(["xxx"], buffer_count=0)
        self.assertEqual(self.wc.current, "buffer")
        self.assertIn("未知工作區", res.messages[0][1])


class TestShow(WCTestBase):
    def test_show_buffer_delegates_to_queue(self):
        res = self.wc.handle_show()
        self.assertEqual(res.acc_cmds, [{"cmd": "peek"}])
        self.assertEqual(res.messages, [])

    def test_show_stt_empty(self):
        self.wc.set_current("stt")
        res = self.wc.handle_show()
        self.assertIn("空的", res.messages[0][1])

    def test_show_stt_lists(self):
        self.wc.set_current("stt")
        self.wc.stt.append("hello")
        self.wc.stt.append(["a", "b"])
        res = self.wc.handle_show()
        text = res.messages[0][1]
        self.assertIn("[stt 工作區 · 2 筆]", text)
        self.assertIn("[1] hello", text)
        self.assertIn("[2] a b", text)

    def test_show_chat(self):
        self.wc.set_current("chat")
        self.sm.add_message("user", "嗨")
        res = self.wc.handle_show()
        self.assertIn("用戶說：嗨", res.messages[0][1])


class TestClear(WCTestBase):
    def test_clear_ui(self):
        res = self.wc.handle_clear(["ui"])
        self.assertTrue(res.clear_ui)

    def test_clear_buffer_delegates(self):
        res = self.wc.handle_clear(["buffer"])
        self.assertEqual(res.acc_cmds, [{"cmd": "clear"}])

    def test_clear_current_buffer_no_arg(self):
        # 當前預設 buffer，無參數 → 清 buffer
        res = self.wc.handle_clear([])
        self.assertEqual(res.acc_cmds, [{"cmd": "clear"}])

    def test_clear_stt(self):
        self.wc.stt.append("x")
        res = self.wc.handle_clear(["stt"])
        self.assertTrue(self.wc.stt.is_empty())
        self.assertIn("stt 工作區已清空", res.messages[0][1])

    def test_clear_chat(self):
        self.sm.add_message("user", "a")
        self.sm.add_message("assistant", "b")
        res = self.wc.handle_clear(["chat"])
        self.assertEqual(self.sm.message_count(), 0)
        self.assertIn("已清空（原含 2 筆）", res.messages[0][1])

    def test_clear_current_after_switch(self):
        self.wc.set_current("stt")
        self.wc.stt.append("x")
        res = self.wc.handle_clear([])  # 清當前 = stt
        self.assertTrue(self.wc.stt.is_empty())
        self.assertIn("stt", res.messages[0][1])

    def test_clear_unknown_target(self):
        res = self.wc.handle_clear(["bogus"])
        self.assertIn("未知的清除目標", res.messages[0][1])


class TestSend(WCTestBase):
    def test_send_buffer(self):
        res = self.wc.handle_send()
        self.assertEqual(res.acc_cmds, [{"cmd": "flush", "msg_type": "TextChat"}])

    def test_send_non_buffer_blocked(self):
        self.wc.set_current("chat")
        res = self.wc.handle_send()
        self.assertEqual(res.acc_cmds, [])
        self.assertIn("僅適用於 buffer", res.messages[0][1])


if __name__ == "__main__":
    unittest.main()
