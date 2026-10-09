"""modules.CommandRouter 工作區指令單元測試（Task 3）——清除、刪除、移動、合併、複製貼上。

執行：python3 -m unittest tests.test_command_router_workspace_edit
"""

import os
import sys
import tempfile
import unittest
from unittest import mock

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


class TestCopyPasteCommands(unittest.TestCase):
    """Test 7-8: /copy /paste"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    @mock.patch("utils.clipboard.copy", return_value=(True, ""))
    def test_copy_success(self, mock_copy):
        """Test 7a: /copy 成功複製並回報筆數"""
        ws = self.wm.get("buffer")
        ws.append("line1")
        ws.append("line2")
        msgs = cmd(self.router, "/copy")
        mock_copy.assert_called_once()
        text = msgs[0].payload["text"]
        self.assertIn("2", text)
        self.assertIn("複製", text)

    def test_copy_empty_workspace(self):
        """Test 7b: /copy 空工作區 → 空的訊息"""
        msgs = cmd(self.router, "/copy")
        text = msgs[0].payload["text"]
        self.assertIn("空的", text)
        self.assertIn("buffer", text)

    @mock.patch("utils.clipboard.copy", return_value=(False, "找不到工具"))
    def test_copy_failure_message(self, mock_copy):
        """Test 7c: /copy 剪貼簿失敗 → 錯誤訊息"""
        self.wm.get("buffer").append("x")
        msgs = cmd(self.router, "/copy")
        text = msgs[0].payload["text"]
        self.assertIn("[錯誤]", text)
        self.assertIn("找不到工具", text)

    @mock.patch("utils.clipboard.paste", return_value=(True, "line1\n  \nline2\n"))
    def test_paste_multi_line(self, mock_paste):
        """Test 8: /paste 把多行剪貼簿內容逐非空行 append 到工作區"""
        ws = self.wm.get("buffer")
        msgs = cmd(self.router, "/paste")
        self.assertEqual(ws.count(), 2)
        self.assertEqual(ws.lines(), ["line1", "line2"])
        text = msgs[0].payload["text"]
        self.assertIn("2", text)
        self.assertIn("貼上", text)

    @mock.patch("utils.clipboard.paste", return_value=(False, "讀取失敗"))
    def test_paste_failure(self, mock_paste):
        """Test 8b: /paste 失敗 → 錯誤訊息，工作區不變"""
        msgs = cmd(self.router, "/paste")
        text = msgs[0].payload["text"]
        self.assertIn("[錯誤]", text)
        self.assertTrue(self.wm.get("buffer").is_empty())


class _FakeClipboard:
    """注入 CommandRouter 的剪貼簿替身（階段 7b：clipboard 參數）。"""

    def __init__(self, paste_result=(True, "")):
        self.copied: list[str] = []
        self._paste_result = paste_result

    def copy(self, text):
        self.copied.append(text)
        return True, ""

    def paste(self):
        return self._paste_result


class TestInjectedClipboard(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    @mock.patch("utils.clipboard.copy", side_effect=AssertionError("不應呼叫本機剪貼簿"))
    def test_copy_uses_injected_clipboard(self, _local):
        fake = _FakeClipboard()
        self.router._clipboard = fake
        self.wm.get("buffer").append("a")
        self.wm.get("buffer").append("b")
        msgs = cmd(self.router, "/copy")
        self.assertEqual(fake.copied, ["a\nb"])
        self.assertIn("已複製 buffer 工作區 2 筆", msgs[0].payload["text"])

    def test_paste_uses_injected_clipboard(self):
        from modules.command_router import CommandRouter
        fake = _FakeClipboard(paste_result=(True, "x\ny"))
        router = CommandRouter(self.wm, self.sm, self._tmp.name, clipboard=fake)
        msgs = cmd(router, "/paste")
        self.assertEqual(self.wm.get("buffer").lines(), ["x", "y"])
        self.assertIn("貼上 2 筆", msgs[0].payload["text"])


if __name__ == "__main__":
    unittest.main()
