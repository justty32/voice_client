"""modules.CommandRouter 工作區指令單元測試（Task 3）——/ws 與 /show 檢視。

執行：python3 -m unittest tests.test_command_router_workspace_view
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.message import Message
from tests._router_helpers import cmd, make_router


class TestWsCommand(unittest.TestCase):
    """Test 1-2: /ws 列出工作區 + 切換"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_ws_no_args_lists_workspaces(self):
        """Test 1: /ws 無參數列出 buffer、stt 並標示當前，chat 顯示真實筆數"""
        msgs = cmd(self.router, "/ws")
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].topic, "ui_event")
        text = msgs[0].payload["text"]
        self.assertIn("buffer", text)
        self.assertIn("stt", text)
        # 當前工作區 buffer 應有標示
        self.assertIn("當前", text)
        # chat 應出現並顯示筆數（不再是階段④佔位訊息）
        self.assertIn("chat", text)
        self.assertNotIn("階段④", text)

    def test_ws_no_args_shows_counts(self):
        """Test 1b: /ws 無參數顯示各工作區筆數"""
        # 在 buffer 加一筆
        self.wm.get("buffer").append("hello")
        msgs = cmd(self.router, "/ws")
        text = msgs[0].payload["text"]
        # buffer 有 1 筆
        self.assertIn("1", text)

    def test_ws_switch_valid(self):
        """Test 2a: /ws stt 切換成功"""
        msgs = cmd(self.router, "/ws", ["stt"])
        self.assertEqual(len(msgs), 1)
        text = msgs[0].payload["text"]
        self.assertIn("已切換當前工作區至", text)
        self.assertIn("stt", text)
        self.assertEqual(self.wm.current, "stt")

    def test_ws_switch_invalid(self):
        """Test 2b: /ws nope 失敗並回傳可用清單"""
        msgs = cmd(self.router, "/ws", ["nope"])
        self.assertEqual(len(msgs), 1)
        text = msgs[0].payload["text"]
        self.assertIn("未知工作區", text)
        self.assertIn("nope", text)
        self.assertIn("buffer", text)
        self.assertIn("stt", text)
        # 當前應不變
        self.assertEqual(self.wm.current, "buffer")


class TestShowCommand(unittest.TestCase):
    """Test 3: /show"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_show_with_content(self):
        """Test 3a: /show 有內容時顯示編號行"""
        self.wm.get("buffer").append("line one")
        self.wm.get("buffer").append("line two")
        msgs = cmd(self.router, "/show")
        self.assertEqual(len(msgs), 1)
        text = msgs[0].payload["text"]
        # 應包含標頭
        self.assertIn("buffer", text)
        self.assertIn("2", text)
        # 應有編號
        self.assertIn("1", text)
        self.assertIn("line one", text)
        self.assertIn("line two", text)

    def test_show_empty_workspace(self):
        """Test 3b: /show 空工作區顯示空訊息"""
        msgs = cmd(self.router, "/show")
        self.assertEqual(len(msgs), 1)
        text = msgs[0].payload["text"]
        self.assertIn("空的", text)
        self.assertIn("buffer", text)


class TestWsChatCount(unittest.TestCase):
    """/ws 無參數 — chat 行顯示真實歷史筆數（Task 4 新測試）"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_ws_chat_count_zero(self):
        """chat 歷史為空時顯示 0 筆"""
        msgs = cmd(self.router, "/ws")
        text = msgs[0].payload["text"]
        # chat 行應含 '0 筆'
        import re
        chat_line = next(ln for ln in text.splitlines() if "chat" in ln)
        self.assertIn("0", chat_line)

    def test_ws_chat_count_after_add(self):
        """加入 2 則歷史後 /ws 顯示 2 筆"""
        self.sm.add_message("user", "hello")
        self.sm.add_message("assistant", "hi")
        msgs = cmd(self.router, "/ws")
        text = msgs[0].payload["text"]
        chat_line = next(ln for ln in text.splitlines() if "chat" in ln)
        self.assertIn("2", chat_line)

    def test_ws_chat_no_sm_shows_zero_or_omits(self):
        """_sm 為 None 時 /ws chat 行顯示 0 筆（或省略），不崩潰"""
        from modules.workspace_manager import WorkspaceManager as WM
        from modules.command_router import CommandRouter as CR
        wm2 = WM()
        r2 = CR(workspace_manager=wm2, session_manager=None, export_dir=self._tmp.name)
        r2.handle(Message(topic="commands", payload={"cmd": "/ws", "args": []}))
        result = []
        while True:
            try:
                result.append(r2.outbox.get_nowait())
            except Exception:
                break
        self.assertEqual(len(result), 1)
        text = result[0].payload["text"]
        # 至少有 buffer 和 stt，不崩潰
        self.assertIn("buffer", text)


class TestWsChatReadonly(unittest.TestCase):
    """/ws chat 應回唯讀提示，不允許切換"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_ws_chat_returns_readonly_message(self):
        """/ws chat 回「chat 為唯讀檢視」提示，current 不變"""
        original_current = self.wm.current
        msgs = cmd(self.router, "/ws", ["chat"])
        self.assertEqual(len(msgs), 1)
        text = msgs[0].payload["text"]
        self.assertIn("唯讀", text)
        self.assertIn("chat", text)
        # current 工作區不應變更
        self.assertEqual(self.wm.current, original_current)

    def test_ws_chat_message_mentions_history_and_clear(self):
        """/ws chat 訊息提及 /history 與 /clear chat"""
        msgs = cmd(self.router, "/ws", ["chat"])
        text = msgs[0].payload["text"]
        self.assertIn("/history", text)
        self.assertIn("/clear chat", text)

    def test_ws_chat_not_set_as_current(self):
        """wm.switch('chat') 不應被呼叫 — chat 不可成為當前工作區"""
        # 在切換後 current 仍為 buffer（預設）
        cmd(self.router, "/ws", ["chat"])
        self.assertNotEqual(self.wm.current, "chat")


if __name__ == "__main__":
    unittest.main()
