"""Workspace 執行緒安全與 drain() 測試（階段 3，B3）。

執行：python3 -m unittest tests.test_workspace_concurrency
"""

import os
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domain.workspace import Workspace


class TestDrainUnit(unittest.TestCase):
    def test_drain_empty_returns_empty_string(self):
        ws = Workspace("buffer")
        self.assertEqual(ws.drain(), "")
        self.assertEqual(ws.count(), 0)

    def test_drain_flattens_and_clears(self):
        ws = Workspace("buffer", [["a", "b"], "c"])
        self.assertEqual(ws.drain(seg_sep="-", entry_sep="|"), "a-b|c")
        self.assertEqual(ws.count(), 0)
        self.assertTrue(ws.is_empty())


class TestConcurrency(unittest.TestCase):
    def test_append_vs_drain_loses_nothing(self):
        """4 條執行緒各 append 500 筆，主執行緒反覆 drain；收集數＋殘留數 == 2000。"""
        start = time.monotonic()
        ws = Workspace("buffer")
        per_thread, n_threads = 500, 4

        def producer(tag):
            for i in range(per_thread):
                ws.append(f"t{tag}_{i}")

        threads = [threading.Thread(target=producer, args=(t,)) for t in range(n_threads)]
        for t in threads:
            t.start()
        collected = 0
        while any(t.is_alive() for t in threads):
            text = ws.drain(seg_sep=" ", entry_sep=" ")
            if text:
                collected += len(text.split(" "))
        for t in threads:
            t.join(timeout=5)
        remaining = ws.count()
        self.assertEqual(collected + remaining, per_thread * n_threads)
        self.assertLess(time.monotonic() - start, 3.0)

    def test_append_vs_concat_all_keeps_all_segments(self):
        """併發 append 與 concat_all：所有字串片段總數不變。"""
        start = time.monotonic()
        ws = Workspace("buffer")
        per_thread, n_threads = 500, 4
        stop = threading.Event()

        def producer(tag):
            for i in range(per_thread):
                ws.append(f"t{tag}_{i}")

        def concatter():
            while not stop.is_set():
                ws.concat_all(seg_sep=" ")

        c = threading.Thread(target=concatter)
        c.start()
        threads = [threading.Thread(target=producer, args=(t,)) for t in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        stop.set()
        c.join(timeout=5)
        segments = ws.flatten(seg_sep=" ", entry_sep=" ").split(" ")
        self.assertEqual(len(segments), per_thread * n_threads)
        self.assertEqual(len(set(segments)), per_thread * n_threads)
        self.assertLess(time.monotonic() - start, 3.0)


    def test_mixed_mutations_no_errors(self):
        """append 與 move／move_to_top／delete／replace 併發：不拋例外、結構保持 list[list[str]]。"""
        start = time.monotonic()
        ws = Workspace("buffer", ["seed0", "seed1"])
        errors = []

        def producer():
            try:
                for i in range(500):
                    ws.append(f"p{i}")
            except Exception as exc:  # pragma: no cover - 失敗時才會進入
                errors.append(exc)

        def mutator():
            try:
                for i in range(500):
                    n = ws.count()
                    ws.move(i % max(n, 1), 0)
                    ws.move_to_top()
                    ws.replace(0, f"r{i}")
                    if i % 5 == 0:
                        ws.delete(ws.count() - 1)
            except Exception as exc:  # pragma: no cover
                errors.append(exc)

        threads = [threading.Thread(target=producer), threading.Thread(target=mutator)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=5)
        self.assertEqual(errors, [])
        for entry in ws.read_all():
            self.assertIsInstance(entry, list)
            self.assertTrue(all(isinstance(x, str) for x in entry))
        self.assertLess(time.monotonic() - start, 3.0)

if __name__ == "__main__":
    unittest.main()
