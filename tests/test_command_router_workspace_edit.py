"""modules.CommandRouter 工作區指令單元測試（Task 3）——清除、刪除、移動、合併。

複製貼上（/copy、/paste 與注入剪貼簿）見 tests/test_command_router_clipboard.py。
執行：python3 -m unittest tests.test_command_router_workspace_edit
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.message import Message
from tests._router_helpers import cmd, make_router


class TestClearCommand(unittest.TestCase):
    """Test 4: /clear"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_clear_current_with_count(self):
        """Test 4a: /clear 清當前工作區並回報原筆數"""
        ws = self.wm.get("buffer")
        ws.append("a")
        ws.append("b")
        msgs = cmd(self.router, "/clear")
        text = msgs[0].payload["text"]
        self.assertIn("2", text)
        self.assertTrue(ws.is_empty())

    def test_clear_ui_emits_clear_and_status(self):
        """Test 4b: /clear ui 發出 clear 類型事件 + status 待機"""
        msgs = cmd(self.router, "/clear", ["ui"])
        topics = {m.topic: m.payload for m in msgs}
        self.assertIn("ui_event", topics)
        # 應有一個 type=clear 事件
        ui_payloads = [m.payload for m in msgs if m.topic == "ui_event"]
        types = [p.get("type") for p in ui_payloads]
        self.assertIn("clear", types)
        self.assertIn("status", types)
        # status 文字為 "待機"
        status_texts = [p.get("text") for p in ui_payloads if p.get("type") == "status"]
        self.assertIn("待機", status_texts)

    def test_clear_buffer_explicit(self):
        """Test 4c: /clear buffer 清 buffer 工作區"""
        self.wm.get("buffer").append("x")
        msgs = cmd(self.router, "/clear", ["buffer"])
        text = msgs[0].payload["text"]
        self.assertIn("buffer", text)
        self.assertTrue(self.wm.get("buffer").is_empty())

    def test_clear_stt_explicit(self):
        """Test 4d: /clear stt 清 stt 工作區"""
        self.wm.get("stt").append("x")
        msgs = cmd(self.router, "/clear", ["stt"])
        text = msgs[0].payload["text"]
        self.assertIn("stt", text)
        self.assertTrue(self.wm.get("stt").is_empty())

    def test_clear_chat_clears_history_and_reports_count(self):
        """Test 4e: /clear chat 清空 sm history 並回報原筆數"""
        # 種入 3 則歷史
        self.sm.add_message("user", "msg1")
        self.sm.add_message("assistant", "reply1")
        self.sm.add_message("user", "msg2")
        msgs = cmd(self.router, "/clear", ["chat"])
        text = msgs[0].payload["text"]
        self.assertIn("已清空", text)
        self.assertIn("3", text)
        self.assertIn("chat", text)
        # 確認 sm history 已清空
        self.assertEqual(self.sm.message_count(), 0)

    def test_clear_chat_sm_none_friendly_message(self):
        """Test 4f: /clear chat 在 _sm 為 None 時回傳友善訊息，不 AttributeError"""
        router_no_sm, wm_ns, _ = make_router(self._tmp.name, sm=None)
        # 需要手動建一個 session_manager=None 的 router
        from modules.workspace_manager import WorkspaceManager as WM
        wm2 = WM()
        from modules.command_router import CommandRouter as CR
        r2 = CR(workspace_manager=wm2, session_manager=None, export_dir=self._tmp.name)
        payload = {"cmd": "/clear", "args": ["chat"]}
        r2.handle(Message(topic="commands", payload=payload))
        result = []
        while True:
            try:
                result.append(r2.outbox.get_nowait())
            except Exception:
                break
        self.assertEqual(len(result), 1)
        text = result[0].payload["text"]
        # 不應崩潰，應有友善文字
        self.assertIsInstance(text, str)
        self.assertGreater(len(text), 0)


