"""utils.logging_setup 單元測試：log_file 路徑處理（B13）。

測試前後保存並還原 root logger 的 handlers 與工作目錄，不污染其他測試。

執行：python3 -m unittest tests.test_logging_setup
"""

import configparser
import logging
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.logging_setup import setup_logging


def _config(log_file: str) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg["LOGGING"] = {"level": "INFO"}
    cfg["WORKSPACE"] = {"log_file": log_file}
    return cfg


class TestSetupLogging(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self._old_cwd = os.getcwd()
        os.chdir(self._tmp.name)
        root = logging.getLogger()
        self._old_handlers = root.handlers[:]
        self._old_level = root.level
        root.handlers.clear()  # 讓 basicConfig 真的生效

    def tearDown(self):
        root = logging.getLogger()
        for h in root.handlers:
            h.close()
        root.handlers.clear()
        root.handlers.extend(self._old_handlers)
        root.setLevel(self._old_level)
        os.chdir(self._old_cwd)
        self._tmp.cleanup()

    def test_bare_filename_does_not_raise(self):
        setup_logging(_config("system.log"))
        self.assertTrue(os.path.isfile(os.path.join(self._tmp.name, "system.log")))

    def test_nested_directory_is_created(self):
        setup_logging(_config(os.path.join("out", "logs", "system.log")))
        self.assertTrue(os.path.isfile(os.path.join(self._tmp.name, "out", "logs", "system.log")))


if __name__ == "__main__":
    unittest.main()
