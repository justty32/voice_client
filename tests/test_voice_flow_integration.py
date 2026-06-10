"""語音資料流整合測試：模擬既有模組（裸 queue＋自有執行緒）經轉接器上隧道。

驗證階段②目標：Recorder →audio→ STT →raw_text→ 當前工作區，
其中「Recorder」「STT」用與既有模組相同的介面形態（裸 queue.Queue），
完全不依賴 record.py / voice_to_text.py 的硬體與模型。

執行：python3 -m unittest tests.test_voice_flow_integration
"""

import os
import queue
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.adapter import InboxAdapter, OutboxAdapter
from core.exchange import Exchange
from modules.workspace_manager import WorkspaceManager


class FakeLegacyStt:
    """形態同 voice_to_text.VoiceToText：裸輸入/輸出 queue＋自有工作執行緒。"""

    def __init__(self, audio_queue: queue.Queue, text_queue: queue.Queue):
        self._audio_queue = audio_queue
        self._text_queue = text_queue
        self._running = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def _loop(self):
        while self._running:
            try:
                chunk = self._audio_queue.get(timeout=0.05)
            except queue.Empty:
                continue
            self._text_queue.put(f"辨識[{chunk.decode()}]")


def wait_until(predicate, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class TestVoiceFlow(unittest.TestCase):
    def setUp(self):
        # 既有模組形態的裸 queue
        self.recorder_audio_out = queue.Queue()  # 模擬 Recorder 的輸出
        self.stt_audio_in = queue.Queue()        # FakeLegacyStt 的輸入
        self.stt_text_out = queue.Queue()        # FakeLegacyStt 的輸出

        self.stt = FakeLegacyStt(self.stt_audio_in, self.stt_text_out)
        self.wm = WorkspaceManager()

        self.ex = Exchange(idle_sleep=0.001)
        self.ex.register_producer(
            "recorder", OutboxAdapter(self.recorder_audio_out, topic="audio", source="recorder"))
        self.ex.register_consumer("audio", InboxAdapter(self.stt_audio_in))
        self.ex.register_producer(
            "stt", OutboxAdapter(self.stt_text_out, topic="raw_text", source="stt"))
        self.wm.attach(self.ex)

        self.ex.start()
        self.stt.start()
        self.wm.start()

    def tearDown(self):
        self.wm.stop()
        self.stt.stop()
        self.ex.stop()

    def test_audio_reaches_current_workspace_as_text(self):
        self.recorder_audio_out.put(b"hello")
        self.assertTrue(wait_until(lambda: self.wm.get("buffer").count() == 1))
        self.assertEqual(self.wm.get("buffer").lines(), ["辨識[hello]"])
        self.assertTrue(self.wm.get("stt").is_empty())

    def test_switch_redirects_following_texts(self):
        self.recorder_audio_out.put(b"one")
        self.assertTrue(wait_until(lambda: self.wm.get("buffer").count() == 1))
        self.wm.switch("stt")
        self.recorder_audio_out.put(b"two")
        self.assertTrue(wait_until(lambda: self.wm.get("stt").count() == 1))
        self.assertEqual(self.wm.get("buffer").lines(), ["辨識[one]"])
        self.assertEqual(self.wm.get("stt").lines(), ["辨識[two]"])

    def test_order_preserved_under_burst(self):
        for i in range(10):
            self.recorder_audio_out.put(f"c{i}".encode())
        self.assertTrue(wait_until(lambda: self.wm.get("buffer").count() == 10))
        self.assertEqual(
            self.wm.get("buffer").lines(),
            [f"辨識[c{i}]" for i in range(10)],
        )


if __name__ == "__main__":
    unittest.main()
