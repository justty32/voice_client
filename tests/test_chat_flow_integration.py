"""聊天流整合測試：全鏈在真實 Exchange 上驗證。

全鏈使用真模組（ChatFlow、CommandRouter、WorkspaceManager）與假外設
（裸 queue.Queue 包裹於 OutboxAdapter / InboxAdapter），
無硬體依賴、無網路依賴。

執行：python3 -m unittest tests.test_chat_flow_integration -v
"""

import configparser
import os
import queue
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.adapter import InboxAdapter, OutboxAdapter
from core.exchange import Exchange
from modules.chat_flow import ChatFlow
from modules.command_router import CommandRouter
from modules.workspace_manager import WorkspaceManager
from session_manager import SessionManager


# ── 共用工具 ────────────────────────────────────────────────────────────────


def wait_until(predicate, timeout=3.0):
    """輪詢直到謂詞成立或逾時；回傳 True/False。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def make_sm(tmp: str) -> SessionManager:
    """建立指向 tmp 目錄的 SessionManager，並預建 default session。"""
    cfg = configparser.ConfigParser()
    cfg["WORKSPACE"] = {
        "sessions_file": os.path.join(tmp, "output", ".sessions.json"),
        "deleted_sessions_dir": os.path.join(tmp, "output", "deleted"),
    }
    sm = SessionManager(cfg)
    sm.new_session("default")
    return sm


def drain_queue(q: queue.Queue) -> list:
    """取出佇列中所有現有項目，回傳 list。"""
    items = []
    while True:
        try:
            items.append(q.get_nowait())
        except queue.Empty:
            break
    return items


# ── Test 1: HTTP 往返 ────────────────────────────────────────────────────────


class FakeLegacyHttp(threading.Thread):
    """形態同 http_client.HttpClient：裸 send_queue→recv_queue＋自有工作執行緒。

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


# ── Test 2: 摘要鏈 ──────────────────────────────────────────────────────────


class FakeLegacySummarizer(threading.Thread):
    """形態同 summary_generator.SummaryGenerator：裸 summary_queue→output_queue＋自有執行緒。

    讀取 {"cmd":"summary","text":...} → 輸出 {"type":"summary","text":"摘"}。
    """

    def __init__(self, summary_queue: queue.Queue, output_queue: queue.Queue):
        super().__init__(daemon=True, name="FakeLegacySummarizer")
        self._summary_queue = summary_queue
        self._output_queue = output_queue
        self._running = False

    def run(self):
        self._running = True
        while self._running:
            try:
                task = self._summary_queue.get(timeout=0.05)
            except queue.Empty:
                continue
            # 模擬摘要器：輸出固定摘要文字 "摘"
            self._output_queue.put({"type": "summary", "text": "摘"})

    def stop(self):
        self._running = False


