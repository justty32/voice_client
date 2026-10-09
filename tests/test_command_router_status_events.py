"""modules.CommandRouter 錄音／STT 狀態事件（recorder_event、stt_event）單元測試。

自 tests/test_command_router_hotkeys.py 拆出。
執行：python3 -m unittest tests.test_command_router_status_events
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.message import Message
from tests._helpers import drain as _drain
from tests._router_helpers import make_bare_router as _make_router


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

    # ── 13b. recording_stopped flushed=False（靜音）→ status「待機」────────
    def test_recording_stopped_without_flush_returns_idle(self):
        """靜音錄音停止時沒有音訊送往 STT，狀態列應直接回「待機」（B8）。"""
        self.router.handle(Message(topic="recorder_event", payload={"event": "recording_started"}))
        _drain(self.router)
        self.router.handle(Message(topic="recorder_event",
                                   payload={"event": "recording_stopped", "flushed": False}))
        msgs = _drain(self.router)
        status_msgs = [m for m in msgs if m.topic == "ui_event" and m.payload.get("type") == "status"]
        self.assertEqual([m.payload["text"] for m in status_msgs], ["待機"])
        self.assertFalse(self.router._is_recording)

    # ── 13c. recording_stopped flushed=True → status「處理中」──────────────
    def test_recording_stopped_with_flush_keeps_processing(self):
        self.router.handle(Message(topic="recorder_event",
                                   payload={"event": "recording_stopped", "flushed": True}))
        msgs = _drain(self.router)
        status_msgs = [m for m in msgs if m.topic == "ui_event" and m.payload.get("type") == "status"]
        self.assertEqual([m.payload["text"] for m in status_msgs], ["處理中"])

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


class TestCommandRouterSttEvent(unittest.TestCase):
    """stt_event：STT 結束後狀態列回「待機」；錯誤另顯示訊息（B7、B8、D6）。"""

    def setUp(self):
        self.router = _make_router()

    def _ui(self, payload):
        self.router.handle(Message(topic="stt_event", payload=payload))
        msgs = _drain(self.router)
        self.assertTrue(all(m.topic == "ui_event" for m in msgs))
        status = [m.payload["text"] for m in msgs if m.payload.get("type") == "status"]
        texts = [m.payload["text"] for m in msgs if m.payload.get("type") == "message"]
        return status, texts

    def test_stt_error_shows_message_and_idle(self):
        status, texts = self._ui({"event": "stt_error", "message": "STT 模型未載入"})
        self.assertEqual(texts, ["[STT 錯誤] STT 模型未載入"])
        self.assertEqual(status, ["待機"])

    def test_stt_empty_returns_idle(self):
        status, texts = self._ui({"event": "stt_empty"})
        self.assertEqual((status, texts), (["待機"], []))

    def test_stt_done_returns_idle(self):
        status, texts = self._ui({"event": "stt_done"})
        self.assertEqual((status, texts), (["待機"], []))

    def test_stt_event_while_recording_keeps_status(self):
        """錄音中途切片的 STT 結果不得把「錄音中」蓋成「待機」；錯誤訊息仍顯示。"""
        self.router._is_recording = True
        self.assertEqual(self._ui({"event": "stt_done"}), ([], []))
        status, texts = self._ui({"event": "stt_error", "message": "x"})
        self.assertEqual(status, [])
        self.assertEqual(texts, ["[STT 錯誤] x"])

    def test_unknown_stt_event_ignored(self):
        self.assertEqual(self._ui({"event": "???"}), ([], []))


if __name__ == "__main__":
    unittest.main()
