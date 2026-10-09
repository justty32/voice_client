"""聊天流整合測試：全鏈在真實 Exchange 上驗證——摘要鏈。

執行：python3 -m unittest tests.test_chat_flow_integration_summary
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
from tests._helpers import make_sm, wait_until


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


if __name__ == "__main__":
    unittest.main()
