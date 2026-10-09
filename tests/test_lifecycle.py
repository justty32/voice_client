"""Lifecycle 啟停註冊表測試：順序、例外隔離、reverse 選項。

執行：python3 -m unittest tests.test_lifecycle
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app_wiring.assembly import Lifecycle


class _Fake:
    def __init__(self, name, log, *, fail_start=False, fail_stop=False):
        self.name = name
        self._log = log
        self._fail_start = fail_start
        self._fail_stop = fail_stop

    def start(self):
        self._log.append(("start", self.name))
        if self._fail_start:
            raise RuntimeError("start 失敗")

    def stop(self):
        self._log.append(("stop", self.name))
        if self._fail_stop:
            raise RuntimeError("stop 失敗")


def _build(log, **flags):
    lc = Lifecycle()
    for name in ("a", "b", "c"):
        lc.add(name, _Fake(name, log, **flags.get(name, {})))
    return lc


class TestLifecycle(unittest.TestCase):
    def test_start_all_in_registration_order(self):
        log = []
        lc = _build(log)
        lc.start_all()
        self.assertEqual(log, [("start", "a"), ("start", "b"), ("start", "c")])
        self.assertEqual(lc.started, ["a", "b", "c"])
        self.assertEqual(lc.names(), ["a", "b", "c"])

    def test_stop_all_default_forward_order(self):
        log = []
        lc = _build(log)
        lc.start_all()
        log.clear()
        lc.stop_all()
        self.assertEqual(log, [("stop", "a"), ("stop", "b"), ("stop", "c")])
        self.assertEqual(lc.started, [])

    def test_stop_all_reverse(self):
        log = []
        lc = _build(log)
        lc.start_all()
        log.clear()
        lc.stop_all(reverse=True)
        self.assertEqual(log, [("stop", "c"), ("stop", "b"), ("stop", "a")])

    def test_stop_exception_does_not_block_others(self):
        log = []
        lc = _build(log, b={"fail_stop": True})
        lc.start_all()
        log.clear()
        with self.assertLogs("app.lifecycle", level="ERROR"):
            lc.stop_all()
        self.assertEqual(log, [("stop", "a"), ("stop", "b"), ("stop", "c")])

    def test_start_exception_propagates_and_records_started(self):
        log = []
        lc = _build(log, b={"fail_start": True})
        with self.assertRaises(RuntimeError):
            lc.start_all()
        self.assertEqual(lc.started, ["a"])
        log.clear()
        lc.stop_all()
        self.assertEqual(log, [("stop", "a")])


if __name__ == "__main__":
    unittest.main()
