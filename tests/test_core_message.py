"""core.Message 單元測試。

執行：python3 -m unittest tests.test_core_message
"""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.message import Message


class TestMessage(unittest.TestCase):
    def test_required_fields(self):
        msg = Message(topic="raw_text", payload="hello")
        self.assertEqual(msg.topic, "raw_text")
        self.assertEqual(msg.payload, "hello")
        self.assertEqual(msg.source, "")

    def test_created_at_auto(self):
        before = time.time()
        msg = Message(topic="t", payload=None)
        self.assertGreaterEqual(msg.created_at, before)
        self.assertLessEqual(msg.created_at, time.time())

    def test_source(self):
        msg = Message(topic="t", payload=1, source="stt")
        self.assertEqual(msg.source, "stt")


if __name__ == "__main__":
    unittest.main()
