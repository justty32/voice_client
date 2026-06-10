"""Recorder error handling tests.

執行：python3 -m unittest tests.test_record
"""

import configparser
import os
import sys
import types
import unittest
from queue import Queue
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

sys.modules.setdefault("numpy", types.SimpleNamespace())
sys.modules.setdefault("pyaudio", types.SimpleNamespace(PyAudio=lambda: None, paInt16=object()))

from record import Recorder


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


class TestRecorderErrors(unittest.TestCase):
    @mock.patch("record.pyaudio.PyAudio", side_effect=RuntimeError("no audio device"))
    def test_worker_reports_pyaudio_init_failure(self, _mock_pyaudio):
        events = Queue()
        rec = Recorder(make_config(), Queue(), Queue(), events)

        rec._worker()

        event = events.get_nowait()
        self.assertEqual(event["event"], "error")
        self.assertIn("no audio device", event["message"])


if __name__ == "__main__":
    unittest.main()
