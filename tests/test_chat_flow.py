"""tests.test_chat_flow — ChatFlow 模組單元測試。

執行：python3 -m unittest tests.test_chat_flow -v
"""

import configparser
import os
import queue
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.message import Message
from modules.chat_flow import ChatFlow
from session_manager import SessionManager


# ── 共用 fixtures ──────────────────────────────────────────────────────────────


def make_sm(tmp: str) -> SessionManager:
    cfg = configparser.ConfigParser()
    cfg["WORKSPACE"] = {
        "sessions_file": os.path.join(tmp, "output", ".sessions.json"),
        "deleted_sessions_dir": os.path.join(tmp, "output", "deleted"),
    }
    sm = SessionManager(cfg)
    sm.new_session("default")
    return sm


def drain(module) -> list[Message]:
    """取出所有 outbox 訊息，回傳 list[Message]。"""
    msgs = []
    while True:
        try:
            msgs.append(module.outbox.get_nowait())
        except queue.Empty:
            break
    return msgs


def inbound(type_: str, **kwargs) -> Message:
    payload = {"type": type_}
    payload.update(kwargs)
    return Message(topic="inbound", payload=payload)


def summary_out(type_: str, text: str) -> Message:
    return Message(topic="summary_out", payload={"type": type_, "text": text})


def chat_ctl(cmd: str) -> Message:
    return Message(topic="chat_ctl", payload={"cmd": cmd})


# ── 測試案例 ───────────────────────────────────────────────────────────────────


