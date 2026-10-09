"""ChatFlow 模組單元測試——summary_out 與 play_last。

執行：python3 -m unittest tests.test_chat_flow_summary
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.message import Message
from modules.chat_flow import ChatFlow
from tests._helpers import drain, make_sm
from tests._chat_flow_helpers import chat_ctl, inbound, summary_out


class TestChatFlowSummaryOut(unittest.TestCase):
    """summary_out 相關測試。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.sm = make_sm(self.tmp)

    # ── 測試 9a：summary_out status → ui_event status ──────────────────────

    def test_summary_out_status_ui_event(self):
        """summary_out type=status → ui_event status。"""
        cf = ChatFlow(self.sm)
        cf.handle(summary_out("status", "摘要產生中"))
        msgs = drain(cf)
        ui_msgs = [m for m in msgs if m.topic == "ui_event"]
        self.assertTrue(any(
            m.payload.get("type") == "status" and m.payload.get("text") == "摘要產生中"
            for m in ui_msgs
        ))
        # 不應有 tts
        self.assertFalse(any(m.topic == "tts" for m in msgs))

    # ── 測試 9b：summary_out summary → 「回覆摘要：...」ui + tts medium ────

    def test_summary_out_summary_ui_and_tts_medium(self):
        """summary_out type=summary → ui_event summary 訊息 + tts medium。"""
        cf = ChatFlow(self.sm)
        cf.handle(summary_out("summary", "這是摘要"))
        msgs = drain(cf)
        expected_text = "回覆摘要：這是摘要"
        ui_msgs = [m for m in msgs if m.topic == "ui_event"]
        tts_msgs = [m for m in msgs if m.topic == "tts"]
        self.assertTrue(any(
            m.payload.get("type") == "message"
            and m.payload.get("role") == "summary"
            and m.payload.get("text") == expected_text
            for m in ui_msgs
        ))
        self.assertTrue(any(
            m.payload.get("text") == expected_text
            and m.payload.get("priority") == "medium"
            for m in tts_msgs
        ))

    # ── 測試 9c：summary_out summary_failed → 提示＋改播原文（B14）──────────

    def test_summary_failed_falls_back_to_original_text(self):
        """summary_out type=summary_failed → system 提示「[摘要失敗] …，改播原文」＋ tts medium 原文。"""
        cf = ChatFlow(self.sm)
        cf.handle(Message(topic="summary_out", payload={
            "type": "summary_failed", "message": "連線逾時", "text": "很長的原文回覆",
        }))
        msgs = drain(cf)
        ui = [m.payload for m in msgs if m.topic == "ui_event"]
        tts = [m.payload for m in msgs if m.topic == "tts"]
        self.assertEqual(ui, [{"type": "message", "role": "system",
                               "text": "[摘要失敗] 連線逾時，改播原文"}])
        self.assertEqual(tts, [{"text": "很長的原文回覆", "priority": "medium"}])

    def test_summary_failed_without_text_only_notifies(self):
        cf = ChatFlow(self.sm)
        cf.handle(Message(topic="summary_out", payload={"type": "summary_failed", "message": "空摘要"}))
        msgs = drain(cf)
        self.assertEqual([m.topic for m in msgs], ["ui_event"])


class TestChatFlowPlayLast(unittest.TestCase):
    """chat_ctl play_last 相關測試。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.sm = make_sm(self.tmp)

    # ── 測試 10a：play_last 有內容 → ui + tts 原文 ──────────────────────────

    def test_play_last_with_content(self):
        """chat_ctl play_last（有 last_full_response）→ ui 系統訊息 + tts medium 原文。"""
        cf = ChatFlow(self.sm, summary_threshold=20)
        # 先產生一次 ChatReply 讓 last_full_response 被記錄
        cf.handle(inbound("ChatReply", Content={"full_response": "原文回覆"}))
        drain(cf)  # 清空

        cf.handle(chat_ctl("play_last"))
        msgs = drain(cf)
        ui_msgs = [m for m in msgs if m.topic == "ui_event"]
        tts_msgs = [m for m in msgs if m.topic == "tts"]
        self.assertTrue(any(
            m.payload.get("type") == "message"
            and m.payload.get("role") == "system"
            and "播放最後一次回覆原文" in m.payload.get("text", "")
            for m in ui_msgs
        ))
        self.assertTrue(any(
            m.payload.get("text") == "原文回覆"
            and m.payload.get("priority") == "medium"
            for m in tts_msgs
        ))

    # ── 測試 10b：play_last 無內容（全新模組）→ 不 emit 任何訊息 ────────────

    def test_play_last_without_content_emits_nothing(self):
        """chat_ctl play_last（全新模組，無 last_full_response）→ 不 emit 任何訊息。"""
        cf = ChatFlow(self.sm)
        cf.handle(chat_ctl("play_last"))
        msgs = drain(cf)
        self.assertEqual(msgs, [])

    # ── 測試額外：未知 chat_ctl cmd → 忽略，不 emit ────────────────────────

    def test_unknown_chat_ctl_ignored(self):
        """chat_ctl 未知指令 → 忽略，不 emit 任何訊息。"""
        cf = ChatFlow(self.sm)
        cf.handle(Message(topic="chat_ctl", payload={"cmd": "unknown_cmd"}))
        msgs = drain(cf)
        self.assertEqual(msgs, [])


if __name__ == "__main__":
    unittest.main()
