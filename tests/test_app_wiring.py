"""接線整合測試：用裸 queue + native 模組驗證 wire() 的所有代表性路由。

不啟動任何真實硬體模組（Recorder / VoiceToText / TuiRenderer 等）——
這些模組的 queue 僅作為裸 queue 存在，供測試直接讀寫。

執行：python3 -m unittest tests.test_app_wiring
"""

import configparser
import os
import queue
import sys
import tempfile
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import wire, _dict_to_ui_event
from core.exchange import Exchange
from core.endpoint import Inbox
from modules.workspace_manager import WorkspaceManager
from modules.stt_gate import SttGate
from modules.command_router import CommandRouter
from modules.chat_flow import ChatFlow
from modules.cli_text_bridge import CliTextBridge
from session_manager import SessionManager

# UiEvent 延遲匯入（tui_renderer 依賴 rich，測試環境可能未安裝）；
# 測試中以屬性驗證替代 isinstance 檢查。
_UiEvent = None


def _get_ui_event_class():
    global _UiEvent
    if _UiEvent is None:
        try:
            from tui_renderer import UiEvent
            _UiEvent = UiEvent
        except ImportError:
            pass
    return _UiEvent


def wait_until(predicate, timeout=3.0):
    """輪詢直到條件成立或逾時，回傳 bool。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def _make_config(tmp_dir: str) -> configparser.ConfigParser:
    """建立一個最小可用的 ConfigParser（不需要實體 config.ini）。"""
    config = configparser.ConfigParser()
    config["WORKSPACE"] = {
        "sessions_file": os.path.join(tmp_dir, ".sessions.json"),
        "deleted_sessions_dir": os.path.join(tmp_dir, "deleted"),
        "export_file": os.path.join(tmp_dir, "export.json"),
        "log_file": os.path.join(tmp_dir, "system.log"),
    }
    config["SLM"] = {
        "summary_threshold": "20",
        "enabled": "false",  # 測試時停用摘要（短回覆直接走 TTS）
    }
    config["LOGGING"] = {"level": "WARNING"}
    return config


class TestAppWiring(unittest.TestCase):
    """整合測試：wire() 接線後的端對端路由驗證。"""

    def setUp(self):
        # ── 暫存目錄（隔離各測試） ─────────────────────────────────────
        self._tmpdir = tempfile.mkdtemp()
        config = _make_config(self._tmpdir)

        # ── SessionManager（用暫存路徑，不汙染主目錄） ─────────────────
        self.session_manager = SessionManager(config)
        if not self.session_manager.current_title:
            if not self.session_manager.switch_session("default"):
                self.session_manager.new_session("default")

        # ── 裸 queue（代替真實硬體模組的 I/O） ──────────────────────
        self.key_signal        = queue.Queue()
        self.cli_cmd           = queue.Queue()
        self.cli_text          = queue.Queue()
        self.recorder_cmd      = queue.Queue()
        self.audio_out         = queue.Queue()
        self.audio_in          = queue.Queue()
        self.recorder_event    = queue.Queue()
        self.stt_out           = queue.Queue()
        self.http_send         = queue.Queue()
        self.http_recv         = queue.Queue()
        self.summary_in        = queue.Queue()
        self.summary_out_q     = queue.Queue()
        self.tts_input         = queue.Queue()
        self.tts_cmd           = queue.Queue()
        self.ui_event_q        = queue.Queue()

        # ── Export dir ────────────────────────────────────────────────
        export_dir = self._tmpdir

        # ── Native modules ────────────────────────────────────────────
        self.wm = WorkspaceManager()
        self.stt_gate = SttGate()
        self.command_router = CommandRouter(self.wm, self.session_manager, export_dir)
        self.chat_flow = ChatFlow(
            self.session_manager,
            summary_threshold=20,
            slm_enabled=False,
        )
        self.cli_bridge = CliTextBridge()

        # ── Exchange ──────────────────────────────────────────────────
        self.exchange = Exchange(idle_sleep=0.001)

        # ── wire() 呼叫 ───────────────────────────────────────────────
        self.app_ctl = wire(
            self.exchange,
            native_modules={
                "wm": self.wm,
                "stt_gate": self.stt_gate,
                "command_router": self.command_router,
                "chat_flow": self.chat_flow,
                "cli_text_bridge": self.cli_bridge,
            },
            legacy_queues={
                "key_signal":        self.key_signal,
                "cli_cmd":           self.cli_cmd,
                "cli_text":          self.cli_text,
                "recorder_cmd":      self.recorder_cmd,
                "audio_out":         self.audio_out,
                "audio_in":          self.audio_in,
                "recorder_event":    self.recorder_event,
                "stt_out":           self.stt_out,
                "http_send":         self.http_send,
                "http_recv":         self.http_recv,
                "summary_in":        self.summary_in,
                "summary_out_q":     self.summary_out_q,
                "tts_input":         self.tts_input,
                "tts_cmd":           self.tts_cmd,
                "ui_event_q":        self.ui_event_q,
            },
        )

        # ── 啟動 exchange 與 native modules ──────────────────────────
        self.exchange.start()
        self.wm.start()
        self.stt_gate.start()
        self.command_router.start()
        self.chat_flow.start()
        self.cli_bridge.start()

    def tearDown(self):
        # 停止順序：native → exchange
        for m in (self.wm, self.stt_gate, self.command_router, self.chat_flow, self.cli_bridge):
            m.stop()
        self.exchange.stop()
        # 清理暫存目錄
        import shutil
        shutil.rmtree(self._tmpdir, ignore_errors=True)

    # ── 測試 1：key_signal "RECORD_TOGGLE" → recorder_cmd 收到 "START" ─

    def test_1_record_toggle_routes_to_recorder_cmd(self):
        """RECORD_TOGGLE 進 key_signal → recorder_cmd 應收到 "START"。"""
        self.key_signal.put("RECORD_TOGGLE")
        ok = wait_until(lambda: not self.recorder_cmd.empty())
        self.assertTrue(ok, "recorder_cmd 逾時未收到任何指令")
        cmd = self.recorder_cmd.get_nowait()
        self.assertEqual(cmd, "START")

    # ── 測試 2：cli_text "哈囉" → ui_event_q 收 UiEvent + wm buffer 有文字 ─

    def test_2_cli_text_produces_ui_event_and_wm_buffer(self):
        """cli_text "哈囉" → ui_event_q 有 UiEvent(message, user) 且 wm.buffer 含此文字。"""
        self.cli_text.put("哈囉")

        # ui_event_q 應收到 UiEvent 物件（由 InboxAdapter transform 轉換）
        ok_ui = wait_until(lambda: not self.ui_event_q.empty())
        self.assertTrue(ok_ui, "ui_event_q 逾時未收到 UiEvent")
        evt = self.ui_event_q.get_nowait()
        # 驗證物件有 UiEvent 應有的屬性（以屬性檢查取代 isinstance，
        # 使測試在 rich 未安裝的環境中亦可執行）
        self.assertTrue(hasattr(evt, "event_type"), "evt 缺少 event_type 屬性")
        self.assertTrue(hasattr(evt, "data"), "evt 缺少 data 屬性")
        self.assertEqual(evt.event_type, "message")
        self.assertIsInstance(evt.data, dict)
        self.assertEqual(evt.data.get("role"), "user")
        self.assertEqual(evt.data.get("text"), "哈囉")

        # WorkspaceManager buffer 也應含此文字
        ok_wm = wait_until(lambda: self.wm.get("buffer").count() >= 1)
        self.assertTrue(ok_wm, "wm.buffer 逾時未寫入文字")
        self.assertIn("哈囉", self.wm.get("buffer").lines())

    # ── 測試 3：stt_out "語音文字" → wm buffer 收到 + ui_event voice ─────

    def test_3_stt_text_routes_to_wm_buffer_and_ui_voice(self):
        """stt_out "語音文字" (normal mode) → wm buffer 有文字且 ui_event_q 有 voice UiEvent。"""
        self.stt_out.put("語音文字")

        # WorkspaceManager buffer
        ok_wm = wait_until(lambda: self.wm.get("buffer").count() >= 1)
        self.assertTrue(ok_wm, "wm.buffer 逾時未收到 stt 文字")
        self.assertIn("語音文字", self.wm.get("buffer").lines())

        # ui_event_q：voice role（SttGate 在 normal 模式下先 emit ui_event 再 emit raw_text）
        ok_ui = wait_until(lambda: not self.ui_event_q.empty())
        self.assertTrue(ok_ui, "ui_event_q 逾時未收到 voice UiEvent")
        evt = self.ui_event_q.get_nowait()
        self.assertTrue(hasattr(evt, "event_type"), "evt 缺少 event_type 屬性")
        self.assertEqual(evt.event_type, "message")
        self.assertEqual(evt.data.get("role"), "voice")
        self.assertEqual(evt.data.get("text"), "語音文字")

    # ── 測試 4：ChatReply 進 http_recv → tts_input 收到 {"text":...,"priority":"medium"} ─

    def test_4_chat_reply_routes_to_tts_input(self):
        """ChatReply dict 進 http_recv → tts_input 應收到 {"text":...,"priority":"medium"}。"""
        reply = {
            "type": "ChatReply",
            "Content": {"full_response": "你好，有什麼需要幫忙的嗎？"},
        }
        self.http_recv.put(reply)

        ok = wait_until(lambda: not self.tts_input.empty())
        self.assertTrue(ok, "tts_input 逾時未收到 TTS 項目")
        item = self.tts_input.get_nowait()
        self.assertIsInstance(item, dict)
        self.assertIn("text", item)
        self.assertEqual(item["text"], "你好，有什麼需要幫忙的嗎？")
        self.assertEqual(item.get("priority"), "medium")

    # ── 測試 5：{"cmd":"/exit"} 進 cli_cmd → app_ctl 收到 "EXIT" ─────────

    def test_5_exit_cmd_routes_to_app_ctl(self):
        """cli_cmd {"cmd":"/exit"} → app_ctl Inbox 應收到 "EXIT"。"""
        self.cli_cmd.put({"cmd": "/exit"})
        ok = wait_until(lambda: not self.app_ctl.empty())
        self.assertTrue(ok, "app_ctl 逾時未收到 EXIT")
        payload = self.app_ctl.get_nowait()
        self.assertEqual(payload, "EXIT")

    # ── 測試 6：_dict_to_ui_event 各種形狀的轉換 ─────────────────────────

    def test_6_dict_to_ui_event_transforms(self):
        """_dict_to_ui_event 對三種 dict 形狀均回傳具有正確屬性的 UiEvent。"""
        # status 形狀
        ev = _dict_to_ui_event({"type": "status", "text": "待機"})
        self.assertTrue(hasattr(ev, "event_type"))
        self.assertEqual(ev.event_type, "status")
        self.assertEqual(ev.data, "待機")

        # message 形狀
        ev = _dict_to_ui_event({"type": "message", "role": "user", "text": "hi"})
        self.assertTrue(hasattr(ev, "event_type"))
        self.assertEqual(ev.event_type, "message")
        self.assertEqual(ev.data["role"], "user")
        self.assertEqual(ev.data["text"], "hi")

        # clear 形狀
        ev = _dict_to_ui_event({"type": "clear"})
        self.assertTrue(hasattr(ev, "event_type"))
        self.assertEqual(ev.event_type, "clear")
        self.assertIsNone(ev.data)

        # 未知 type → 安全 fallback（message + system role）
        ev = _dict_to_ui_event({"type": "unknown_xyz", "data": 123})
        self.assertTrue(hasattr(ev, "event_type"))
        self.assertEqual(ev.event_type, "message")
        self.assertEqual(ev.data["role"], "system")


if __name__ == "__main__":
    unittest.main()