class TestChatFlowChatReply(unittest.TestCase):
    """ChatReply 相關測試。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.sm = make_sm(self.tmp)

    def _make_chat_reply_msg(self, full_response: str) -> Message:
        return inbound("ChatReply", Content={"full_response": full_response})

    # ── 測試 1：短回覆 → 直接 TTS medium，不發 summary_req ──────────────────

    def test_short_response_direct_tts_no_summary_req(self):
        """ChatReply 短回覆（< threshold）→ tts medium 直接發送，無 summary_req。"""
        cf = ChatFlow(self.sm, summary_threshold=20, slm_enabled=True)
        cf.handle(self._make_chat_reply_msg("短回覆"))
        msgs = drain(cf)
        topics = [m.topic for m in msgs]
        self.assertIn("tts", topics)
        self.assertNotIn("summary_req", topics)
        tts_msg = next(m for m in msgs if m.topic == "tts")
        self.assertEqual(tts_msg.payload["text"], "短回覆")
        self.assertEqual(tts_msg.payload["priority"], "medium")

    # ── 測試 2：長回覆、slm_enabled=True → summary_req，無直接 TTS 原文 ────

    def test_long_response_summary_req_no_direct_tts(self):
        """ChatReply 長回覆（>= threshold，slm_enabled=True）→ summary_req，無直接 tts 原文。"""
        cf = ChatFlow(self.sm, summary_threshold=5, slm_enabled=True)
        long_text = "這是一段超過門檻的長回覆文字"
        cf.handle(self._make_chat_reply_msg(long_text))
        msgs = drain(cf)
        topics = [m.topic for m in msgs]
        self.assertIn("summary_req", topics)
        # 不應有 tts
        self.assertNotIn("tts", topics)
        # summary_req 格式
        sr = next(m for m in msgs if m.topic == "summary_req")
        self.assertEqual(sr.payload["cmd"], "summary")
        self.assertEqual(sr.payload["text"], long_text)
        self.assertEqual(sr.payload["title"], self.sm.current_title)

    # ── 測試 3：slm_enabled=False → 長回覆也走直接 TTS ──────────────────────

    def test_slm_disabled_always_direct_tts(self):
        """slm_enabled=False 時，無論回覆長短一律直接發 tts，不走 summary_req。"""
        cf = ChatFlow(self.sm, summary_threshold=5, slm_enabled=False)
        long_text = "這是一段超過門檻的長回覆文字"
        cf.handle(self._make_chat_reply_msg(long_text))
        msgs = drain(cf)
        topics = [m.topic for m in msgs]
        self.assertIn("tts", topics)
        self.assertNotIn("summary_req", topics)

    # ── 測試 4：ChatReply 寫入助理訊息至會話歷史 ────────────────────────────

    def test_chat_reply_writes_assistant_to_history(self):
        """ChatReply 非空回覆 → sm.add_message("assistant", ...) 寫入歷史。"""
        cf = ChatFlow(self.sm, summary_threshold=20)
        cf.handle(self._make_chat_reply_msg("AI 回覆內容"))
        session = self.sm.get_current_session()
        history = session["history"]
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0][0], "assistant")
        self.assertEqual(history[0][1], "AI 回覆內容")

    # ── 測試 5：last_full_response 記錄 ────────────────────────────────────

    def test_last_full_response_recorded(self):
        """ChatReply 非空回覆 → last_full_response 記錄正確。"""
        cf = ChatFlow(self.sm, summary_threshold=20)
        cf.handle(self._make_chat_reply_msg("最後一次完整回覆"))
        self.assertEqual(cf.last_full_response, "最後一次完整回覆")

    # ── 測試 6：空 full_response → 只發 status 待機 ────────────────────────

    def test_empty_full_response_only_status(self):
        """ChatReply full_response 為空 → 只發 ui_event status 待機，無歷史寫入與 tts。"""
        cf = ChatFlow(self.sm, summary_threshold=20)
        cf.handle(self._make_chat_reply_msg(""))
        msgs = drain(cf)
        topics = [m.topic for m in msgs]
        # 不應寫歷史
        session = self.sm.get_current_session()
        self.assertEqual(len(session["history"]), 0)
        # 不應有 tts 或 summary_req
        self.assertNotIn("tts", topics)
        self.assertNotIn("summary_req", topics)
        # 應有 ui_event status 待機
        ui_msgs = [m for m in msgs if m.topic == "ui_event"]
        self.assertTrue(any(
            m.payload.get("type") == "status" and m.payload.get("text") == "待機"
            for m in ui_msgs
        ))

    # ── 測試 11：ChatReply status 待機 必為最後一筆 emit ────────────────────

    def test_chat_reply_status_daiji_is_last_emission(self):
        """ChatReply（非空）→ ui_event status 待機 必為所有 emit 的最後一筆。"""
        cf = ChatFlow(self.sm, summary_threshold=20, slm_enabled=True)
        cf.handle(self._make_chat_reply_msg("短回覆測試"))
        msgs = drain(cf)
        self.assertTrue(len(msgs) > 0, "應有 emit")
        last = msgs[-1]
        self.assertEqual(last.topic, "ui_event")
        self.assertEqual(last.payload.get("type"), "status")
        self.assertEqual(last.payload.get("text"), "待機")


class TestChatFlowStatusUpdateAndError(unittest.TestCase):
    """StatusUpdate 與 Error 相關測試。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.sm = make_sm(self.tmp)

    # ── 測試 7：StatusUpdate → ui status + tts low ──────────────────────────

    def test_status_update_ui_and_tts_low(self):
        """StatusUpdate → ui_event status + tts low。"""
        cf = ChatFlow(self.sm)
        cf.handle(inbound("StatusUpdate", text="處理中"))
        msgs = drain(cf)
        ui_msgs = [m for m in msgs if m.topic == "ui_event"]
        tts_msgs = [m for m in msgs if m.topic == "tts"]
        self.assertTrue(any(
            m.payload.get("type") == "status" and m.payload.get("text") == "處理中"
            for m in ui_msgs
        ))
        self.assertTrue(any(
            m.payload.get("text") == "處理中" and m.payload.get("priority") == "low"
            for m in tts_msgs
        ))

    # ── 測試 8：Error → [錯誤] 訊息 + tts high ──────────────────────────────

    def test_error_ui_message_and_tts_high(self):
        """Error → ui_event [錯誤] 系統訊息 + tts high。"""
        cf = ChatFlow(self.sm)
        cf.handle(inbound("Error", message="連線中斷"))
        msgs = drain(cf)
        ui_msgs = [m for m in msgs if m.topic == "ui_event"]
        tts_msgs = [m for m in msgs if m.topic == "tts"]
        self.assertTrue(any(
            m.payload.get("type") == "message"
            and m.payload.get("role") == "system"
            and "[錯誤] 連線中斷" in m.payload.get("text", "")
            for m in ui_msgs
        ))
        self.assertTrue(any(
            "發生錯誤：連線中斷" in m.payload.get("text", "")
            and m.payload.get("priority") == "high"
            for m in tts_msgs
        ))


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
