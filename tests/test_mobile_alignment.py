"""手機伺服器與桌面對齊（階段 7b，D9、D10）的 TestClient 測試。

自 tests/test_mobile_server.py 拆出；共用基底 `MobileBase` 在 tests/_mobile_helpers.py。
"""

import importlib.util
import io
import json
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_HAS_DEPS = all(importlib.util.find_spec(m) for m in ("fastapi", "httpx"))

if _HAS_DEPS:
    from tests._helpers import wait_until
    from tests._mobile_helpers import (
        MobileBase as _MobileBase,
        is_type,
        recv,
        recv_until,
    )
else:
    _MobileBase = unittest.TestCase


@unittest.skipUnless(_HAS_DEPS, "fastapi／httpx 未安裝")
class MobileDesktopAlignmentTest(_MobileBase):
    """階段 7b【改行為】：手機走 Data Tunnel 後與桌面對齊的各項（D9、D10）。"""

    def _cmd(self, ws, cmd, args=()):
        ws.send_json({"type": "cmd", "cmd": cmd, "args": list(args)})

    def _system(self, ws, needle):
        msg, seen = recv_until(
            ws, lambda m: m.get("type") == "message" and m.get("role") == "system"
            and needle in m["text"])
        return msg, seen

    # 1：工作區集合 buffer/stt；chat 唯讀
    def test_ws_chat_is_read_only(self):
        with self._client() as c:
            ws = self._connect(c)
            self._cmd(ws, "/ws")
            msg, _ = self._system(ws, "工作區列表")
            for name in ("buffer (當前)", "stt", "chat"):
                self.assertIn(name, msg["text"])
            self._cmd(ws, "/ws", ["chat"])
            self._system(ws, "chat 為唯讀檢視")
            self.assertEqual(self.state.wm.current, "buffer")
            self._cmd(ws, "/ws", ["stt"])
            self._system(ws, "已切換當前工作區至: stt")
            self.assertEqual(self.state.wm.current, "stt")

    # 2：STT 文字只進當前工作區
    def test_stt_text_goes_to_current_workspace_only(self):
        with self._client() as c:
            ws = self._connect(c)
            self._cmd(ws, "/ws", ["stt"])
            self._system(ws, "已切換當前工作區至: stt")
            self.state.parts.queues["stt_out"].put("切到 stt 後的語音")
            recv_until(ws, is_type("message", role="voice"))
            stt = self.state.wm.get("stt")
            self.assertTrue(wait_until(lambda: stt.count() == 1))
            self.assertEqual(stt.lines(), ["切到 stt 後的語音"])
            self.assertTrue(self.state.wm.get("buffer").is_empty())

    # 3：/switch 無參數且無 default → 自動建立
    def test_switch_without_default_creates_it(self):
        with self._client() as c:
            ws = self._connect(c)
            self._cmd(ws, "/new", ["甲"])
            self._system(ws, "新建對話: 甲")
            self._cmd(ws, "/delete", ["default"])
            self.assertTrue(wait_until(
                lambda: "default" not in self.state.session_manager.list_sessions()))
            self._cmd(ws, "/switch")
            self._system(ws, "建立並切換至: default")
            self.assertEqual(self.state.session_manager.current_title, "default")

    # 4：/list 尾行（另見 test_list_command）
    def test_list_tail_shows_current_after_new(self):
        with self._client() as c:
            ws = self._connect(c)
            self._cmd(ws, "/new", ["乙"])
            self._system(ws, "新建對話: 乙")
            self._cmd(ws, "/list")
            msg, _ = self._system(ws, "對話列表")
            self.assertTrue(msg["text"].endswith("當前使用session：乙"), msg["text"])

    # 5：Error 回覆 role 為 system、播報錯誤，不推「待機」
    def test_error_reply_is_system_role(self):
        with self._client() as c:
            ws = self._connect(c)
            self.state.parts.queues["http_recv"].put({"type": "Error", "message": "爆了"})
            msg, _ = recv_until(ws, is_type("message"))
            self.assertEqual(msg, {"type": "message", "role": "system", "text": "[錯誤] 爆了"})
            tts = recv(ws)
            self.assertEqual(tts, {"type": "tts", "text": "發生錯誤：爆了", "priority": "high"})
            # 錯誤後狀態列回待機（同桌面）
            self.assertEqual(recv(ws), {"type": "status", "text": "待機"})
            self._cmd(ws, "/show")
            nxt = recv(ws)
            self.assertEqual((nxt["type"], nxt["role"]), ("message", "system"))
            self.assertIn("工作區是空的", nxt["text"])

    # 6：/import 無參數回錯誤（不再讀 _buffer_temp.json）
    def test_import_without_args_is_error(self):
        with self._client() as c:
            ws = self._connect(c)
            self._cmd(ws, "/import")
            self._system(ws, "[錯誤] 請指定匯入檔名。")

    # D10：停機時 buffer 非空 → 匯出 _buffer_temp.json（落在 tmp 的 export 目錄）
    def test_shutdown_autosaves_nonempty_buffer(self):
        path = os.path.join(self.state.export_dir, "_buffer_temp.json")
        with self._client() as c:
            ws = self._connect(c)
            ws.send_json({"type": "text", "content": "停機前"})
            recv_until(ws, is_type("message", role="user"))
            self._wait_buffer(1)
            self.assertFalse(os.path.exists(path))
        self.assertTrue(path.startswith(self._tmp.name))
        with open(path, encoding="utf-8") as f:
            self.assertEqual(json.load(f), [["停機前"]])

    def test_shutdown_skips_autosave_when_buffer_empty(self):
        with self._client():
            pass
        self.assertFalse(os.path.exists(os.path.join(self.state.export_dir, "_buffer_temp.json")))

    # /paste 在邊緣攔截：只推 clipboard_read，不產生「[錯誤]」
    def test_paste_does_not_emit_error(self):
        with self._client() as c:
            ws = self._connect(c)
            self._cmd(ws, "/paste")
            self.assertEqual(recv(ws), {"type": "clipboard_read"})
            self._cmd(ws, "/show")
            _, seen = self._system(ws, "工作區是空的")
            self.assertFalse(any("[錯誤]" in m.get("text", "") for m in seen), seen)

    def test_copy_goes_through_command_router(self):
        with self._client() as c:
            ws = self._connect(c)
            self._cmd(ws, "/copy")
            self._system(ws, "[buffer 工作區是空的，沒有可複製的內容]")
            ws.send_json({"type": "text", "content": "一句"})
            recv_until(ws, is_type("message", role="user"))
            self._wait_buffer(1)
            self._cmd(ws, "/copy")
            _, seen = self._system(ws, "已複製 buffer 工作區 1 筆到剪貼簿")
            self.assertIn({"type": "clipboard_write", "text": "一句"}, seen)

    def test_help_is_desktop_text(self):
        with self._client() as c:
            ws = self._connect(c)
            self._cmd(ws, "/help")
            msg, _ = self._system(ws, "/new [title]")
            self.assertIn("/to_top [i]", msg["text"])

    def test_exit_is_rejected_at_edge(self):
        with self._client() as c:
            ws = self._connect(c)
            self._cmd(ws, "/exit")
            self._system(ws, "未知指令: /exit")
            self.assertTrue(self.state.parts.app_ctl.empty())

    def test_session_commands_push_sessions(self):
        with self._client() as c:
            ws = self._connect(c)
            self._cmd(ws, "/new", ["丙"])
            msg, _ = recv_until(ws, lambda m: m.get("type") == "sessions" and m["current"] == "丙")
            self.assertIn("丙 (當前)", msg["list"])

    def test_force_stop_signal_stops_browser_tts(self):
        with self._client() as c:
            ws = self._connect(c)
            ws.send_json({"type": "signal", "signal": "FORCE_STOP_TTS"})
            _, seen = recv_until(ws, is_type("status", text="待機"))
            self.assertEqual(seen, [{"type": "tts_control", "action": "stop"},
                                    {"type": "status", "text": "待機"}])

    def test_audio_goes_through_recorder_event_and_audio_topic(self):
        wav = io.BytesIO(b"RIFF")
        with mock.patch("mobile.inputs._to_wav", return_value=(wav, None)):
            with self._client() as c:
                ws = self._connect(c)
                ws.send_bytes(b"webm")
                recv_until(ws, is_type("status", text="處理中"))
                audio_in = self.state.parts.queues["audio_in"]
                self.assertTrue(wait_until(lambda: not audio_in.empty()))
                self.assertIs(audio_in.get_nowait(), wav)
                # VoiceToText 處理完回 stt_done → 待機（階段 4c）
                self.state.parts.queues["stt_event"].put({"event": "stt_done"})
                recv_until(ws, is_type("status", text="待機"))

    def test_audio_conversion_failure_reports_recorder_error(self):
        with mock.patch("mobile.inputs._to_wav", return_value=(None, "解碼失敗")):
            with self._client() as c:
                ws = self._connect(c)
                ws.send_bytes(b"bad")
                msg, _ = self._system(ws, "[錄音錯誤] 解碼失敗")
                recv_until(ws, is_type("status", text="待機"))


if __name__ == "__main__":
    unittest.main()
