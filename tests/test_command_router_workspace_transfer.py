"""modules.CommandRouter 工作區指令單元測試（Task 3）——匯出匯入與送出。

執行：python3 -m unittest tests.test_command_router_workspace_transfer
"""

import os
import sys
import tempfile
import unittest
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.message import Message
from tests._helpers import drain
from tests._router_helpers import cmd, make_router


class TestExportImportCommands(unittest.TestCase):
    """Test 9: /export + /import 往返"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_export_then_import_roundtrip(self):
        """Test 9: /export 後 /import 能還原資料"""
        ws = self.wm.get("buffer")
        ws.append("entry_a")
        ws.append("entry_b")
        # 匯出
        export_msgs = cmd(self.router, "/export", ["roundtrip_test"])
        self.assertEqual(len(export_msgs), 1)
        self.assertIn("匯出", export_msgs[0].payload["text"])
        # 清空
        ws.clear()
        self.assertTrue(ws.is_empty())
        # 匯入
        import_msgs = cmd(self.router, "/import", ["roundtrip_test"])
        self.assertEqual(len(import_msgs), 1)
        self.assertIn("匯入", import_msgs[0].payload["text"])
        self.assertIn("2", import_msgs[0].payload["text"])
        self.assertEqual(ws.count(), 2)

    def test_export_no_args_is_error(self):
        """Test 9b: /export 不帶參數應報錯，要求指定檔名"""
        ws = self.wm.get("buffer")
        ws.append("data")
        msgs = cmd(self.router, "/export")
        self.assertEqual(len(msgs), 1)
        text = msgs[0].payload["text"]
        self.assertIn("[錯誤]", text)
        self.assertIn("/export", text)

    def test_import_no_args_is_error(self):
        """Test 9d: /import 不帶參數應報錯"""
        msgs = cmd(self.router, "/import")
        self.assertEqual(len(msgs), 1)
        text = msgs[0].payload["text"]
        self.assertIn("[錯誤]", text)

    def test_import_file_not_found(self):
        """Test 9c: /import 找不到檔案 → 錯誤訊息"""
        msgs = cmd(self.router, "/import", ["nonexistent_xyz"])
        text = msgs[0].payload["text"]
        self.assertIn("[錯誤]", text)


class TestSendCommand(unittest.TestCase):
    """Test 10-12: /send"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_send_non_buffer_workspace_rejected(self):
        """Test 10: 當前工作區不是 buffer 時 /send 被拒絕，不發 outbound"""
        self.wm.switch("stt")
        msgs = cmd(self.router, "/send")
        # 只有 ui_event，沒有 outbound
        topics = [m.topic for m in msgs]
        self.assertNotIn("outbound", topics)
        self.assertIn("ui_event", topics)
        ui_msgs = [m for m in msgs if m.topic == "ui_event"]
        text = ui_msgs[0].payload["text"]
        self.assertIn("/send", text)
        self.assertIn("buffer", text)
        self.assertIn("stt", text)

    def test_send_empty_buffer_no_outbound(self):
        """Test 11: buffer 空時 /send 不發 outbound，只發 ui_event 訊息"""
        # buffer is current and empty
        msgs = cmd(self.router, "/send")
        topics = [m.topic for m in msgs]
        self.assertNotIn("outbound", topics)
        self.assertIn("ui_event", topics)

    def test_send_with_content_outbound_payload(self):
        """Test 12: buffer 有內容時 /send 發出正確 outbound payload（無 Type 鍵）"""
        ws = self.wm.get("buffer")
        ws.append("hello")
        ws.append("world")
        msgs = cmd(self.router, "/send")

        # 確認有 outbound
        outbound_msgs = [m for m in msgs if m.topic == "outbound"]
        self.assertEqual(len(outbound_msgs), 1)
        payload = outbound_msgs[0].payload

        # 舊版 payload 只有 Title、Content、Metadata.ClientTime，沒有 Type
        self.assertNotIn("Type", payload)
        self.assertIn("hello", payload["Content"])
        self.assertIn("world", payload["Content"])
        self.assertEqual(payload["Title"], self.sm.current_title)
        self.assertIn("ClientTime", payload["Metadata"])
        # ClientTime 應為 ISO 格式 UTC 時間
        ct = payload["Metadata"]["ClientTime"]
        # 能正常解析
        datetime.fromisoformat(ct)

    def test_send_whitespace_only_buffer_no_outbound(self):
        """Test 12e: buffer 僅含空白字元時 /send 不發 outbound，清空 buffer，發 ui 訊息"""
        ws = self.wm.get("buffer")
        ws.append("   ")
        ws.append("  \t  ")
        msgs = cmd(self.router, "/send")
        topics = [m.topic for m in msgs]
        self.assertNotIn("outbound", topics)
        self.assertIn("ui_event", topics)
        self.assertTrue(ws.is_empty())

    def test_send_adds_to_session_history(self):
        """Test 12b: /send 把 content 加入 session 歷史"""
        ws = self.wm.get("buffer")
        ws.append("test message")
        cmd(self.router, "/send")
        session = self.sm.get_current_session()
        history = session["history"]
        self.assertTrue(any(h[0] == "user" and "test message" in h[1] for h in history))

    def test_send_clears_buffer(self):
        """Test 12c: /send 後 buffer 應被清空"""
        ws = self.wm.get("buffer")
        ws.append("clear me")
        cmd(self.router, "/send")
        self.assertTrue(ws.is_empty())

    def test_send_uses_atomic_drain(self):
        """Test 12c-2: /send 以 Workspace.drain() 單次原子取出並清空（B3），不再分開 flatten＋clear"""
        from unittest import mock
        ws = self.wm.get("buffer")
        ws.append("a")
        ws.append("b")
        with mock.patch.object(ws, "drain", wraps=ws.drain) as spy, \
                mock.patch.object(ws, "clear", wraps=ws.clear) as clear_spy:
            msgs = cmd(self.router, "/send")
        spy.assert_called_once_with(seg_sep=" ", entry_sep=" ")
        clear_spy.assert_not_called()
        self.assertTrue(ws.is_empty())
        outbound = [m for m in msgs if m.topic == "outbound"]
        self.assertEqual(len(outbound), 1)

    def test_send_emits_sending_and_status_events(self):
        """Test 12d: /send 發出 sending 訊息 + status 傳送中"""
        ws = self.wm.get("buffer")
        ws.append("content")
        msgs = cmd(self.router, "/send")
        ui_msgs = [m for m in msgs if m.topic == "ui_event"]
        types = [m.payload.get("type") for m in ui_msgs]
        self.assertIn("message", types)
        self.assertIn("status", types)
        # 找 sending 角色的訊息
        sending = [m for m in ui_msgs if m.payload.get("role") == "sending"]
        self.assertTrue(len(sending) >= 1)
        self.assertIn("[傳送內容]", sending[0].payload["text"])
        # status "傳送中"
        status = [m for m in ui_msgs if m.payload.get("type") == "status"]
        self.assertTrue(any("傳送中" in m.payload.get("text", "") for m in status))


