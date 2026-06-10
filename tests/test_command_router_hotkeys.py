"""modules.CommandRouter 熱鍵訊號單元測試。

執行：python3 -m unittest tests.test_command_router_hotkeys
"""

import os
import queue
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.message import Message
from modules.command_router import CommandRouter
from modules.workspace_manager import WorkspaceManager


def _make_router():
    wm = WorkspaceManager()
    router = CommandRouter(workspace_manager=wm, session_manager=None)
    return router


def _drain(router):
    """取出所有 outbox 訊息，回傳 list[Message]。"""
    msgs = []
    while True:
        try:
            msgs.append(router.outbox.get_nowait())
        except queue.Empty:
            break
    return msgs


class TestCommandRouterHotkeys(unittest.TestCase):

    def setUp(self):
        self.router = _make_router()

    # ── 1. 字串 "RECORD_TOGGLE" → recorder_ctl "START" + gate_ctl normal ──
    def test_record_toggle_string_emits_start_and_gate_normal(self):
        self.router.handle(Message(topic="commands", payload="RECORD_TOGGLE"))
        msgs = _drain(self.router)
        topics = {m.topic: m.payload for m in msgs}
        self.assertIn("recorder_ctl", topics)
        self.assertEqual(topics["recorder_ctl"], "START")
        self.assertIn("gate_ctl", topics)
        self.assertEqual(topics["gate_ctl"], {"mode": "normal"})

    # ── 2. 第二次 "RECORD_TOGGLE" → STOP＋gate_ctl normal（舊版停止也清 command）─
    def test_record_toggle_second_emits_stop_and_gate_normal(self):
        self.router.handle(Message(topic="commands", payload="RECORD_TOGGLE"))
        _drain(self.router)  # 清掉第一次
        self.router.handle(Message(topic="commands", payload="RECORD_TOGGLE"))
        msgs = _drain(self.router)
        topics = {m.topic: m.payload for m in msgs}
        self.assertEqual(topics["recorder_ctl"], "STOP")
        # 舊 main.py：RECORD_TOGGLE 不論開始/停止一律清 is_command_mode
        self.assertEqual(topics["gate_ctl"], {"mode": "normal"})

    # ── 2b. F7 停止錄音時不送 gate_ctl（舊版停止時 is_command_mode 不變）────
    def test_command_toggle_stop_keeps_mode(self):
        self.router.handle(Message(topic="commands", payload="RECORD_COMMAND_TOGGLE"))
        _drain(self.router)
        self.router.handle(Message(topic="commands", payload="RECORD_COMMAND_TOGGLE"))
        msgs = _drain(self.router)
        topics = [m.topic for m in msgs]
        self.assertNotIn("gate_ctl", topics)
        recorder_payload = next(m.payload for m in msgs if m.topic == "recorder_ctl")
        self.assertEqual(recorder_payload, "STOP")

    # ── 2c. F7 開始 → F8 停止：gate 收到 normal（舊版 F8 一律清 command 模式）─
    def test_f7_start_f8_stop_clears_command_mode(self):
        self.router.handle(Message(topic="commands", payload="RECORD_COMMAND_TOGGLE"))
        _drain(self.router)
        self.router.handle(Message(topic="commands", payload="RECORD_TOGGLE"))
        msgs = _drain(self.router)
        topics = {m.topic: m.payload for m in msgs}
        self.assertEqual(topics["recorder_ctl"], "STOP")
        self.assertEqual(topics["gate_ctl"], {"mode": "normal"})

    # ── 3. "RECORD_COMMAND_TOGGLE" → recorder_ctl "START" + gate_ctl command ─
    def test_record_command_toggle_emits_start_and_gate_command(self):
        self.router.handle(Message(topic="commands", payload="RECORD_COMMAND_TOGGLE"))
        msgs = _drain(self.router)
        topics = {m.topic: m.payload for m in msgs}
        self.assertIn("recorder_ctl", topics)
        self.assertEqual(topics["recorder_ctl"], "START")
        self.assertIn("gate_ctl", topics)
        self.assertEqual(topics["gate_ctl"], {"mode": "command"})

    # ── 4. "FORCE_STOP_TTS" → tts_ctl "STOP_SPEECH" + ui_event status 待機 ──
    def test_force_stop_tts_emits_tts_ctl_and_status(self):
        self.router.handle(Message(topic="commands", payload="FORCE_STOP_TTS"))
        msgs = _drain(self.router)
        topics = {m.topic: m.payload for m in msgs}
        self.assertIn("tts_ctl", topics)
        self.assertEqual(topics["tts_ctl"], "STOP_SPEECH")
        self.assertIn("ui_event", topics)
        self.assertEqual(topics["ui_event"], {"type": "status", "text": "待機"})

    # ── 5. 未知字串 → ui_event 未知指令，無其他訊息 ─────────────────────────
    def test_unknown_string_emits_ui_event_only(self):
        self.router.handle(Message(topic="commands", payload="NO_SUCH_SIGNAL"))
        msgs = _drain(self.router)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].topic, "ui_event")
        self.assertIn("未知指令", msgs[0].payload["text"])
        self.assertIn("NO_SUCH_SIGNAL", msgs[0].payload["text"])

    # ── 6. dict 形式 {"cmd":"record_toggle"} 與字串形式行為相同 ──────────────
    def test_dict_record_toggle_same_as_string(self):
        self.router.handle(Message(topic="commands", payload={"cmd": "record_toggle"}))
        msgs = _drain(self.router)
        topics = {m.topic: m.payload for m in msgs}
        self.assertIn("recorder_ctl", topics)
        self.assertEqual(topics["recorder_ctl"], "START")
        self.assertIn("gate_ctl", topics)
        self.assertEqual(topics["gate_ctl"], {"mode": "normal"})

    # ── 7. record_command_toggle START → record_toggle → STOP（共用 _is_recording）
    def test_command_toggle_start_then_record_toggle_stop(self):
        # F8: start command mode recording
        self.router.handle(Message(topic="commands", payload="RECORD_COMMAND_TOGGLE"))
        msgs = _drain(self.router)
        recorder_payloads = [m.payload for m in msgs if m.topic == "recorder_ctl"]
        self.assertEqual(recorder_payloads, ["START"])
        self.assertTrue(self.router._is_recording)

        # F7: stop (since _is_recording is now True, toggle → False → STOP)
        self.router.handle(Message(topic="commands", payload="RECORD_TOGGLE"))
        msgs = _drain(self.router)
        recorder_payloads = [m.payload for m in msgs if m.topic == "recorder_ctl"]
        self.assertEqual(recorder_payloads, ["STOP"])
        self.assertFalse(self.router._is_recording)

    # ── 8. "QUICK_SEND" → ui_event placeholder 訊息 ───────────────────────────
    def test_quick_send_emits_placeholder_ui_event(self):
        self.router.handle(Message(topic="commands", payload="QUICK_SEND"))
        msgs = _drain(self.router)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].topic, "ui_event")
        self.assertEqual(msgs[0].payload["type"], "message")

    # ── 9. "PLAY_LAST_ORIGINAL" → ui_event placeholder 訊息 ──────────────────
    def test_play_last_emits_placeholder_ui_event(self):
        self.router.handle(Message(topic="commands", payload="PLAY_LAST_ORIGINAL"))
        msgs = _drain(self.router)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].topic, "ui_event")

    # ── 10. 未知 dict 指令 → ui_event 未知指令 ───────────────────────────────
    def test_unknown_dict_cmd_emits_ui_event(self):
        self.router.handle(Message(topic="commands", payload={"cmd": "no_such_cmd"}))
        msgs = _drain(self.router)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].topic, "ui_event")
        self.assertIn("未知指令", msgs[0].payload["text"])
        self.assertIn("no_such_cmd", msgs[0].payload["text"])


if __name__ == "__main__":
    unittest.main()
