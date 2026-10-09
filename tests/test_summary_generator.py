"""SummaryGenerator 單元測試：摘要成功、失敗 fallback（B14）。

以假 LLMClient 取代網路呼叫；不需要 SLM 伺服器。

執行：python3 -m unittest tests.test_summary_generator
"""

import configparser
import os
import queue
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from llm.summary_generator import SummaryGenerator


def _make_config(enabled: bool = True) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg["SLM"] = {
        "enabled": "true" if enabled else "false",
        "model": "fake-model",
        "base_url": "http://127.0.0.1:9",
        "retry": "0",
    }
    return cfg


class _OneShotQueue:
    """第一次 get 回傳 task，之後令產生器停止並拋 Empty，讓 _loop 只跑一輪。"""

    def __init__(self, task, gen_ref):
        self._task = task
        self._gen_ref = gen_ref

    def get(self, timeout=None):
        if self._task is not None:
            task, self._task = self._task, None
            return task
        self._gen_ref[0]._running = False
        raise queue.Empty


def _run_once(chat_side_effect=None, chat_return=None, enabled=True):
    ref = [None]
    out = queue.Queue()
    in_q = _OneShotQueue({"cmd": "summary", "text": "原文內容", "title": "default"}, ref)
    gen = SummaryGenerator(_make_config(enabled), in_q, out)
    ref[0] = gen
    gen._llm = mock.Mock()
    gen._llm.chat.side_effect = chat_side_effect
    gen._llm.chat.return_value = chat_return
    gen._running = True
    gen._loop()
    items = []
    while not out.empty():
        items.append(out.get_nowait())
    return items


class TestSummaryGenerator(unittest.TestCase):
    def test_success_emits_summary_between_statuses(self):
        items = _run_once(chat_return="摘要")
        self.assertEqual(items, [
            {"type": "status", "text": "SLM摘要中"},
            {"type": "summary", "text": "摘要", "model": "fake-model"},
            {"type": "status", "text": "待機"},
        ])

    def test_exception_emits_summary_failed_with_original_text(self):
        items = _run_once(chat_side_effect=RuntimeError("連線失敗"))
        self.assertEqual(items, [
            {"type": "status", "text": "SLM摘要中"},
            {"type": "summary_failed", "message": "連線失敗", "text": "原文內容"},
            {"type": "status", "text": "待機"},
        ])

    def test_blank_summary_emits_summary_failed(self):
        items = _run_once(chat_return="   ")
        self.assertEqual(items[1], {"type": "summary_failed", "message": "空摘要", "text": "原文內容"})
        self.assertEqual(items[-1], {"type": "status", "text": "待機"})

    def test_disabled_drops_task_silently(self):
        self.assertEqual(_run_once(chat_return="摘要", enabled=False), [])


class TestSummaryGeneratorInputs(unittest.TestCase):
    """餵給 LLM 的參數：摘要提示詞＋任務原文。"""

    def _run_with_task(self, task):
        ref = [None]
        out = queue.Queue()
        gen = SummaryGenerator(_make_config(), _OneShotQueue(task, ref), out)
        ref[0] = gen
        gen._llm = mock.Mock()
        gen._llm.chat.return_value = "摘要"
        gen._running = True
        gen._loop()
        return gen

    def test_chat_receives_summary_prompt_and_task_text(self):
        gen = self._run_with_task({"cmd": "summary", "text": "原文內容"})
        gen._llm.chat.assert_called_once_with(gen._summary_prompt, "原文內容")
        self.assertTrue(gen._summary_prompt)  # prompts/slm_summary.txt 存在且非空

    def test_task_without_text_uses_empty_string(self):
        gen = self._run_with_task({"cmd": "summary"})
        gen._llm.chat.assert_called_once_with(gen._summary_prompt, "")



class TestSummaryGeneratorStop(unittest.TestCase):
    def test_stop_returns_after_worker_thread_exits(self):
        gen = SummaryGenerator(_make_config(), queue.Queue(), queue.Queue())
        gen.start()
        thread = gen._thread
        self.assertTrue(thread.is_alive())
        gen.stop()
        self.assertFalse(thread.is_alive())


if __name__ == "__main__":
    unittest.main()
