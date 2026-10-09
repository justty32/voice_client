"""modules.CommandRouter 語音指令解析單元測試（Task 5）——send／switch／export／clear 語音指令。

執行：python3 -m unittest tests.test_command_router_voice_commands
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._router_helpers import make_router, ui_texts, voice


# ── Test 1: "send" 英文關鍵字 → outbound 路徑 ─────────────────────────────────


class TestVoiceSendEnglish(unittest.TestCase):
    """Test 1: "send" → outbound 路徑（內部重派發到 /send）"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)
        # 確保當前工作區是 buffer 並放一筆資料
        self.wm.switch("buffer")
        self.wm.get("buffer").append("hello world")

    def tearDown(self):
        self._tmp.cleanup()

    def test_send_english_emits_outbound(self):
        """Test 1: "send" → emit outbound（內部重派發到 /send）"""
        msgs = voice(self.router, "send")
        topics = [m.topic for m in msgs]
        self.assertIn("outbound", topics)

    def test_send_english_outbound_has_content(self):
        """Test 1b: outbound payload 含 Content 欄位"""
        msgs = voice(self.router, "send")
        outbound_msgs = [m for m in msgs if m.topic == "outbound"]
        self.assertEqual(len(outbound_msgs), 1)
        self.assertIn("Content", outbound_msgs[0].payload)
        self.assertEqual(outbound_msgs[0].payload["Content"], "hello world")


# ── Test 2: "發送" 中文關鍵字 ─────────────────────────────────────────────────


class TestVoiceSendChinese(unittest.TestCase):
    """Test 2: "發送" 中文關鍵字 → outbound 路徑"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)
        self.wm.switch("buffer")
        self.wm.get("buffer").append("測試內容")

    def tearDown(self):
        self._tmp.cleanup()

    def test_send_chinese_keyword(self):
        """Test 2: "發送" 中文關鍵字也會觸發 /send"""
        msgs = voice(self.router, "發送")
        topics = [m.topic for m in msgs]
        self.assertIn("outbound", topics)

    def test_chuansong_keyword(self):
        """Test 2b: "傳送" 關鍵字也會觸發 /send"""
        # 重新放資料（之前已被清除）
        self.wm.get("buffer").append("傳送測試")
        msgs = voice(self.router, "傳送")
        topics = [m.topic for m in msgs]
        self.assertIn("outbound", topics)


# ── Test 3: "切換 foo" → session switch ──────────────────────────────────────


class TestVoiceSwitch(unittest.TestCase):
    """Test 3: "切換 foo" → session switch"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_switch_nonexistent_session(self):
        """Test 3a: 切換到不存在的 session → 找不到對話訊息"""
        msgs = voice(self.router, "切換 noexist")
        texts = ui_texts(msgs)
        combined = " ".join(texts)
        self.assertIn("找不到對話", combined)

    def test_switch_existing_session(self):
        """Test 3b: 切換到已存在的 session → 切換成功訊息

        Note: session 名稱不可含 "new" 以避免觸發 legacy new 優先分支。
        """
        self.sm.new_session("beta")
        self.sm.switch_session("default")  # 先回 default
        msgs = voice(self.router, "切換 beta")
        texts = ui_texts(msgs)
        combined = " ".join(texts)
        self.assertIn("切換至", combined)
        self.assertIn("beta", combined)


# ── Test 4: "匯出 測試" → arg extraction ─────────────────────────────────────


class TestVoiceExport(unittest.TestCase):
    """Test 4: "匯出 測試" → arg extraction，export 以 測試 為檔名"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)
        # 填充 buffer 供匯出
        self.wm.get("buffer").append("匯出內容")

    def tearDown(self):
        self._tmp.cleanup()

    def test_export_arg_extraction(self):
        """Test 4: "匯出 測試" → 以 "測試" 作為匯出檔名"""
        msgs = voice(self.router, "匯出 測試")
        texts = ui_texts(msgs)
        combined = " ".join(texts)
        # 訊息中應含 "測試"（檔名）或 export 路徑
        self.assertIn("測試", combined)

    def test_export_english_keyword(self):
        """Test 4b: "export myfile" → 以 "myfile" 作為匯出檔名"""
        msgs = voice(self.router, "export myfile")
        texts = ui_texts(msgs)
        combined = " ".join(texts)
        self.assertIn("myfile", combined)


# ── Test 5: "清除" 變體 ────────────────────────────────────────────────────────


class TestVoiceClear(unittest.TestCase):
    """Test 5: "清除 暫存" → /clear buffer；"清除 畫面" → /clear ui"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)
        self.wm.get("buffer").append("有資料")

    def tearDown(self):
        self._tmp.cleanup()

    def test_clear_buffer_variant(self):
        """Test 5a: "清除 暫存" → 清 buffer 工作區"""
        msgs = voice(self.router, "清除 暫存")
        texts = ui_texts(msgs)
        combined = " ".join(texts)
        # 語音指令顯示訊息 + buffer 清空確認訊息
        self.assertIn("語音指令", combined)
        self.assertIn("buffer", combined)

    def test_clear_ui_variant(self):
        """Test 5b: "清除 畫面" → emit ui_event clear"""
        msgs = voice(self.router, "清除 畫面")
        topics = [m.topic for m in msgs]
        self.assertIn("ui_event", topics)
        clear_msgs = [
            m for m in msgs
            if m.topic == "ui_event" and m.payload.get("type") == "clear"
        ]
        self.assertEqual(len(clear_msgs), 1)

    def test_clear_english_buffer(self):
        """Test 5c: "clear buffer" → 清 buffer 工作區"""
        self.wm.get("buffer").append("more data")
        msgs = voice(self.router, "clear buffer")
        texts = ui_texts(msgs)
        combined = " ".join(texts)
        self.assertIn("buffer", combined)

    def test_clear_ui_english(self):
        """Test 5d: "clear ui" → emit ui_event clear"""
        msgs = voice(self.router, "clear ui")
        clear_msgs = [
            m for m in msgs
            if m.topic == "ui_event" and m.payload.get("type") == "clear"
        ]
        self.assertEqual(len(clear_msgs), 1)

    def test_clear_no_variant(self):
        """Test 5e: "清除" 無變體 → 清當前工作區（buffer）"""
        msgs = voice(self.router, "清除")
        texts = ui_texts(msgs)
        combined = " ".join(texts)
        # 應有語音指令顯示 + 清空確認
        self.assertIn("語音指令", combined)


if __name__ == "__main__":
    unittest.main()
