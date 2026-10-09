"""modules.CommandRouter 複製貼上指令單元測試（/copy、/paste、注入剪貼簿）。

自 tests/test_command_router_workspace_edit.py 拆出。
執行：python3 -m unittest tests.test_command_router_clipboard
"""

import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._router_helpers import cmd, make_router


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
