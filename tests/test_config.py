"""config.load_config 單元測試。

執行：python3 -m unittest tests.test_config
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import load_config


class TestLoadConfig(unittest.TestCase):
    def test_missing_file_returns_empty_config(self):
        with tempfile.TemporaryDirectory() as tmp:
            cfg = load_config(os.path.join(tmp, "不存在.ini"))
        self.assertEqual(cfg.sections(), [])

    def test_reads_utf8_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "config.ini")
            with open(path, "w", encoding="utf-8") as f:
                f.write("[TTS]\nvoice = 中文語音\n")
            cfg = load_config(path)
        self.assertEqual(cfg["TTS"]["voice"], "中文語音")


if __name__ == "__main__":
    unittest.main()