class TestDelCommand(unittest.TestCase):
    """Test 5: /del"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_del_valid_index(self):
        """Test 5a: /del 1 刪除第一筆（1-based）"""
        ws = self.wm.get("buffer")
        ws.append("keep")
        ws.append("delete_me")
        # 切換到 stt 來測試（buffer 預設是當前）
        # 實際上 current=buffer，/del 1 刪除 buffer 第 1 筆（0-indexed 0）
        msgs = cmd(self.router, "/del", ["1"])
        text = msgs[0].payload["text"]
        self.assertIn("1", text)
        self.assertEqual(ws.count(), 1)
        self.assertEqual(ws.lines()[0], "delete_me")  # 原第 2 筆

    def test_del_non_numeric(self):
        """Test 5b: /del abc → 用法訊息"""
        msgs = cmd(self.router, "/del", ["abc"])
        text = msgs[0].payload["text"]
        self.assertIn("用法", text)
        self.assertIn("/del", text)

    def test_del_out_of_range(self):
        """Test 5c: /del 99 → 失敗訊息"""
        ws = self.wm.get("buffer")
        ws.append("only_one")
        msgs = cmd(self.router, "/del", ["99"])
        text = msgs[0].payload["text"]
        self.assertIn("99", text)
        self.assertEqual(ws.count(), 1)  # 未被刪

    def test_del_no_args(self):
        """Test 5d: /del 無參數 → 用法訊息"""
        msgs = cmd(self.router, "/del")
        text = msgs[0].payload["text"]
        self.assertIn("用法", text)


class TestMoveToTopConcatCommands(unittest.TestCase):
    """Test 6: /move /to_top /concat 快樂路徑"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_move_happy_path(self):
        """Test 6a: /move 2 1 移動第 2 筆到第 1 位"""
        ws = self.wm.get("buffer")
        ws.append("first")
        ws.append("second")
        msgs = cmd(self.router, "/move", ["2", "1"])
        text = msgs[0].payload["text"]
        self.assertIn("2", text)
        self.assertIn("1", text)
        self.assertEqual(ws.lines()[0], "second")

    def test_move_missing_args(self):
        """Test 6b: /move 缺參數 → 用法訊息"""
        msgs = cmd(self.router, "/move", ["1"])
        text = msgs[0].payload["text"]
        self.assertIn("用法", text)

    def test_to_top_happy_path(self):
        """Test 6c: /to_top 不帶參數把最後一筆移到最前"""
        ws = self.wm.get("buffer")
        ws.append("first")
        ws.append("last")
        msgs = cmd(self.router, "/to_top")
        text = msgs[0].payload["text"]
        self.assertIn("最前", text)
        self.assertEqual(ws.lines()[0], "last")

    def test_to_top_with_index(self):
        """Test 6d: /to_top 2 把第 2 筆移到最前"""
        ws = self.wm.get("buffer")
        ws.append("a")
        ws.append("b")
        ws.append("c")
        msgs = cmd(self.router, "/to_top", ["2"])
        text = msgs[0].payload["text"]
        self.assertIn("2", text)
        self.assertEqual(ws.lines()[0], "b")

    def test_to_top_zero_reports_usage(self):
        """Test 6d-2: /to_top 0 → 用法訊息（編號需 ≥ 1），工作區不變"""
        ws = self.wm.get("buffer")
        ws.append("a")
        ws.append("b")
        msgs = cmd(self.router, "/to_top", ["0"])
        texts = [m.payload["text"] for m in msgs]
        self.assertEqual(texts, ["用法: /to_top [編號]（編號需 ≥ 1）"])
        self.assertEqual(ws.lines(), ["a", "b"])

    def test_to_top_negative_reports_usage(self):
        """Test 6d-3: /to_top -1 → 同樣回報用法，工作區不變"""
        ws = self.wm.get("buffer")
        ws.append("a")
        ws.append("b")
        msgs = cmd(self.router, "/to_top", ["-1"])
        self.assertIn("編號需 ≥ 1", msgs[0].payload["text"])
        self.assertEqual(ws.lines(), ["a", "b"])

    def test_concat_happy_path(self):
        """Test 6e: /concat 壓縮多筆為一筆"""
        ws = self.wm.get("buffer")
        ws.append("hello")
        ws.append("world")
        msgs = cmd(self.router, "/concat")
        text = msgs[0].payload["text"]
        self.assertIn("2", text)
        self.assertEqual(ws.count(), 1)
        self.assertIn("hello world", ws.lines()[0])


if __name__ == "__main__":
    unittest.main()
