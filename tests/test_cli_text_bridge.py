"""modules.CliTextBridge 單元測試。

執行：python3 -m unittest tests.test_cli_text_bridge
"""

import os
import queue
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.message import Message
from modules.cli_text_bridge import CliTextBridge
from terminal_input import EXIT_SIGNAL


class TestCliTextBridge(unittest.TestCase):
    def setUp(self):
        self.bridge = CliTextBridge()

    def _drain(self):
        """取出所有 outbox 訊息，回傳 list[Message]。"""
        msgs = []
        while True:
            try:
                msgs.append(self.bridge.outbox.get_nowait())
            except queue.Empty:
                break
        return msgs

    # ── 1. EXIT_SIGNAL → 只發 app_ctl "EXIT"，不發 raw_text ─────────────────
    def test_exit_signal_emits_app_ctl_only(self):
        """EXIT_SIGNAL 只發射 app_ctl "EXIT"，不發射任何其他訊息。"""
        self.bridge.handle(Message(topic="cli_text", payload=EXIT_SIGNAL))
        msgs = self._drain()
        self.assertEqual(len(msgs), 1, "EXIT_SIGNAL 應只發射一條訊息")
        self.assertEqual(msgs[0].topic, "app_ctl")
        self.assertEqual(msgs[0].payload, "EXIT")

    def test_exit_signal_does_not_emit_raw_text(self):
        """EXIT_SIGNAL 不可發射 raw_text。"""
        self.bridge.handle(Message(topic="cli_text", payload=EXIT_SIGNAL))
        msgs = self._drain()
        topics = [m.topic for m in msgs]
        self.assertNotIn("raw_text", topics)

    # ── 2. 空白文字 → 不發射任何訊息 ────────────────────────────────────────
    def test_blank_payload_emits_nothing(self):
        """純空白（spaces/tab/newline）的 payload 應不發射任何訊息。"""
        for blank in ("", "   ", "\t", "\n", "  \t  \n  "):
            with self.subTest(blank=repr(blank)):
                self.bridge.handle(Message(topic="cli_text", payload=blank))
                msgs = self._drain()
                self.assertEqual(msgs, [], f"空白 payload {blank!r} 不應有任何輸出")

    # ── 3. 正常文字 → 先 ui_event(user)，後 raw_text，且角色正確 ─────────────
    def test_text_emits_ui_event_before_raw_text(self):
        """正常文字先發射 ui_event（role=user），再發射 raw_text；順序必須正確。"""
        self.bridge.handle(Message(topic="cli_text", payload="你好世界"))
        msgs = self._drain()
        self.assertEqual(len(msgs), 2, "正常文字應發射恰好 2 條訊息")
        # 順序：ui_event 在前
        self.assertEqual(msgs[0].topic, "ui_event")
        self.assertEqual(msgs[1].topic, "raw_text")

    def test_text_ui_event_has_correct_role_and_text(self):
        """ui_event payload 必須含 type=message、role=user、text=輸入文字。"""
        text = "測試輸入"
        self.bridge.handle(Message(topic="cli_text", payload=text))
        msgs = self._drain()
        ui_msg = msgs[0]
        self.assertEqual(ui_msg.payload.get("type"), "message")
        self.assertEqual(ui_msg.payload.get("role"), "user")
        self.assertEqual(ui_msg.payload.get("text"), text)

    def test_text_raw_text_payload_equals_input(self):
        """raw_text payload 必須等於原始輸入文字。"""
        text = "Hello CLI"
        self.bridge.handle(Message(topic="cli_text", payload=text))
        msgs = self._drain()
        raw_msg = msgs[1]
        self.assertEqual(raw_msg.topic, "raw_text")
        self.assertEqual(raw_msg.payload, text)

    # ── 4. module 基本屬性 ──────────────────────────────────────────────────
    def test_module_name_and_consumes(self):
        """模組名稱為 cli_text_bridge，消費 cli_text topic。"""
        self.assertEqual(self.bridge.name, "cli_text_bridge")
        self.assertIn("cli_text", self.bridge.consumes)


if __name__ == "__main__":
    unittest.main()
