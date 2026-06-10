"""modules.WorkspaceManager 單元測試。

執行：python3 -m unittest tests.test_workspace_manager
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.exchange import Exchange
from core.message import Message
from modules.workspace_manager import WorkspaceManager


class TestWorkspaceManager(unittest.TestCase):
    def setUp(self):
        self.wm = WorkspaceManager()

    def test_default_workspaces_and_current(self):
        self.assertEqual(sorted(self.wm.names()), ["buffer", "stt"])
        self.assertEqual(self.wm.current, "buffer")

    def test_handle_appends_to_current_workspace(self):
        self.wm.handle(Message(topic="raw_text", payload="第一句"))
        self.assertEqual(self.wm.get("buffer").lines(), ["第一句"])
        self.assertTrue(self.wm.get("stt").is_empty())

    def test_switch_changes_consumer_target(self):
        self.assertTrue(self.wm.switch("stt"))
        self.wm.handle(Message(topic="raw_text", payload="到 stt"))
        self.assertEqual(self.wm.get("stt").lines(), ["到 stt"])
        self.assertTrue(self.wm.get("buffer").is_empty())

    def test_switch_unknown_returns_false_and_keeps_current(self):
        self.assertFalse(self.wm.switch("nothing"))
        self.assertEqual(self.wm.current, "buffer")

    def test_invalid_initial_current_raises(self):
        with self.assertRaises(ValueError):
            WorkspaceManager(current="nope")

    def test_consumes_raw_text_on_exchange(self):
        ex = Exchange()
        self.wm.attach(ex)
        self.wm.outbox.put(Message(topic="raw_text", payload="經過交換核心"))
        # wm 自己也是生產者；用自己的 outbox 餵 raw_text 回自己的 inbox
        self.assertTrue(ex.tick())
        self.assertEqual(self.wm.inbox.get_nowait().payload, "經過交換核心")


if __name__ == "__main__":
    unittest.main()