class TestSummaryChain(unittest.TestCase):
    """Test 2: 長回覆 → summary_req → FakeLegacySummarizer → summary_out → tts「回覆摘要：摘」。

    summary_threshold=2 使得任何非空回覆都觸發 summary_req。
    斷言：tts 最終收到 text="回覆摘要：摘", priority="medium"。
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()

        # 外設裸 queue
        self.inbound_queue = queue.Queue()    # 注入 ChatReply → inbound
        self.summary_queue = queue.Queue()    # summary_req → FakeLegacySummarizer 輸入
        self.summary_out_queue = queue.Queue()  # FakeLegacySummarizer 輸出 → summary_out
        self.tts_queue = queue.Queue()        # 收集 tts

        # 模組
        self.sm = make_sm(self._tmp.name)
        # summary_threshold=2：任何回覆長度 >= 2 都走摘要路徑
        self.chat_flow = ChatFlow(
            session_manager=self.sm,
            summary_threshold=2,
            slm_enabled=True,
        )

        # Exchange 配線
        self.ex = Exchange(idle_sleep=0.001)

        # 生產者 1：inbound_queue → inbound
        self.ex.register_producer(
            "inbound_producer",
            OutboxAdapter(self.inbound_queue, topic="inbound", source="test"),
        )

        # 生產者 2：summary_out_queue（摘要器輸出）→ summary_out
        self.ex.register_producer(
            "summary_out_producer",
            OutboxAdapter(self.summary_out_queue, topic="summary_out", source="summarizer"),
        )

        # ChatFlow：消費 inbound / summary_out / chat_ctl
        self.chat_flow.attach(self.ex)

        # 消費者 1：summary_req → summary_queue（FakeLegacySummarizer 輸入）
        self.ex.register_consumer("summary_req", InboxAdapter(self.summary_queue))

        # 消費者 2：tts → 裸 queue
        self.ex.register_consumer("tts", InboxAdapter(self.tts_queue))

        # FakeLegacySummarizer
        self.fake_summarizer = FakeLegacySummarizer(self.summary_queue, self.summary_out_queue)

        self.ex.start()
        self.chat_flow.start()
        self.fake_summarizer.start()

    def tearDown(self):
        self.chat_flow.stop()
        self.fake_summarizer.stop()
        self.ex.stop()
        self._tmp.cleanup()

    def test_summary_chain_tts_receives_summary(self):
        """注入長回覆（>= threshold）→ summary_req → 摘要器 → summary_out → tts「回覆摘要：摘」。"""
        # 注入一個長度 >= threshold=2 的 ChatReply（觸發 summary 路徑）
        self.inbound_queue.put({
            "type": "ChatReply",
            "Content": {"full_response": "回覆"},
        })

        # 等待 tts 收到摘要
        def tts_has_summary():
            items = list(self.tts_queue.queue)
            return any(
                item.get("text") == "回覆摘要：摘" and item.get("priority") == "medium"
                for item in items
            )

        self.assertTrue(
            wait_until(tts_has_summary),
            "tts 佇列超時未收到「回覆摘要：摘」",
        )

        # 從佇列取出並驗證
        found = False
        while not self.tts_queue.empty():
            msg = self.tts_queue.get_nowait()
            if msg.get("text") == "回覆摘要：摘" and msg.get("priority") == "medium":
                found = True
                break
        self.assertTrue(found, "tts 應包含 text='回覆摘要：摘', priority='medium'")


# ── Test 3: 重播鏈 ───────────────────────────────────────────────────────────


class TestPlayLastChain(unittest.TestCase):
    """Test 3: ChatReply → 收到後發 PLAY_LAST_ORIGINAL → tts 重播原文。

    前置步驟：注入短 ChatReply "原文"（收到 tts）→ 排空 tts；
    再發 "PLAY_LAST_ORIGINAL" 到 commands → CommandRouter → chat_ctl → ChatFlow
    → tts 再次收到 {"text":"原文","priority":"medium"}；
    ui_event 中包含「播放最後一次回覆原文」。
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()

        # 外設裸 queue
        self.inbound_queue = queue.Queue()   # 注入 ChatReply → inbound
        self.cmd_queue = queue.Queue()       # commands 入口
        self.tts_queue = queue.Queue()       # 收集 tts
        self.ui_event_queue = queue.Queue()  # 收集 ui_event

        # 模組
        self.wm = WorkspaceManager()
        self.sm = make_sm(self._tmp.name)
        self.router = CommandRouter(
            workspace_manager=self.wm,
            session_manager=self.sm,
            export_dir=self._tmp.name,
        )
        # summary_threshold=100 確保短文字走直接 TTS
        self.chat_flow = ChatFlow(
            session_manager=self.sm,
            summary_threshold=100,
            slm_enabled=True,
        )

        # Exchange 配線
        self.ex = Exchange(idle_sleep=0.001)

        # 生產者 1：inbound_queue → inbound
        self.ex.register_producer(
            "inbound_producer",
            OutboxAdapter(self.inbound_queue, topic="inbound", source="test"),
        )

        # 生產者 2：cmd_queue → commands
        self.ex.register_producer(
            "cmd_producer",
            OutboxAdapter(self.cmd_queue, topic="commands", source="test"),
        )

        # CommandRouter：消費 commands
        self.router.attach(self.ex)

        # WorkspaceManager：消費 raw_text
        self.wm.attach(self.ex)

        # ChatFlow：消費 inbound / summary_out / chat_ctl
        self.chat_flow.attach(self.ex)

        # 消費者：tts → 裸 queue
        self.ex.register_consumer("tts", InboxAdapter(self.tts_queue))

        # 消費者：ui_event → 裸 queue
        self.ex.register_consumer("ui_event", InboxAdapter(self.ui_event_queue))

        self.ex.start()
        self.router.start()
        self.wm.start()
        self.chat_flow.start()

    def tearDown(self):
        self.chat_flow.stop()
        self.router.stop()
        self.wm.stop()
        self.ex.stop()
        self._tmp.cleanup()

    def test_play_last_chain(self):
        """ChatReply "原文" 後，PLAY_LAST_ORIGINAL → tts 再次收到原文。"""
        # 步驟 1：注入 ChatReply "原文"（短回覆 < threshold=100，走直接 TTS）
        self.inbound_queue.put({
            "type": "ChatReply",
            "Content": {"full_response": "原文"},
        })

        # 等待第一次 tts 到達
        self.assertTrue(
            wait_until(lambda: not self.tts_queue.empty()),
            "初始 ChatReply 的 tts 超時未到達",
        )

        # 排空第一次的 tts（確保後面斷言的是重播的那筆）
        drain_queue(self.tts_queue)
        # 也排空 ui_event（避免舊訊息干擾後面斷言）
        drain_queue(self.ui_event_queue)

        # 步驟 2：送出 PLAY_LAST_ORIGINAL 熱鍵字串
        self.cmd_queue.put("PLAY_LAST_ORIGINAL")

        # 步驟 3：等待 tts 再次收到原文
        def tts_has_original():
            items = list(self.tts_queue.queue)
            return any(
                item.get("text") == "原文" and item.get("priority") == "medium"
                for item in items
            )

        self.assertTrue(
            wait_until(tts_has_original),
            "tts 佇列超時未收到重播的「原文」",
        )

        # 驗證 tts 包含正確訊息
        found_tts = False
        tts_items = drain_queue(self.tts_queue)
        for item in tts_items:
            if item.get("text") == "原文" and item.get("priority") == "medium":
                found_tts = True
                break
        self.assertTrue(found_tts, "tts 應包含 text='原文', priority='medium'")

        # 步驟 4：等待 ui_event 中包含「播放最後一次回覆原文」
        def ui_has_play_last():
            items = list(self.ui_event_queue.queue)
            return any(
                "播放最後一次回覆原文" in str(item.get("text", ""))
                for item in items
            )

        self.assertTrue(
            wait_until(ui_has_play_last),
            "ui_event 超時未收到「播放最後一次回覆原文」",
        )

        ui_items = drain_queue(self.ui_event_queue)
        self.assertTrue(
            any("播放最後一次回覆原文" in str(item.get("text", "")) for item in ui_items),
            "ui_event 應包含「播放最後一次回覆原文」",
        )


