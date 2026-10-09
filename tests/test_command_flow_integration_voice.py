"""指令流整合測試：熱鍵／語音指令／終端全鏈在真實 Exchange 上驗證——熱鍵、語音指令模式與 normal 模式。

執行：python3 -m unittest tests.test_command_flow_integration_voice
"""

import os
import queue
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.adapter import InboxAdapter, OutboxAdapter
from core.exchange import Exchange
from modules.command_router import CommandRouter
from modules.stt_gate import SttGate
from modules.workspace_manager import WorkspaceManager
from tests._helpers import make_sm, wait_until


# ── Test 1: 熱鍵流 ──────────────────────────────────────────────────────────


class TestHotkeyFlow(unittest.TestCase):
    """Test 1: 裸 key_signal_queue → OutboxAdapter(commands) → CommandRouter
    → InboxAdapter(recorder_ctl) → 裸 recorder_cmd_queue 收到 "START"。
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()

        # 外設裸 queue
        self.key_signal_queue = queue.Queue()    # 鍵盤模擬輸出
        self.recorder_cmd_queue = queue.Queue()  # 錄音指令消費

        # 模組
        self.wm = WorkspaceManager()
        self.sm = make_sm(self._tmp.name)
        self.router = CommandRouter(
            workspace_manager=self.wm,
            session_manager=self.sm,
            export_dir=self._tmp.name,
        )

        # Exchange 配線
        self.ex = Exchange(idle_sleep=0.001)

        # 生產者：熱鍵訊號 → commands
        self.ex.register_producer(
            "hotkeys",
            OutboxAdapter(self.key_signal_queue, topic="commands", source="hotkeys"),
        )

        # CommandRouter：消費 commands，生產多個 topic
        self.router.attach(self.ex)

        # 消費者：recorder_ctl → 裸 queue
        self.ex.register_consumer("recorder_ctl", InboxAdapter(self.recorder_cmd_queue))

        self.ex.start()
        self.router.start()

    def tearDown(self):
        self.router.stop()
        self.ex.stop()
        self._tmp.cleanup()

    def test_hotkey_record_toggle_sends_start(self):
        """RECORD_TOGGLE 字串訊號 → recorder_ctl "START" 到達裸 queue。"""
        self.key_signal_queue.put("RECORD_TOGGLE")
        self.assertTrue(
            wait_until(lambda: not self.recorder_cmd_queue.empty()),
            "recorder_cmd_queue 超時未收到訊息",
        )
        msg = self.recorder_cmd_queue.get_nowait()
        self.assertEqual(msg, "START")


# ── Test 2: 語音指令模式全鏈 ─────────────────────────────────────────────────


class TestVoiceCommandModeFlow(unittest.TestCase):
    """Test 2: record_command_toggle → gate_ctl command 模式 → stt_text "send"
    → SttGate → commands voice → CommandRouter /send → outbound 收到 payload。

    前置條件：buffer 工作區預先放一筆 "hello"。
    斷言：outbound payload["Content"] == "hello"，且 payload 含 "Title"。
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()

        # 外設裸 queue
        self.cmd_producer_queue = queue.Queue()   # 終端/熱鍵指令入口 → commands
        self.stt_text_queue = queue.Queue()        # STT 輸出 → stt_text
        self.outbound_queue = queue.Queue()        # 收集 outbound payload

        # 模組
        self.wm = WorkspaceManager()
        self.sm = make_sm(self._tmp.name)
        self.gate = SttGate()
        self.router = CommandRouter(
            workspace_manager=self.wm,
            session_manager=self.sm,
            export_dir=self._tmp.name,
        )

        # Exchange 配線
        self.ex = Exchange(idle_sleep=0.001)

        # 生產者 1：指令佇列 → commands（熱鍵 / 終端 / 測試注入）
        self.ex.register_producer(
            "cmd_producer",
            OutboxAdapter(self.cmd_producer_queue, topic="commands", source="test"),
        )

        # 生產者 2：STT 文字 → stt_text
        self.ex.register_producer(
            "stt",
            OutboxAdapter(self.stt_text_queue, topic="stt_text", source="stt"),
        )

        # SttGate：消費 stt_text + gate_ctl，生產 raw_text + commands
        self.gate.attach(self.ex)

        # CommandRouter：消費 commands，生產 recorder_ctl / gate_ctl / outbound / ui_event …
        self.router.attach(self.ex)

        # WorkspaceManager：消費 raw_text
        self.wm.attach(self.ex)

        # 消費者：outbound → 裸 queue
        self.ex.register_consumer("outbound", InboxAdapter(self.outbound_queue))

        self.ex.start()
        self.gate.start()
        self.router.start()
        self.wm.start()

    def tearDown(self):
        self.wm.stop()
        self.router.stop()
        self.gate.stop()
        self.ex.stop()
        self._tmp.cleanup()

    def test_voice_command_send_flow(self):
        """record_command_toggle → (gate 切 command) → STT "send" → /send → outbound。"""
        # 0. 預填 buffer 工作區
        self.wm.get("buffer").append("hello")

        # 1. 發送 record_command_toggle（開始錄音，同時把 gate 切到 command 模式）
        #    CommandRouter 正規化字串 → record_command_toggle → emit gate_ctl{mode:command}
        self.cmd_producer_queue.put("RECORD_COMMAND_TOGGLE")

        # 等待 gate_ctl 生效（gate 已切到 command 模式）；
        # 判斷方式：等 SttGate.mode 變成 "command"
        self.assertTrue(
            wait_until(lambda: self.gate.mode == "command"),
            "SttGate 未在超時內切換到 command 模式",
        )

        # 2. 注入 STT 辨識文字 "send"
        self.stt_text_queue.put("send")

        # 3. SttGate(command) → commands {"cmd":"voice","args":["send"]}
        #    → CommandRouter._handle_voice → 關鍵字 "send" → /send
        #    → outbound payload
        self.assertTrue(
            wait_until(lambda: not self.outbound_queue.empty()),
            "outbound 超時未收到 payload",
        )

        payload = self.outbound_queue.get_nowait()
        self.assertEqual(payload["Content"], "hello")
        self.assertIn("Title", payload)


