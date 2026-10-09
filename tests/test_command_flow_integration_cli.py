"""指令流整合測試：熱鍵／語音指令／終端全鏈在真實 Exchange 上驗證——終端指令流。

執行：python3 -m unittest tests.test_command_flow_integration_cli
"""

import os
import queue
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.adapter import OutboxAdapter
from core.exchange import Exchange
from modules.command_router import CommandRouter
from modules.workspace_manager import WorkspaceManager
from tests._helpers import make_sm, wait_until


# ── Test 4: 終端指令流 ───────────────────────────────────────────────────────


class TestCliCommandFlow(unittest.TestCase):
    """Test 4: 裸 cli_cmd_queue → OutboxAdapter(commands) → CommandRouter
    → /ws stt → wm.current == "stt"。
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()

        # 外設裸 queue
        self.cli_cmd_queue = queue.Queue()

        # 模組
        self.wm = WorkspaceManager()
        self.sm = make_sm(self._tmp.name)
        self.router = CommandRouter(
            workspace_manager=self.wm,
            session_manager=self.sm,
            export_dir=self._tmp.name,
        )

        # Exchange 配線
        self.ex = Exchange(idle_sleep=0.001)

        # 生產者：CLI 指令 → commands
        self.ex.register_producer(
            "cli",
            OutboxAdapter(self.cli_cmd_queue, topic="commands", source="cli"),
        )

        # CommandRouter：消費 commands
        self.router.attach(self.ex)

        # WorkspaceManager（CommandRouter 同步呼叫 wm.switch，不需掛 exchange 消費）
        # 但仍 attach 使其 outbox 有 producer 身份（避免 orphan warning）
        self.wm.attach(self.ex)

        self.ex.start()
        self.router.start()
        self.wm.start()

    def tearDown(self):
        self.wm.stop()
        self.router.stop()
        self.ex.stop()
        self._tmp.cleanup()

    def test_cli_ws_switch_changes_current(self):
        """終端 /ws stt 指令讓 wm.current 切換為 "stt"。"""
        self.cli_cmd_queue.put({"cmd": "/ws", "args": ["stt"]})
        self.assertTrue(
            wait_until(lambda: self.wm.current == "stt"),
            "wm.current 超時未切換至 stt",
        )
        self.assertEqual(self.wm.current, "stt")


if __name__ == "__main__":
    unittest.main()
