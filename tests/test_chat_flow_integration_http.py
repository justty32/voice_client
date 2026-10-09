"""聊天流整合測試：全鏈在真實 Exchange 上驗證——HTTP 往返。

執行：python3 -m unittest tests.test_chat_flow_integration_http
"""

import os
import queue
import sys
import tempfile
import threading
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.adapter import InboxAdapter, OutboxAdapter
from core.exchange import Exchange
from modules.chat_flow import ChatFlow
from modules.command_router import CommandRouter
from modules.workspace_manager import WorkspaceManager
from tests._helpers import make_sm, wait_until


# ── Test 1: HTTP 往返 ────────────────────────────────────────────────────────


class FakeLegacyHttp(threading.Thread):
    """形態同 llm.http_client.HttpClient：裸 send_queue→recv_queue＋自有工作執行緒。

    收到 payload 後，固定回覆 {"type":"ChatReply","Content":{"full_response":"好的"}}。
    """

    def __init__(self, send_queue: queue.Queue, recv_queue: queue.Queue):
        super().__init__(daemon=True, name="FakeLegacyHttp")
        self._send_queue = send_queue
        self._recv_queue = recv_queue
        self._running = False

    def run(self):
        self._running = True
        while self._running:
            try:
                _payload = self._send_queue.get(timeout=0.05)
            except queue.Empty:
                continue
            self._recv_queue.put({
                "type": "ChatReply",
                "Content": {"full_response": "好的"},
            })

    def stop(self):
        self._running = False


class TestHttpRoundTrip(unittest.TestCase):
    """Test 1: /send → outbound → FakeLegacyHttp → inbound → ChatFlow → tts medium。

    前置條件：buffer 工作區預先放一筆 "hi"。
    斷言：
    - tts 佇列收到 {"text":"好的","priority":"medium"}（短回覆 < threshold）
    - session 歷史含 user "hi" 與 assistant "好的"
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()

        # 外設裸 queue
        self.cmd_queue = queue.Queue()    # commands 入口
        self.send_queue = queue.Queue()   # outbound payload → FakeLegacyHttp
        self.recv_queue = queue.Queue()   # FakeLegacyHttp 回應 → inbound
        self.tts_queue = queue.Queue()    # 收集 tts 訊息

        # 模組
        self.wm = WorkspaceManager()
        self.sm = make_sm(self._tmp.name)
        self.router = CommandRouter(
            workspace_manager=self.wm,
            session_manager=self.sm,
            export_dir=self._tmp.name,
        )
        self.chat_flow = ChatFlow(
            session_manager=self.sm,
            summary_threshold=20,
            slm_enabled=True,
        )

        # Exchange 配線
        self.ex = Exchange(idle_sleep=0.001)

        # 生產者 1：指令佇列 → commands
        self.ex.register_producer(
            "cmd_producer",
            OutboxAdapter(self.cmd_queue, topic="commands", source="test"),
        )

        # 生產者 2：recv_queue（FakeLegacyHttp 回應）→ inbound
        self.ex.register_producer(
            "http_recv",
            OutboxAdapter(self.recv_queue, topic="inbound", source="http"),
        )

        # CommandRouter：消費 commands，生產 outbound / ui_event / chat_ctl / …
        self.router.attach(self.ex)

        # WorkspaceManager：消費 raw_text
        self.wm.attach(self.ex)

        # ChatFlow：消費 inbound / summary_out / chat_ctl，生產 tts / ui_event / summary_req
        self.chat_flow.attach(self.ex)

        # 消費者 1：outbound → send_queue（FakeLegacyHttp 輸入）
        self.ex.register_consumer("outbound", InboxAdapter(self.send_queue))

        # 消費者 2：tts → 裸 queue
        self.ex.register_consumer("tts", InboxAdapter(self.tts_queue))

        # FakeLegacyHttp
        self.fake_http = FakeLegacyHttp(self.send_queue, self.recv_queue)

        self.ex.start()
        self.router.start()
        self.wm.start()
        self.chat_flow.start()
        self.fake_http.start()

    def tearDown(self):
        self.chat_flow.stop()
        self.router.stop()
        self.wm.stop()
        self.fake_http.stop()
        self.ex.stop()
        self._tmp.cleanup()

    def test_http_roundtrip_tts_and_history(self):
        """全鏈：/send → outbound → FakeLegacyHttp → inbound → tts medium；歷史含 user + assistant。"""
        # 預填 buffer 工作區
        self.wm.get("buffer").append("hi")

        # 發送 /send 指令
        self.cmd_queue.put({"cmd": "/send", "args": []})

        # 等待 tts 收到回覆
        self.assertTrue(
            wait_until(lambda: not self.tts_queue.empty()),
            "tts 佇列超時未收到訊息",
        )

        tts_msg = self.tts_queue.get_nowait()
        self.assertEqual(tts_msg["text"], "好的")
        self.assertEqual(tts_msg["priority"], "medium")

        # 驗證 session 歷史含 user "hi" 與 assistant "好的"
        def history_complete():
            session = self.sm.get_current_session()
            if session is None:
                return False
            history = session.get("history", [])
            has_user = any(h[0] == "user" and h[1] == "hi" for h in history)
            has_assistant = any(h[0] == "assistant" and h[1] == "好的" for h in history)
            return has_user and has_assistant

        self.assertTrue(
            wait_until(history_complete),
            "session 歷史未在超時內包含 user 'hi' 與 assistant '好的'",
        )

        session = self.sm.get_current_session()
        history = session["history"]
        user_entries = [h for h in history if h[0] == "user"]
        assistant_entries = [h for h in history if h[0] == "assistant"]
        self.assertTrue(any(h[1] == "hi" for h in user_entries))
        self.assertTrue(any(h[1] == "好的" for h in assistant_entries))


if __name__ == "__main__":
    unittest.main()
