"""core.endpoint（Outbox / Inbox）單元測試。

執行：python3 -m unittest tests.test_core_endpoint
"""

import os
import queue
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.endpoint import Inbox, Outbox


class TestOutbox(unittest.TestCase):
    def test_put_then_get(self):
        ob = Outbox()
        ob.put("a")
        self.assertEqual(ob.get_nowait(), "a")

    def test_fifo_order(self):
        ob = Outbox()
        ob.put("a")
        ob.put("b")
        self.assertEqual(ob.get_nowait(), "a")
        self.assertEqual(ob.get_nowait(), "b")

    def test_get_empty_raises(self):
        with self.assertRaises(queue.Empty):
            Outbox().get_nowait()

    def test_empty(self):
        ob = Outbox()
        self.assertTrue(ob.empty())
        ob.put("x")
        self.assertFalse(ob.empty())


class TestInbox(unittest.TestCase):
    def test_put_then_get(self):
        ib = Inbox()
        ib.put_nowait("a")
        self.assertEqual(ib.get_nowait(), "a")

    def test_get_with_timeout_raises_when_empty(self):
        with self.assertRaises(queue.Empty):
            Inbox().get(timeout=0.01)

    def test_empty(self):
        ib = Inbox()
        self.assertTrue(ib.empty())
        ib.put_nowait("x")
        self.assertFalse(ib.empty())


if __name__ == "__main__":
    unittest.main()