class TestQuickSend(unittest.TestCase):
    """Test 13: quick_send 走同一路徑"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_quick_send_empty_buffer_no_outbound(self):
        """Test 13a: QUICK_SEND 在空 buffer 下不發 outbound（與 /send 相同路徑）"""
        self.router.handle(Message(topic="commands", payload="QUICK_SEND"))
        msgs = drain(self.router)
        topics = [m.topic for m in msgs]
        self.assertNotIn("outbound", topics)
        self.assertIn("ui_event", topics)

    def test_quick_send_with_content_goes_through_send_path(self):
        """Test 13b: QUICK_SEND 有內容時發 outbound（與 /send 相同路徑，無 Type 鍵）"""
        ws = self.wm.get("buffer")
        ws.append("quick content")
        self.router.handle(Message(topic="commands", payload="QUICK_SEND"))
        msgs = drain(self.router)
        outbound_msgs = [m for m in msgs if m.topic == "outbound"]
        self.assertEqual(len(outbound_msgs), 1)
        self.assertNotIn("Type", outbound_msgs[0].payload)
        self.assertIn("quick content", outbound_msgs[0].payload["Content"])

    def test_quick_send_non_buffer_workspace_rejected(self):
        """Test 13c: QUICK_SEND 在非 buffer 工作區 → 拒絕，不發 outbound"""
        self.wm.switch("stt")
        self.router.handle(Message(topic="commands", payload="QUICK_SEND"))
        msgs = drain(self.router)
        topics = [m.topic for m in msgs]
        self.assertNotIn("outbound", topics)
        self.assertIn("ui_event", topics)


if __name__ == "__main__":
    unittest.main()
