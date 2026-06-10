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

    # ── 9. "PLAY_LAST_ORIGINAL" → chat_ctl {"cmd":"play_last"} ──────────────────
    def test_play_last_emits_chat_ctl(self):
        """PLAY_LAST_ORIGINAL 應 emit chat_ctl {"cmd":"play_last"}，由 ChatFlow 消費。"""
        self.router.handle(Message(topic="commands", payload="PLAY_LAST_ORIGINAL"))
        msgs = _drain(self.router)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].topic, "chat_ctl")
        self.assertEqual(msgs[0].payload, {"cmd": "play_last"})

    # ── 10. 未知 dict 指令 → ui_event 未知指令 ───────────────────────────────
    def test_unknown_dict_cmd_emits_ui_event(self):
        self.router.handle(Message(topic="commands", payload={"cmd": "no_such_cmd"}))
        msgs = _drain(self.router)
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].topic, "ui_event")
        self.assertIn("未知指令", msgs[0].payload["text"])
        self.assertIn("no_such_cmd", msgs[0].payload["text"])


class TestCommandRouterRecorderEvent(unittest.TestCase):
    """recorder_event topic 的處理測試。"""

    def setUp(self):
        self.router = _make_router()

    # ── 11. recording_started（normal 模式）→ status「錄音中」────────────────
    def test_recording_started_normal_mode_status(self):
        """recording_started 在 normal 模式下應 emit status「錄音中」。"""
        self.router.handle(Message(topic="recorder_event", payload={"event": "recording_started"}))
        msgs = _drain(self.router)
        status_msgs = [m for m in msgs if m.topic == "ui_event" and m.payload.get("type") == "status"]
        self.assertEqual(len(status_msgs), 1)
        self.assertEqual(status_msgs[0].payload["text"], "錄音中")
        self.assertTrue(self.router._is_recording)

    # ── 12. recording_started（command 模式）→ status「語音指令中」──────────
    def test_recording_started_command_mode_status(self):
        """先觸發 RECORD_COMMAND_TOGGLE（sets _last_mode="command"），
        再收到 recording_started → status「語音指令中」。"""
        self.router.handle(Message(topic="commands", payload="RECORD_COMMAND_TOGGLE"))
        _drain(self.router)
        self.router.handle(Message(topic="recorder_event", payload={"event": "recording_started"}))
        msgs = _drain(self.router)
        status_msgs = [m for m in msgs if m.topic == "ui_event" and m.payload.get("type") == "status"]
        self.assertEqual(len(status_msgs), 1)
        self.assertEqual(status_msgs[0].payload["text"], "語音指令中")
        self.assertTrue(self.router._is_recording)

    # ── 13. recording_stopped → status「處理中」且 _is_recording=False ───────
    def test_recording_stopped_status_and_flag(self):
        """recording_stopped → emit status「處理中」且 _is_recording 清為 False。"""
        # 先啟動錄音
        self.router.handle(Message(topic="recorder_event", payload={"event": "recording_started"}))
        _drain(self.router)
        self.router.handle(Message(topic="recorder_event", payload={"event": "recording_stopped"}))
        msgs = _drain(self.router)
        status_msgs = [m for m in msgs if m.topic == "ui_event" and m.payload.get("type") == "status"]
        self.assertEqual(len(status_msgs), 1)
        self.assertEqual(status_msgs[0].payload["text"], "處理中")
        self.assertFalse(self.router._is_recording)

    # ── 14. error → gate_ctl normal + [錄音錯誤] 訊息 + status 待機 + _is_recording False
    def test_error_event_resets_state(self):
        """error 事件應 emit gate_ctl normal、[錄音錯誤] system 訊息、status 待機，
        並清 _is_recording。"""
        # 先進入 command 模式
        self.router.handle(Message(topic="commands", payload="RECORD_COMMAND_TOGGLE"))
        _drain(self.router)
        # 模擬已在錄音
        self.router._is_recording = True
        self.router.handle(Message(topic="recorder_event",
                                   payload={"event": "error", "message": "麥克風故障"}))
        msgs = _drain(self.router)
        topics = {m.topic: m.payload for m in msgs}

        self.assertIn("gate_ctl", topics)
        self.assertEqual(topics["gate_ctl"], {"mode": "normal"})

        ui_msgs = [m for m in msgs if m.topic == "ui_event"]
        msg_events = [m for m in ui_msgs if m.payload.get("type") == "message"]
        status_events = [m for m in ui_msgs if m.payload.get("type") == "status"]
        self.assertEqual(len(msg_events), 1)
        self.assertIn("[錄音錯誤]", msg_events[0].payload["text"])
        self.assertIn("麥克風故障", msg_events[0].payload["text"])
        self.assertEqual(len(status_events), 1)
        self.assertEqual(status_events[0].payload["text"], "待機")
        self.assertFalse(self.router._is_recording)
        self.assertEqual(self.router._last_mode, "normal")

    # ── 15. error 後 RECORD_TOGGLE → recorder_ctl START（狀態機已恢復）───────
    def test_error_then_record_toggle_starts_recording(self):
        """error 重設後，RECORD_TOGGLE 應能正常觸發 recorder_ctl START
        （_is_recording 已被重設為 False，狀態機正常恢復）。"""
        # 製造 error，模擬已在錄音
        self.router._is_recording = True
        self.router.handle(Message(topic="recorder_event",
                                   payload={"event": "error", "message": "test"}))
        _drain(self.router)
        # 現在 _is_recording 應為 False，再按 RECORD_TOGGLE → START
        self.router.handle(Message(topic="commands", payload="RECORD_TOGGLE"))
        msgs = _drain(self.router)
        recorder_msgs = [m for m in msgs if m.topic == "recorder_ctl"]
        self.assertEqual(len(recorder_msgs), 1)
        self.assertEqual(recorder_msgs[0].payload, "START")


if __name__ == "__main__":
    unittest.main()