# ── Test 4: 錯誤鏈 ───────────────────────────────────────────────────────────


class TestErrorChain(unittest.TestCase):
    """Test 4: inbound Error → ui_event [錯誤] + tts high。

    注入 {"type":"Error","message":"boom"} 至 inbound；
    消費 ui_event + tts 確認：
    - ui_event 訊息文字含「[錯誤] boom」
    - tts priority="high"
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()

        # 外設裸 queue
        self.inbound_queue = queue.Queue()   # 注入 Error → inbound
        self.tts_queue = queue.Queue()       # 收集 tts
        self.ui_event_queue = queue.Queue()  # 收集 ui_event

        # 模組
        self.sm = make_sm(self._tmp.name)
        self.chat_flow = ChatFlow(session_manager=self.sm)

        # Exchange 配線
        self.ex = Exchange(idle_sleep=0.001)

        # 生產者：inbound_queue → inbound
        self.ex.register_producer(
            "inbound_producer",
            OutboxAdapter(self.inbound_queue, topic="inbound", source="test"),
        )

        # ChatFlow：消費 inbound / summary_out / chat_ctl
        self.chat_flow.attach(self.ex)

        # 消費者：tts → 裸 queue
        self.ex.register_consumer("tts", InboxAdapter(self.tts_queue))

        # 消費者：ui_event → 裸 queue
        self.ex.register_consumer("ui_event", InboxAdapter(self.ui_event_queue))

        self.ex.start()
        self.chat_flow.start()

    def tearDown(self):
        self.chat_flow.stop()
        self.ex.stop()
        self._tmp.cleanup()

    def test_error_chain_ui_and_tts_high(self):
        """inbound Error "boom" → ui_event 含「[錯誤] boom」；tts priority=high。"""
        # 注入 Error
        self.inbound_queue.put({"type": "Error", "message": "boom"})

        # 等待 tts 收到訊息
        self.assertTrue(
            wait_until(lambda: not self.tts_queue.empty()),
            "tts 佇列超時未收到訊息",
        )

        # 等待 ui_event 收到訊息
        self.assertTrue(
            wait_until(lambda: not self.ui_event_queue.empty()),
            "ui_event 佇列超時未收到訊息",
        )

        # 驗證 tts：priority="high"，文字含 "boom"
        tts_items = drain_queue(self.tts_queue)
        self.assertTrue(
            any(item.get("priority") == "high" for item in tts_items),
            f"tts 應包含 priority='high'，實際: {tts_items}",
        )
        self.assertTrue(
            any("boom" in item.get("text", "") for item in tts_items),
            f"tts 文字應包含 'boom'，實際: {tts_items}",
        )

        # 驗證 ui_event：文字含「[錯誤] boom」
        ui_items = drain_queue(self.ui_event_queue)
        self.assertTrue(
            any("[錯誤] boom" in item.get("text", "") for item in ui_items),
            f"ui_event 應包含「[錯誤] boom」，實際: {ui_items}",
        )


if __name__ == "__main__":
    unittest.main()
