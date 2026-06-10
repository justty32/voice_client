"""modules.SttGate 單元測試。

執行：python3 -m unittest tests.test_stt_gate
"""

import os
import queue
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.message import Message
from modules.stt_gate import SttGate


class TestSttGate(unittest.TestCase):
    def setUp(self):
        self.gate = SttGate()

    def _drain(self):
        """取出所有 outbox 訊息，回傳 list[Message]。"""
        msgs = []
        while True:
            try:
                msgs.append(self.gate.outbox.get_nowait())
            except queue.Empty:
                break
        return msgs

    # ── 1. 預設模式 normal：stt_text → ui_event(voice) + raw_text ──────────
    def test_default_mode_is_normal(self):
        self.assertEqual(self.gate.mode, "normal")

    def test_normal_mode_emits_ui_event_before_raw_text(self):
        """normal 模式先發射 ui_event(voice)，再發射 raw_text（順序必須正確）。"""
        self.gate.handle(Message(topic="stt_text", payload="你好"))
        msgs = self._drain()
        self.assertEqual(len(msgs), 2, "normal 模式應發射 2 條訊息")
        self.assertEqual(msgs[0].topic, "ui_event")
        self.assertEqual(msgs[1].topic, "raw_text")

    def test_normal_mode_ui_event_has_voice_role(self):
        """normal 模式的 ui_event payload 必須含 role=voice、text=辨識文字。"""
        self.gate.handle(Message(topic="stt_text", payload="你好"))
        msgs = self._drain()
        ui_msg = msgs[0]
        self.assertEqual(ui_msg.payload.get("type"), "message")
        self.assertEqual(ui_msg.payload.get("role"), "voice")
        self.assertEqual(ui_msg.payload.get("text"), "你好")

    def test_normal_mode_raw_text_payload_equals_input(self):
        """normal 模式的 raw_text payload 必須等於辨識文字。"""
        self.gate.handle(Message(topic="stt_text", payload="你好"))
        msgs = self._drain()
        raw_msg = msgs[1]
        self.assertEqual(raw_msg.topic, "raw_text")
        self.assertEqual(raw_msg.payload, "你好")

    # ── 2. gate_ctl command → stt_text 路由到 commands（不發 ui_event）───────
    def test_command_mode_routes_stt_text_to_commands(self):
        """command 模式只發射 commands，不發 ui_event voice 訊息。"""
        self.gate.handle(Message(topic="gate_ctl", payload={"mode": "command"}))
        self.gate.handle(Message(topic="stt_text", payload="發送"))
        msgs = self._drain()
        self.assertEqual(len(msgs), 1, "command 模式應只發射 1 條訊息（commands）")
        self.assertEqual(msgs[0].topic, "commands")
        self.assertEqual(msgs[0].payload, {"cmd": "voice", "args": ["發送"]})

    def test_command_mode_does_not_emit_voice_ui_event(self):
        """command 模式不可發射 role=voice 的 ui_event（[語音指令] 顯示由 CommandRouter 負責）。"""
        self.gate.handle(Message(topic="gate_ctl", payload={"mode": "command"}))
        self._drain()
        self.gate.handle(Message(topic="stt_text", payload="刪除"))
        msgs = self._drain()
        voice_ui_events = [
            m for m in msgs
            if m.topic == "ui_event" and isinstance(m.payload, dict)
               and m.payload.get("role") == "voice"
        ]
        self.assertEqual(voice_ui_events, [], "command 模式不應發射 voice ui_event")

    # ── 3. gate_ctl normal 切回 ────────────────────────────────────
    def test_gate_ctl_switches_back_to_normal(self):
        self.gate.handle(Message(topic="gate_ctl", payload={"mode": "command"}))
        self.assertEqual(self.gate.mode, "command")
        self.gate.handle(Message(topic="gate_ctl", payload={"mode": "normal"}))
        self.assertEqual(self.gate.mode, "normal")
        self.gate.handle(Message(topic="stt_text", payload="回到正常"))
        msgs = self._drain()
        # 現在應有 2 條：ui_event + raw_text
        self.assertEqual(len(msgs), 2)
        # 最後一條是 raw_text
        self.assertEqual(msgs[-1].topic, "raw_text")

    # ── 4. 非法 gate_ctl 忽略，模式不變，無任何發射 ───────────────
    def test_invalid_gate_ctl_dict_is_ignored(self):
        self.gate.handle(Message(topic="gate_ctl", payload={"mode": "weird"}))
        self.assertEqual(self.gate.mode, "normal")
        self.assertEqual(self._drain(), [])

    def test_invalid_gate_ctl_non_dict_is_ignored(self):
        self.gate.handle(Message(topic="gate_ctl", payload="command"))
        self.assertEqual(self.gate.mode, "normal")
        self.assertEqual(self._drain(), [])

    # ── 5. 空白文字在兩種模式下均不發射 ───────────────────────────
    def test_blank_text_emits_nothing_in_normal_mode(self):
        self.gate.handle(Message(topic="stt_text", payload="   "))
        self.assertEqual(self._drain(), [])

    def test_blank_text_emits_nothing_in_command_mode(self):
        self.gate.handle(Message(topic="gate_ctl", payload={"mode": "command"}))
        self._drain()  # 清掉 gate_ctl 不應有任何輸出（確保乾淨）
        self.gate.handle(Message(topic="stt_text", payload="\t\n"))
        self.assertEqual(self._drain(), [])

    # ── 6. command 模式跨多筆訊息持續 ─────────────────────────────
    def test_command_mode_persists_across_multiple_stt_messages(self):
        self.gate.handle(Message(topic="gate_ctl", payload={"mode": "command"}))
        self._drain()
        self.gate.handle(Message(topic="stt_text", payload="第一句"))
        self.gate.handle(Message(topic="stt_text", payload="第二句"))
        msgs = self._drain()
        self.assertEqual(len(msgs), 2)
        for msg in msgs:
            self.assertEqual(msg.topic, "commands")
            self.assertEqual(msg.payload["cmd"], "voice")
        self.assertEqual(msgs[0].payload["args"], ["第一句"])
        self.assertEqual(msgs[1].payload["args"], ["第二句"])
        # 模式仍為 command
        self.assertEqual(self.gate.mode, "command")


if __name__ == "__main__":
    unittest.main()
