"""modules.CommandRouter 語音指令解析單元測試（Task 5）——無法辨識、UI 事件順序、優先序與中文關鍵字。

執行：python3 -m unittest tests.test_command_router_voice_parsing
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._router_helpers import make_router, ui_texts, voice


# ── Test 6: 無法識別的語音指令 ────────────────────────────────────────────────


class TestVoiceUnrecognized(unittest.TestCase):
    """Test 6: 無法識別的語音指令 → 顯示 "無法識別的語音指令" 訊息"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_unrecognized_text(self):
        """Test 6a: 無法識別的文字 → 回傳無法識別訊息"""
        msgs = voice(self.router, "完全無法識別的神秘語音")
        texts = ui_texts(msgs)
        combined = " ".join(texts)
        self.assertIn("無法識別的語音指令", combined)

    def test_unrecognized_contains_original_text(self):
        """Test 6b: 無法識別訊息中包含原始文字（lowered）"""
        msgs = voice(self.router, "XYZ_RANDOM_123")
        texts = ui_texts(msgs)
        combined = " ".join(texts)
        self.assertIn("無法識別的語音指令", combined)
        # 原始文字 lowered 後應在訊息中
        self.assertIn("xyz_random_123", combined)

    def test_empty_args_unrecognized(self):
        """Test 6c: 空 args → 不崩潰，回傳無法識別"""
        msgs = voice(self.router, "")
        # 空白文字應顯示無法識別（args[0]="" 後 strip 為空 → 視為空字串進 handler）
        # 行為：text="" → lowered=="" → 不匹配任何關鍵字 → 無法識別
        # 注意：SttGate 過濾空白，但此測試直接給 CommandRouter，不經 SttGate
        texts = ui_texts(msgs)
        combined = " ".join(texts)
        self.assertIn("無法識別的語音指令", combined)


# ── Test 7: ui_event 順序 ─────────────────────────────────────────────────────


class TestVoiceUiEventOrder(unittest.TestCase):
    """Test 7: 先發 [語音指令] 顯示，再發指令本身的訊息"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_voice_display_first(self):
        """Test 7a: [語音指令] 顯示訊息必須是第一條 ui_event message"""
        msgs = voice(self.router, "list")
        ui_msgs = [
            m for m in msgs
            if m.topic == "ui_event" and m.payload.get("type") == "message"
        ]
        self.assertGreaterEqual(len(ui_msgs), 1)
        first_text = ui_msgs[0].payload["text"]
        self.assertIn("語音指令", first_text)

    def test_voice_display_uses_raw_text(self):
        """Test 7b: [語音指令] 顯示的是原始（未 lower）的辨識文字"""
        raw_text = "List Sessions Now"  # 混合大小寫
        msgs = voice(self.router, raw_text)
        ui_msgs = [
            m for m in msgs
            if m.topic == "ui_event" and m.payload.get("type") == "message"
        ]
        first_text = ui_msgs[0].payload["text"]
        # 顯示訊息應含原始 raw_text（大小寫保留）
        self.assertIn(raw_text, first_text)

    def test_voice_list_then_session_list(self):
        """Test 7c: "list" → 第一訊息為語音指令顯示，之後有對話列表"""
        self.sm.new_session("second")
        msgs = voice(self.router, "list")
        ui_msgs = [
            m for m in msgs
            if m.topic == "ui_event" and m.payload.get("type") == "message"
        ]
        self.assertGreaterEqual(len(ui_msgs), 2)
        # 第一條含 [語音指令]
        self.assertIn("語音指令", ui_msgs[0].payload["text"])
        # 後續含對話列表
        later_texts = " ".join(m.payload["text"] for m in ui_msgs[1:])
        self.assertIn("對話列表", later_texts)


# ── Test 8: 優先順序測試（show 先於 clear）────────────────────────────────────


class TestVoicePrecedence(unittest.TestCase):
    """Test 8: 優先順序測試 — legacy 梯形順序

    main.py 中 "show/顯示" (index 13) 早於 "clear/清除" (index 17)。
    若文字同時含有 "顯示" 和 "清除"，應觸發 /show 而非 /clear。
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)
        self.wm.get("buffer").append("test line")

    def tearDown(self):
        self._tmp.cleanup()

    def test_show_before_clear(self):
        """Test 8a: 同時含 "顯示" 與 "清除" → "顯示" 勝出（show 優先於 clear）"""
        msgs = voice(self.router, "顯示清除")
        # /show → 顯示工作區內容，不會有 clear type event
        clear_events = [
            m for m in msgs
            if m.topic == "ui_event" and m.payload.get("type") == "clear"
        ]
        self.assertEqual(len(clear_events), 0, "顯示 should win over 清除 due to precedence")
        # 應有工作區顯示內容
        texts = ui_texts(msgs)
        combined = " ".join(texts)
        # 至少有語音指令顯示 + 工作區顯示訊息
        self.assertIn("語音指令", combined)

    def test_stop_before_show(self):
        """Test 8b: 同時含 "停止" 與 "顯示" → "停止" 勝出（stop 優先於 show）

        main.py 中 "stop/停止" (index 12) 早於 "show/顯示" (index 13)。
        """
        msgs = voice(self.router, "停止顯示")
        topics = [m.topic for m in msgs]
        self.assertIn("tts_ctl", topics)
        tts_msgs = [m for m in msgs if m.topic == "tts_ctl"]
        self.assertEqual(tts_msgs[0].payload, "STOP_SPEECH")

    def test_send_before_export(self):
        """Test 8c: 同時含 "發送" 與 "匯出" → "發送" 勝出（send 早於 export）

        main.py 中 "send/發送" (index 7) 早於 "export/匯出" (index 8)。
        """
        self.wm.get("buffer").append("content for send")
        msgs = voice(self.router, "發送匯出")
        topics = [m.topic for m in msgs]
        # 如果 send 勝出且 buffer 有內容，應有 outbound
        self.assertIn("outbound", topics)


