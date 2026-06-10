"""core.adapter（OutboxAdapter / InboxAdapter）單元測試。

執行：python3 -m unittest tests.test_core_adapter
"""

import os
import queue
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.adapter import InboxAdapter, OutboxAdapter
from core.endpoint import Inbox
from core.exchange import Exchange
from core.message import Message


class TestOutboxAdapter(unittest.TestCase):
    def test_wraps_raw_item_into_message(self):
        raw = queue.Queue()
        adapter = OutboxAdapter(raw, topic="raw_text", source="legacy_stt")
        raw.put("哈囉")
        msg = adapter.get_nowait()
        self.assertIsInstance(msg, Message)
        self.assertEqual(msg.topic, "raw_text")
        self.assertEqual(msg.payload, "哈囉")
        self.assertEqual(msg.source, "legacy_stt")

    def test_get_empty_raises(self):
        adapter = OutboxAdapter(queue.Queue(), topic="t")
        with self.assertRaises(queue.Empty):
            adapter.get_nowait()

    def test_empty_reflects_raw_queue(self):
        raw = queue.Queue()
        adapter = OutboxAdapter(raw, topic="t")
        self.assertTrue(adapter.empty())
        raw.put(b"audio-bytes")
        self.assertFalse(adapter.empty())


class TestInboxAdapter(unittest.TestCase):
    def test_unwraps_payload_into_raw_queue(self):
        raw = queue.Queue()
        adapter = InboxAdapter(raw)
        adapter.put_nowait(Message(topic="audio", payload=b"wav"))
        self.assertEqual(raw.get_nowait(), b"wav")

    def test_empty_reflects_raw_queue(self):
        raw = queue.Queue()
        adapter = InboxAdapter(raw)
        self.assertTrue(adapter.empty())
        adapter.put_nowait(Message(topic="t", payload=1))
        self.assertFalse(adapter.empty())

    def test_transform_applied(self):
        """有 transform 時，投遞的是 transform(payload) 而非原始 payload。"""
        raw = queue.Queue()
        adapter = InboxAdapter(raw, transform=lambda p: ("wrapped", p))
        adapter.put_nowait(Message(topic="ui_event", payload="x"))
        self.assertEqual(raw.get_nowait(), ("wrapped", "x"))

    def test_no_transform_unchanged(self):
        """transform=None（預設）時行為與舊版相同，直接投遞 payload。"""
        raw = queue.Queue()
        adapter = InboxAdapter(raw)
        adapter.put_nowait(Message(topic="ui_event", payload={"key": "value"}))
        self.assertEqual(raw.get_nowait(), {"key": "value"})


class TestAdaptersOnExchange(unittest.TestCase):
    def test_legacy_queues_route_through_exchange(self):
        """既有模組的輸出 queue → Exchange → 既有模組的輸入 queue，全程零改寫。"""
        legacy_out = queue.Queue()   # 模擬 Recorder 的 audio_queue（輸出側）
        legacy_in = queue.Queue()    # 模擬 VoiceToText 的 audio_queue（輸入側）
        ex = Exchange()
        ex.register_producer("recorder", OutboxAdapter(legacy_out, topic="audio", source="recorder"))
        ex.register_consumer("audio", InboxAdapter(legacy_in))
        legacy_out.put(b"chunk-1")
        self.assertTrue(ex.tick())
        self.assertEqual(legacy_in.get_nowait(), b"chunk-1")

    def test_adapter_and_native_inbox_coexist(self):
        """轉接器生產者可以路由到原生 Inbox 消費者。"""
        legacy_out = queue.Queue()
        ib = Inbox()
        ex = Exchange()
        ex.register_producer("legacy", OutboxAdapter(legacy_out, topic="raw_text"))
        ex.register_consumer("raw_text", ib)
        legacy_out.put("你好")
        self.assertTrue(ex.tick())
        self.assertEqual(ib.get_nowait().payload, "你好")


if __name__ == "__main__":
    unittest.main()
