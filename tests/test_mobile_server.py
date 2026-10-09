"""手機伺服器（mobile_server.create_app）的 TestClient 回歸基準。

不需手機、不載 Whisper、不連 LLM：元件以 tests/_mobile_helpers.py 的替身注入，
所有落盤路徑指向 tmp。7a 的 8 類案例事件型別序列維持；階段 7b 起手機走 Data Tunnel，
文案與工作區語意以桌面為準（D9），改動處於各案註明「7b：」。
與桌面對齊的案例見 tests/test_mobile_alignment.py；共用基底 `MobileBase` 在 tests/_mobile_helpers.py。
"""

import importlib.util
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

_HAS_DEPS = all(importlib.util.find_spec(m) for m in ("fastapi", "httpx"))

if _HAS_DEPS:
    from tests._helpers import wait_until
    from tests._mobile_helpers import (
        MobileBase as _MobileBase,
        TestClient,
        WebSocketDisconnect,
        is_type,
        make_state,
        recv,
        recv_until,
    )
else:
    _MobileBase = unittest.TestCase


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
