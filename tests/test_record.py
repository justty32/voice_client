"""Recorder error handling tests.

執行：python3 -m unittest tests.test_record
"""

import configparser
import io
import os
import struct
import sys
import wave
import types
import unittest
from queue import Queue
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 只有環境真的沒有 numpy 時才放 stub；有 numpy 時 _rms 需要真算（_loop 測試依賴）。
try:
    import numpy  # noqa: F401
except ImportError:
    sys.modules.setdefault("numpy", types.SimpleNamespace())
sys.modules.setdefault("pyaudio", types.SimpleNamespace(PyAudio=lambda: None, paInt16=object()))

from speech.record import Recorder


def make_config() -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg["AUDIO"] = {
        "sample_rate": "16000",
        "channels": "1",
        "chunk_size": "1024",
        "chunk_duration": "60",
        "silence_seconds": "1.5",
        "silence_threshold": "300",
        "max_duration": "0",
    }
    return cfg


class _FakeOpenPA:
    """PyAudio 替身：open() 回傳假 stream，記錄 terminate。"""

    def __init__(self):
        self.terminated = False

    def open(self, **_kwargs):
        return mock.Mock()

    def get_sample_size(self, _fmt):
        return 2

    def terminate(self):
        self.terminated = True


class TestRecorderErrors(unittest.TestCase):
    def test_worker_reports_failure_then_retries(self):
        """PyAudio 第一次拋例外 → error 事件恰 1 筆、退避後重試並進入 _loop（B7）。"""
        events = Queue()
        rec = Recorder(make_config(), Queue(), Queue(), events)
        rec._running = True
        fake_pa = _FakeOpenPA()
        loop_calls = []

        def _fake_loop(stream, pa):
            loop_calls.append((stream, pa))
            rec._running = False  # 進入 _loop 後結束 worker

        with mock.patch("speech.record.pyaudio.PyAudio",
                        side_effect=[RuntimeError("no audio device"), fake_pa]), \
                mock.patch("speech.record.time.sleep") as fake_sleep, \
                mock.patch.object(rec, "_interruptible_sleep") as backoff, \
                mock.patch.object(rec, "_loop", side_effect=_fake_loop):
            rec._worker()

        evs = []
        while not events.empty():
            evs.append(events.get_nowait())
        self.assertEqual(len(evs), 1)
        self.assertEqual(evs[0]["event"], "error")
        self.assertIn("no audio device", evs[0]["message"])
        self.assertEqual(len(loop_calls), 1)
        self.assertIs(loop_calls[0][1], fake_pa)
        self.assertTrue(fake_pa.terminated)
        backoff.assert_called_once_with(2)
        fake_sleep.assert_not_called()

    def test_backoff_grows_and_caps_until_stop(self):
        """連續失敗退避 2、4、8、16、30、30…；stop() 後 worker 結束。"""
        rec = Recorder(make_config(), Queue(), Queue(), Queue())
        rec._running = True
        waits = []

        def _record_wait(secs):
            waits.append(secs)
            if len(waits) >= 6:
                rec._running = False

        with mock.patch("speech.record.pyaudio.PyAudio", side_effect=RuntimeError("busy")), \
                mock.patch.object(rec, "_interruptible_sleep", side_effect=_record_wait):
            rec._worker()
        self.assertEqual(waits, [2, 4, 8, 16, 30.0, 30.0])

    def test_interruptible_sleep_returns_after_stop(self):
        rec = Recorder(make_config(), Queue(), Queue(), Queue())
        rec._running = True
        calls = []

        def _tick(_secs):
            calls.append(1)
            rec._running = False

        with mock.patch("speech.record.time.sleep", side_effect=_tick):
            rec._interruptible_sleep(30)
        self.assertEqual(len(calls), 1)

    def test_worker_not_started_does_nothing(self):
        events = Queue()
        rec = Recorder(make_config(), Queue(), Queue(), events)
        with mock.patch("speech.record.pyaudio.PyAudio") as pa:
            rec._worker()
        pa.assert_not_called()
        self.assertTrue(events.empty())


class _FakePA:
    def get_sample_size(self, _fmt):
        return 2


class _FakeStream:
    """read() 固定回傳同一段 PCM；第 stop_after 次呼叫時把 STOP 放進指令佇列。"""

    def __init__(self, data: bytes, cmd_queue: Queue, stop_after: int = 3):
        self._data = data
        self._cmd_queue = cmd_queue
        self._stop_after = stop_after
        self.reads = 0

    def read(self, _n, exception_on_overflow=False):
        self.reads += 1
        if self.reads == self._stop_after:
            self._cmd_queue.put("STOP")
        return self._data


class TestRecorderLoopStopFlush(unittest.TestCase):
    """B8：STOP 時以 flushed 標示是否有音訊送往 STT。"""

    def _run_loop(self, pcm: bytes):
        cmd_q, audio_q, events = Queue(), Queue(), Queue()
        rec = Recorder(make_config(), cmd_q, audio_q, events)
        rec._running = True
        cmd_q.put("START")
        stream = _FakeStream(pcm, cmd_q)

        def _stop_on_idle(_secs):
            # STOP 處理完後迴圈進入待機 sleep：此時結束 _loop
            rec._running = False

        with mock.patch("speech.record.time.sleep", side_effect=_stop_on_idle):
            rec._loop(stream, _FakePA())

        evs = []
        while not events.empty():
            evs.append(events.get_nowait())
        return evs, audio_q

    def test_silent_recording_reports_not_flushed(self):
        evs, audio_q = self._run_loop(b"\x00\x00" * 1024)
        self.assertEqual(evs[0], {"event": "recording_started"})
        self.assertEqual(evs[-1], {"event": "recording_stopped", "flushed": False})
        self.assertTrue(audio_q.empty())

    def test_speech_recording_reports_flushed_and_emits_wav(self):
        loud = struct.pack("<h", 10000) * 1024
        evs, audio_q = self._run_loop(loud)
        self.assertEqual(evs[-1], {"event": "recording_stopped", "flushed": True})
        buf = audio_q.get_nowait()
        self.assertIsInstance(buf, io.BytesIO)
        with wave.open(buf, "rb") as wf:
            self.assertEqual(wf.getnchannels(), 1)
            self.assertEqual(wf.getsampwidth(), 2)
            self.assertGreater(wf.getnframes(), 0)
        self.assertTrue(audio_q.empty())


if __name__ == "__main__":
    unittest.main()
