"""core.TunnelModule 單元測試。

執行：python3 -m unittest tests.test_core_module
"""

import os
import queue
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.exchange import Exchange
from core.message import Message
from core.module import TunnelModule


class EchoConsumer(TunnelModule):
    name = "echo"
    consumes = ("ping",)

    def __init__(self):
        super().__init__()
        self.received = []

    def handle(self, message):
        self.received.append(message.payload)
        self.emit("pong", message.payload)


class BoomConsumer(TunnelModule):
    name = "boom"
    consumes = ("ping",)

    def handle(self, message):
        raise RuntimeError("炸了")


class SilentBoomConsumer(BoomConsumer):
    name = "silent_boom"

    def __init__(self):
        super().__init__()
        self.errors = []

    def on_handle_error(self, message, exc):
        self.errors.append((message.topic, exc))


def wait_outbox(testcase, module, timeout=1.0):
    """輪詢模組 outbox 直到取得一筆訊息，逾時則 fail。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            return module.outbox.get_nowait()
        except queue.Empty:
            time.sleep(0.005)
    testcase.fail("outbox 逾時無資料")


class TestTunnelModule(unittest.TestCase):
    def test_emit_wraps_message(self):
        m = EchoConsumer()
        m.emit("ping", {"a": 1})
        msg = m.outbox.get_nowait()
        self.assertIsInstance(msg, Message)
        self.assertEqual(msg.topic, "ping")
        self.assertEqual(msg.payload, {"a": 1})
        self.assertEqual(msg.source, "echo")

    def test_attach_registers_producer_and_consumer(self):
        ex = Exchange()
        m = EchoConsumer()
        m.attach(ex)
        # emit 進自己的 outbox，經 tick 路由回自己的 inbox（echo 訂閱 ping）
        m.emit("ping", "x")
        self.assertTrue(ex.tick())
        self.assertEqual(m.inbox.get_nowait().payload, "x")

    def test_consume_loop_calls_handle(self):
        m = EchoConsumer()
        m.start()
        try:
            m.inbox.put_nowait(Message(topic="ping", payload="hello"))
            msg = wait_outbox(self, m)
            self.assertEqual(msg.topic, "pong")
            self.assertEqual(msg.payload, "hello")
            self.assertEqual(m.received, ["hello"])
        finally:
            m.stop()

    def test_handle_exception_emits_ui_event(self):
        m = BoomConsumer()
        m.start()
        try:
            m.inbox.put_nowait(Message(topic="ping", payload="x"))
            msg = wait_outbox(self, m)
            self.assertEqual(msg.topic, "ui_event")
            self.assertEqual(msg.payload["type"], "message")
            self.assertIn("boom", msg.payload["text"])
            self.assertIn("ping", msg.payload["text"])
            self.assertIn("炸了", msg.payload["text"])  # 例外文字帶到 UI
        finally:
            m.stop()

    def test_overridden_on_handle_error_replaces_default_emit(self):
        m = SilentBoomConsumer()
        m.start()
        try:
            m.inbox.put_nowait(Message(topic="ping", payload="x"))
            deadline = time.time() + 1.0
            while not m.errors and time.time() < deadline:
                time.sleep(0.005)
            self.assertEqual(len(m.errors), 1)
            topic, exc = m.errors[0]
            self.assertEqual(topic, "ping")
            self.assertIsInstance(exc, RuntimeError)
            self.assertTrue(m.outbox.empty(), "覆寫 hook 後基底不應再 emit ui_event")
        finally:
            m.stop()

    def test_handle_exception_does_not_kill_loop(self):
        m = BoomConsumer()
        m.start()
        try:
            m.inbox.put_nowait(Message(topic="ping", payload="第一筆"))
            wait_outbox(self, m)  # 第一筆的錯誤 ui_event
            m.inbox.put_nowait(Message(topic="ping", payload="第二筆"))
            msg = wait_outbox(self, m)  # 迴圈仍在運作，產出第二筆的錯誤
            self.assertEqual(msg.topic, "ui_event")
        finally:
            m.stop()

    def test_stop_joins_thread(self):
        m = EchoConsumer()
        m.start()
        m.stop()
        self.assertIsNone(m._thread)


if __name__ == "__main__":
    unittest.main()
