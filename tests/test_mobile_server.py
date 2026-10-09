"""手機伺服器（mobile_server.create_app）的 TestClient 回歸基準。

不需手機、不載 Whisper、不連 LLM：元件以 tests/_mobile_helpers.py 的替身注入，
所有落盤路徑指向 tmp。7a 的 8 類案例事件型別序列維持；階段 7b 起手機走 Data Tunnel，
文案與工作區語意以桌面為準（D9），改動處於各案註明「7b：」。
"""

import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_HAS_DEPS = all(importlib.util.find_spec(m) for m in ("fastapi", "httpx"))

if _HAS_DEPS:
    from mobile_server import create_app
    from tests._helpers import wait_until
    from tests._mobile_helpers import (
        STATIC_DIR,
        TestClient,
        WebSocketDisconnect,
        is_type,
        make_state,
        recv,
        recv_until,
    )


class _MobileBase(unittest.TestCase):
    """共用 setUp／連線 helper；本身沒有測試。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.state = make_state(self._tmp.name)
        self.app = create_app(self.state, static_dir=STATIC_DIR)

    def tearDown(self):
        self._tmp.cleanup()

    @contextlib.contextmanager
    def _client(self):
        """TestClient＋ExitStack；WS 連線必須在 TestClient 關閉（lifespan 結束）前先關。"""
        with TestClient(self.app) as c, contextlib.ExitStack() as stack:
            self._stack = stack
            yield c

    def _connect(self, c, drain=True):
        """連線；drain 時吃掉初始的 status 待機與 sessions。"""
        sock = self._stack.enter_context(c.websocket_connect("/ws"))
        if drain:
            recv_until(sock, is_type("sessions"))
        return sock

    def _wait_buffer(self, n):
        buffer = self.state.wm.get("buffer")
        self.assertTrue(wait_until(lambda: buffer.count() == n))


@unittest.skipUnless(_HAS_DEPS, "fastapi／httpx 未安裝")
class MobileServerTest(_MobileBase):
    # 1
    def test_connect_pushes_status_and_sessions(self):
        with TestClient(self.app) as c, c.websocket_connect("/ws") as ws:
            first = recv(ws)
            self.assertEqual(first, {"type": "status", "text": "待機"})
            sessions = recv(ws)
            self.assertEqual(sessions["type"], "sessions")
            self.assertTrue(any(s.startswith("default") for s in sessions["list"]), sessions)
            self.assertEqual(sessions["current"], "default")

    # 2
    def test_text_echoes_user_message(self):
        with self._client() as c:
            ws = self._connect(c)
            ws.send_json({"type": "text", "content": "哈囉"})
            msg = recv(ws)
            self.assertEqual(msg, {"type": "message", "role": "user", "text": "哈囉"})
            self._wait_buffer(1)

    # 3
    def test_list_command(self):
        with self._client() as c:
            ws = self._connect(c)
            ws.send_json({"type": "cmd", "cmd": "/list", "args": []})
            msg = recv(ws)
            self.assertEqual((msg["type"], msg["role"]), ("message", "system"))
            self.assertIn("對話列表", msg["text"])
            # 7b：尾行文案同桌面（D9；原「當前 session：」）
            self.assertIn("當前使用session：default", msg["text"])

    # 4
    def test_quick_send_round_trip(self):
        with self._client() as c:
            ws = self._connect(c)
            ws.send_json({"type": "text", "content": "問題"})
            recv_until(ws, is_type("message", role="user"))
            self._wait_buffer(1)
            ws.send_json({"type": "signal", "signal": "QUICK_SEND"})
            _, seen = recv_until(ws, lambda m: m.get("type") == "status" and m["text"] == "待機")
            kinds = [(m["type"], m.get("role") or m.get("text")) for m in seen]
            self.assertEqual(kinds, [
                ("message", "sending"),
                ("status", "傳送中"),
                ("message", "assistant"),
                ("tts", "回覆:問題"),
                ("status", "待機"),
            ])
            self.assertEqual(seen[0]["text"], "[傳送內容] 問題")
            self.assertEqual(seen[2]["text"], "回覆:問題")
            self.assertEqual(seen[3]["priority"], "medium")
            history = self.state.session_manager.get_history()
            self.assertIn("問題", history)
            self.assertIn("回覆:問題", history)

    # 5
    def test_stt_output_becomes_voice_message(self):
        with self._client() as c:
            ws = self._connect(c)
            self.state.parts.queues["stt_out"].put("語音文字")
            msg = recv(ws)
            self.assertEqual(msg, {"type": "message", "role": "voice", "text": "語音文字"})
            self._wait_buffer(1)
            # 7b：STT 文字只進當前工作區（buffer），不再同時寫入 stt 工作區（同桌面）
            self.assertTrue(self.state.wm.get("stt").is_empty())

    # 6
    def test_clipboard_copy_and_paste(self):
        with self._client() as c:
            ws = self._connect(c)
            ws.send_json({"type": "text", "content": "要複製"})
            recv_until(ws, is_type("message", role="user"))
            self._wait_buffer(1)

            ws.send_json({"type": "cmd", "cmd": "/copy", "args": []})
            msg, _ = recv_until(ws, is_type("clipboard_write"))
            self.assertEqual(msg["text"], "要複製")

            ws.send_json({"type": "cmd", "cmd": "/paste", "args": []})
            recv_until(ws, is_type("clipboard_read"))

            ws.send_json({"type": "clipboard_data", "text": "甲\n\n乙"})
            msg, _ = recv_until(ws, is_type("message", role="system"))
            self.assertIn("已從剪貼簿貼上 2 筆", msg["text"])
            self._wait_buffer(3)

    # 7（B6）
    def test_new_connection_replaces_old(self):
        with self._client() as c:
            ws1 = self._connect(c)
            ws2 = self._connect(c)
            # 舊連線被伺服器關閉
            with self.assertRaises(WebSocketDisconnect):
                recv_until(ws1, lambda m: False)
            self.assertIsNotNone(self.state.current_ws)
            # 事件只送到新連線
            ws2.send_json({"type": "cmd", "cmd": "/list", "args": []})
            msg = recv(ws2)
            self.assertIn("對話列表", msg["text"])

    def test_events_wait_until_a_client_connects(self):
        # 無人連線時 pusher 不消費 queue（與舊版「無連線即無 pusher」相同）
        with self._client() as c:
            self.state.parts.queues["stt_out"].put("離線時的語音")
            ws = self._connect(c, drain=False)
            msg, _ = recv_until(ws, is_type("message", role="voice"))
            self.assertEqual(msg["text"], "離線時的語音")

    def test_disconnect_clears_current_ws(self):
        with self._client() as c:
            with c.websocket_connect("/ws") as ws:
                recv_until(ws, is_type("sessions"))
            self.assertTrue(wait_until(lambda: self.state.current_ws is None))

    # 8
    def test_root_serves_index(self):
        with self._client() as c:
            resp = c.get("/")
            self.assertEqual(resp.status_code, 200)
            self.assertIn("text/html", resp.headers["content-type"])


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
            # 不復位狀態（同桌面）：接著送 /show，下一則即其回覆，中間沒有 status
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


@unittest.skipUnless(_HAS_DEPS, "fastapi／httpx 未安裝")
class MobilePusherRetryTest(unittest.TestCase):
    """B6：send_json 失敗的事件保留重送，不丟棄。"""

    def test_failed_send_is_kept_for_retry(self):
        import asyncio

        from mobile.outputs import _flush_ui_events

        class FlakyWS:
            def __init__(self):
                self.sent = []
                self.fail = True

            async def send_json(self, data):
                if self.fail:
                    self.fail = False
                    raise RuntimeError("boom")
                self.sent.append(data)

        with tempfile.TemporaryDirectory() as tmp:
            state = make_state(tmp)
            state.ui_event_queue.put({"type": "status", "text": "一"})
            state.ui_event_queue.put({"type": "status", "text": "二"})
            ws = FlakyWS()
            asyncio.run(_flush_ui_events(state, ws))
            self.assertEqual(ws.sent, [])
            self.assertEqual(list(state.pending_events), [{"type": "status", "text": "一"}])
            asyncio.run(_flush_ui_events(state, ws))
            self.assertEqual([e["text"] for e in ws.sent], ["一", "二"])
            self.assertEqual(len(state.pending_events), 0)


class MobileImportSideEffectTest(unittest.TestCase):
    """匯入 mobile.state 不得載入 config、設日誌或建立元件。"""

    def test_state_module_has_no_component_globals(self):
        import mobile.state as ms

        for name in ("_cfg", "_session_manager", "_voice_to_text", "_ui_event_queue"):
            self.assertFalse(hasattr(ms, name), name)
        self.assertTrue(callable(ms.build_mobile_state))


if __name__ == "__main__":
    unittest.main()
