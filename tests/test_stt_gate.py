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

    # ── 1. 預設模式 normal：stt_text → raw_text ────────────────────
    def test_default_mode_is_normal(self):
        self.assertEqual(self.gate.mode, "normal")

    def test_normal_mode_routes_stt_text_to_raw_text(self):
        self.gate.handle(Message(topic="stt_text", payload="你好"))
        msgs = self._drain()
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].topic, "raw_text")
        self.assertEqual(msgs[0].payload, "你好")

    # ── 2. gate_ctl command → stt_text 路由到 commands ────────────
    def test_command_mode_routes_stt_text_to_commands(self):
        self.gate.handle(Message(topic="gate_ctl", payload={"mode": "command"}))
        self.gate.handle(Message(topic="stt_text", payload="發送"))
        msgs = self._drain()
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].topic, "commands")
        self.assertEqual(msgs[0].payload, {"cmd": "voice", "args": ["發送"]})

    # ── 3. gate_ctl normal 切回 ────────────────────────────────────
    def test_gate_ctl_switches_back_to_normal(self):
        self.gate.handle(Message(topic="gate_ctl", payload={"mode": "command"}))
        self.assertEqual(self.gate.mode, "command")
        self.gate.handle(Message(topic="gate_ctl", payload={"mode": "normal"}))
        self.assertEqual(self.gate.mode, "normal")
        self.gate.handle(Message(topic="stt_text", payload="回到正常"))
        msgs = self._drain()
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].topic, "raw_text")

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