# ── Test 3: normal 模式全鏈 ─────────────────────────────────────────────────


class TestNormalModeFlow(unittest.TestCase):
    """Test 3: stt_text "今天天氣" 在 normal 模式 → raw_text
    → WorkspaceManager → buffer.count() == 1。
    """

    def setUp(self):
        # 外設裸 queue
        self.stt_text_queue = queue.Queue()

        # 模組
        self.wm = WorkspaceManager()
        self.gate = SttGate()

        # Exchange 配線
        self.ex = Exchange(idle_sleep=0.001)

        # 生產者：STT → stt_text
        self.ex.register_producer(
            "stt",
            OutboxAdapter(self.stt_text_queue, topic="stt_text", source="stt"),
        )

        # SttGate：消費 stt_text + gate_ctl
        self.gate.attach(self.ex)

        # WorkspaceManager：消費 raw_text
        self.wm.attach(self.ex)

        self.ex.start()
        self.gate.start()
        self.wm.start()

    def tearDown(self):
        self.wm.stop()
        self.gate.stop()
        self.ex.stop()

    def test_normal_mode_text_reaches_workspace(self):
        """stt_text 在 normal 模式下流進 buffer 工作區。"""
        # SttGate 預設 mode="normal"
        self.stt_text_queue.put("今天天氣")
        self.assertTrue(
            wait_until(lambda: self.wm.get("buffer").count() == 1),
            "buffer 超時未收到文字",
        )
        self.assertEqual(self.wm.get("buffer").lines(), ["今天天氣"])


if __name__ == "__main__":
    unittest.main()
