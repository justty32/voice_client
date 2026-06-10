"""core 框架端到端整合測試：假生產者 → Exchange → 假消費者。

執行：python3 -m unittest tests.test_core_integration
"""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.exchange import Exchange
from core.module import TunnelModule


class FakeStt(TunnelModule):
    """純生產者：模擬 STT 不斷產出 raw_text。"""
    name = "fake_stt"


class FakeWorkspace(TunnelModule):
    """消費者：模擬當前工作區收集 raw_text。"""
    name = "fake_workspace"
    consumes = ("raw_text",)

    def __init__(self):
        super().__init__()
        self.texts = []

    def handle(self, message):
        self.texts.append(message.payload)


class RelayRouter(TunnelModule):
    """同時是消費者＋生產者：收到 command 後轉發控制訊息。"""
    name = "fake_router"
    consumes = ("commands",)

    def handle(self, message):
        if message.payload == "record_toggle":
            self.emit("recorder_ctl", "START")


class CtlCollector(TunnelModule):
    name = "fake_recorder"
    consumes = ("recorder_ctl",)

    def __init__(self):
        super().__init__()
        self.ctls = []

    def handle(self, message):
        self.ctls.append(message.payload)


def wait_until(predicate, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class TestEndToEnd(unittest.TestCase):
    def test_producer_to_consumer_preserves_order(self):
        ex = Exchange(idle_sleep=0.001)
        stt = FakeStt()
        ws = FakeWorkspace()
        stt.attach(ex)
        ws.attach(ex)
        ex.start()
        ws.start()
        try:
            for i in range(5):
                stt.emit("raw_text", f"句子{i}")
            self.assertTrue(wait_until(lambda: len(ws.texts) == 5))
            self.assertEqual(ws.texts, [f"句子{i}" for i in range(5)])
        finally:
            ws.stop()
            ex.stop()

    def test_consumer_can_also_produce(self):
        ex = Exchange(idle_sleep=0.001)
        keys = FakeStt()  # 借用純生產者模擬熱鍵
        router = RelayRouter()
        rec = CtlCollector()
        keys.attach(ex)
        router.attach(ex)
        rec.attach(ex)
        ex.start()
        router.start()
        rec.start()
        try:
            keys.emit("commands", "record_toggle")
            self.assertTrue(wait_until(lambda: rec.ctls == ["START"]))
        finally:
            rec.stop()
            router.stop()
            ex.stop()


if __name__ == "__main__":
    unittest.main()
