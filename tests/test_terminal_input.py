"""TerminalInput 單元測試：以 mock 的 input() 驅動 _loop，驗證文字／斜線指令分流。

不讀真正的 stdin；每個案例以 EOFError 或 /exit 結束迴圈。

執行：python3 -m unittest tests.test_terminal_input
"""

import configparser
import os
import queue
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from terminal_input import EXIT_SIGNAL, TerminalInput


def _drain(q: queue.Queue) -> list:
    items = []
    while not q.empty():
        items.append(q.get_nowait())
    return items


def _run(lines):
    """依序餵入 lines（可含例外類別／實例），回傳 (text 佇列內容, cmd 佇列內容)。"""
    text_q, cmd_q = queue.Queue(), queue.Queue()
    ti = TerminalInput(configparser.ConfigParser(), text_q, cmd_q)
    ti._running = True
    with mock.patch("builtins.input", side_effect=list(lines)):
        ti._loop()
    return _drain(text_q), _drain(cmd_q)


class TestTerminalInput(unittest.TestCase):
    def test_blank_lines_are_skipped(self):
        texts, cmds = _run(["", "   ", EOFError])
        self.assertEqual(texts, [EXIT_SIGNAL])
        self.assertEqual(cmds, [])

    def test_plain_text_goes_to_text_queue_stripped(self):
        texts, cmds = _run(["  你好 世界  ", EOFError])
        self.assertEqual(texts, ["你好 世界", EXIT_SIGNAL])
        self.assertEqual(cmds, [])

    def test_known_command_without_args(self):
        _texts, cmds = _run(["/send", EOFError])
        self.assertEqual(cmds, [{"cmd": "/send", "args": []}])

    def test_command_is_lowercased_and_args_kept(self):
        _texts, cmds = _run(["/Export my file", EOFError])
        self.assertEqual(cmds, [{"cmd": "/export", "args": ["my", "file"]}])

    def test_unknown_command_carries_whole_line(self):
        _texts, cmds = _run(["/foo bar", EOFError])
        self.assertEqual(cmds, [{"cmd": "unknown", "args": ["/foo bar"]}])

    def test_exit_emits_command_and_exit_signal_then_stops(self):
        # /exit 之後的輸入不應再被讀取
        texts, cmds = _run(["/exit", "不該被讀到"])
        self.assertEqual(cmds, [{"cmd": "/exit", "args": []}])
        self.assertEqual(texts, [EXIT_SIGNAL])

    def test_eof_emits_exit_signal(self):
        texts, cmds = _run([EOFError])
        self.assertEqual(texts, [EXIT_SIGNAL])
        self.assertEqual(cmds, [])


if __name__ == "__main__":
    unittest.main()