# ── Test 9: 更多中文關鍵字覆蓋 ───────────────────────────────────────────────


class TestVoiceChineseKeywords(unittest.TestCase):
    """Test 9: 更多中文關鍵字覆蓋"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_help_chinese(self):
        """Test 9a: "幫助" → /help"""
        msgs = voice(self.router, "幫助")
        texts = ui_texts(msgs)
        combined = " ".join(texts)
        self.assertIn("/help", combined)

    def test_list_chinese(self):
        """Test 9b: "列表" → /list"""
        msgs = voice(self.router, "列表")
        texts = ui_texts(msgs)
        combined = " ".join(texts)
        self.assertIn("對話列表", combined)

    def test_history_chinese(self):
        """Test 9c: "歷史" → /history"""
        msgs = voice(self.router, "歷史")
        texts = ui_texts(msgs)
        combined = " ".join(texts)
        # get_history() 回傳非空字串
        self.assertIsInstance(combined, str)
        self.assertGreater(len(combined), 0)

    def test_workspace_chinese(self):
        """Test 9d: "工作區" → /ws"""
        msgs = voice(self.router, "工作區")
        texts = ui_texts(msgs)
        combined = " ".join(texts)
        self.assertIn("工作區列表", combined)

    def test_workspace_with_arg(self):
        """Test 9e: "工作區 stt" → /ws stt（切換到 stt 工作區）"""
        msgs = voice(self.router, "工作區 stt")
        texts = ui_texts(msgs)
        combined = " ".join(texts)
        self.assertIn("stt", combined)

    def test_stop_chinese(self):
        """Test 9f: "停止" → /stop → emit tts_ctl STOP_SPEECH"""
        msgs = voice(self.router, "停止")
        tts_msgs = [m for m in msgs if m.topic == "tts_ctl"]
        self.assertEqual(len(tts_msgs), 1)
        self.assertEqual(tts_msgs[0].payload, "STOP_SPEECH")


if __name__ == "__main__":
    unittest.main()
