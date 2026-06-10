"""core.Exchange 單元測試。

執行：python3 -m unittest tests.test_core_exchange
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.endpoint import Inbox, Outbox
from core.exchange import Exchange
from core.message import Message


class TestExchangeRouting(unittest.TestCase):
    def setUp(self):
        self.ex = Exchange()
        self.ob = Outbox()
        self.ib = Inbox()
        self.ex.register_producer("p1", self.ob)
        self.ex.register_consumer("topic_a", self.ib)

    def test_tick_moves_exactly_one_message(self):
        self.ob.put(Message(topic="topic_a", payload=1))
        self.ob.put(Message(topic="topic_a", payload=2))
        self.assertTrue(self.ex.tick())
        self.assertEqual(self.ib.get_nowait().payload, 1)
        self.assertTrue(self.ib.empty())  # 一次只搬一筆

    def test_tick_empty_returns_false(self):
        self.assertFalse(self.ex.tick())

    def test_duplicate_consumer_raises(self):
        with self.assertRaises(ValueError):
            self.ex.register_consumer("topic_a", Inbox())

    def test_unrouted_topic_is_dropped(self):
        self.ob.put(Message(topic="nobody", payload=1))
        self.assertTrue(self.ex.tick())   # 丟棄也算做了一個動作
        self.assertFalse(self.ex.tick())  # 訊息已被取出丟棄，不殘留

    def test_round_robin_between_producers(self):
        ob2 = Outbox()
        ib2 = Inbox()
        self.ex.register_producer("p2", ob2)
        self.ex.register_consumer("topic_b", ib2)
        self.ob.put(Message(topic="topic_a", payload="A"))
        ob2.put(Message(topic="topic_b", payload="B"))
        self.assertTrue(self.ex.tick())
        self.assertTrue(self.ex.tick())
        self.assertEqual(self.ib.get_nowait().payload, "A")
        self.assertEqual(ib2.get_nowait().payload, "B")

    def test_broken_producer_does_not_block_others(self):
        bad = mock.Mock()
        bad.get_nowait.side_effect = RuntimeError("boom")
        ex = Exchange()
        ex.register_producer("bad", bad)
        ob, ib = Outbox(), Inbox()
        ex.register_producer("good", ob)
        ex.register_consumer("t", ib)
        ob.put(Message(topic="t", payload="ok"))
        self.assertTrue(ex.tick())
        self.assertEqual(ib.get_nowait().payload, "ok")


class TestExchangeLifecycle(unittest.TestCase):
    def test_start_stop_moves_messages(self):
        ex = Exchange(idle_sleep=0.001)
        ob, ib = Outbox(), Inbox()
        ex.register_producer("p", ob)
        ex.register_consumer("t", ib)
        ex.start()
        try:
            ob.put(Message(topic="t", payload="hi"))
            msg = ib.get(timeout=1)
            self.assertEqual(msg.payload, "hi")
        finally:
            ex.stop()

    def test_stop_joins_thread(self):
        ex = Exchange(idle_sleep=0.001)
        ex.start()
        ex.stop()
        self.assertIsNone(ex._thread)

    def test_loop_survives_broken_producer(self):
        ex = Exchange(idle_sleep=0.001)
        bad = mock.Mock()
        bad.get_nowait.side_effect = RuntimeError("boom")
        ex.register_producer("bad", bad)
        ob, ib = Outbox(), Inbox()
        ex.register_producer("good", ob)
        ex.register_consumer("t", ib)
        ex.start()
        try:
            ob.put(Message(topic="t", payload="ok"))
            self.assertEqual(ib.get(timeout=1).payload, "ok")
        finally:
            ex.stop()


if __name__ == "__main__":
    unittest.main()
