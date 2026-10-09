"""聊天流整合測試：全鏈在真實 Exchange 上驗證——重播與錯誤鏈。

執行：python3 -m unittest tests.test_chat_flow_integration_playback
"""

import os
import queue
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.adapter import InboxAdapter, OutboxAdapter
from core.exchange import Exchange
from modules.chat_flow import ChatFlow
from modules.command_router import CommandRouter
from modules.workspace_manager import WorkspaceManager
from tests._helpers import drain_queue, make_sm, wait_until


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
