"""modules.CommandRouter 對話管理與雜項指令單元測試（Task 4）——歷史、存讀檔、停止、說明、離開與未知指令。

執行：python3 -m unittest tests.test_command_router_session_misc
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._router_helpers import cmd, make_router


class TestHistoryCommand(unittest.TestCase):
    """Test 6: /history"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_history_empty(self):
        """Test 6a: /history 空歷史 → SessionManager 的空歷史訊息"""
        msgs = cmd(self.router, "/history")
        self.assertEqual(len(msgs), 1)
        text = msgs[0].payload["text"]
        # get_history() 回傳 "目前沒有對話歷史。"
        self.assertIsInstance(text, str)
        self.assertGreater(len(text), 0)

    def test_history_with_messages(self):
        """Test 6b: /history 有訊息時顯示歷史"""
        self.sm.add_message("user", "hello")
        self.sm.add_message("assistant", "world")
        msgs = cmd(self.router, "/history")
        text = msgs[0].payload["text"]
        self.assertIn("hello", text)
        self.assertIn("world", text)


class TestSaveCommand(unittest.TestCase):
    """Test 7: /save"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_save_with_filename(self):
        """Test 7a: /save myfile → SessionManager 回傳訊息"""
        msgs = cmd(self.router, "/save", ["myfile"])
        self.assertEqual(len(msgs), 1)
        text = msgs[0].payload["text"]
        self.assertIsInstance(text, str)
        self.assertGreater(len(text), 0)

    def test_save_no_args(self):
        """Test 7b: /save 無參數 → 使用預設檔名（SessionManager 決定）"""
        msgs = cmd(self.router, "/save")
        self.assertEqual(len(msgs), 1)
        text = msgs[0].payload["text"]
        self.assertIsInstance(text, str)
        self.assertGreater(len(text), 0)


class TestLoadCommand(unittest.TestCase):
    """Test 8: /load"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_load_no_args_usage(self):
        """Test 8a: /load 無參數 → 用法訊息"""
        msgs = cmd(self.router, "/load")
        text = msgs[0].payload["text"]
        self.assertIn("用法", text)
        self.assertIn("/load", text)

    def test_load_nonexistent_file(self):
        """Test 8b: /load nonexistent → SessionManager 回傳找不到訊息"""
        msgs = cmd(self.router, "/load", ["nonexistent_xyz_abc"])
        text = msgs[0].payload["text"]
        self.assertIsInstance(text, str)
        self.assertGreater(len(text), 0)

    def test_load_multi_word_filename(self):
        """Test 8c: /load 多詞檔名以空格接合"""
        msgs = cmd(self.router, "/load", ["my", "file"])
        text = msgs[0].payload["text"]
        # 傳入的是 "my file"，不存在故回傳錯誤
        self.assertIsInstance(text, str)


class TestStopCommand(unittest.TestCase):
    """Test 9: /stop"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_stop_emits_tts_ctl_and_status(self):
        """Test 9: /stop 發出 tts_ctl STOP_SPEECH + ui_event status 待機"""
        msgs = cmd(self.router, "/stop")
        topics = [m.topic for m in msgs]
        self.assertIn("tts_ctl", topics)
        self.assertIn("ui_event", topics)

        tts_msgs = [m for m in msgs if m.topic == "tts_ctl"]
        self.assertEqual(len(tts_msgs), 1)
        self.assertEqual(tts_msgs[0].payload, "STOP_SPEECH")

        ui_msgs = [m for m in msgs if m.topic == "ui_event"]
        status_msgs = [m for m in ui_msgs if m.payload.get("type") == "status"]
        self.assertTrue(any("待機" in m.payload.get("text", "") for m in status_msgs))


class TestHelpCommand(unittest.TestCase):
    """Test 10: /help"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_help_text_contains_commands(self):
        """Test 10: /help 回傳包含各指令的說明文字"""
        msgs = cmd(self.router, "/help")
        self.assertEqual(len(msgs), 1)
        text = msgs[0].payload["text"]
        # 驗證幾個關鍵指令都在 help text 中
        for keyword in ["/new", "/switch", "/list", "/delete", "/save", "/load",
                        "/rename", "/history", "/send", "/stop", "/help", "/exit"]:
            self.assertIn(keyword, text, f"help text 缺少 {keyword}")


class TestExitCommand(unittest.TestCase):
    """Test 11: /exit"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_exit_emits_app_ctl_exit(self):
        """Test 11: /exit 發出 app_ctl EXIT"""
        msgs = cmd(self.router, "/exit")
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0].topic, "app_ctl")
        self.assertEqual(msgs[0].payload, "EXIT")


class TestUnknownCommand(unittest.TestCase):
    """Test 12: unknown cmd（terminal_input 發的 {"cmd":"unknown","args":[line]}）"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_unknown_cmd_shows_original_line(self):
        """Test 12a: unknown cmd 顯示 args[0] 而非 cmd 值 "unknown"。

        terminal_input 發 {"cmd":"unknown","args":["/typo"]}；
        訊息應包含 "/typo" 而不是 "unknown"。
        """
        msgs = cmd(self.router, "unknown", ["/typo"])
        text = msgs[0].payload["text"]
        self.assertIn("未知指令", text)
        self.assertIn("/typo", text)
        # 不應出現字串 "unknown" 作為指令名
        self.assertNotIn("未知指令: unknown", text)

    def test_unknown_cmd_empty_args(self):
        """Test 12b: unknown cmd 沒有 args 時顯示空字串（不崩潰）"""
        msgs = cmd(self.router, "unknown", [])
        text = msgs[0].payload["text"]
        self.assertIn("未知指令", text)

    def test_fallthrough_unknown_cmd_uses_cmd_value(self):
        """Test 12c: 完全未知的 cmd 字串（fallthrough）使用 cmd 值本身。

        與 unknown cmd 不同：fallthrough 是未在 dispatch 列舉的指令名稱。
        """
        msgs = cmd(self.router, "/totally_unknown_cmd_xyz")
        text = msgs[0].payload["text"]
        self.assertIn("未知指令", text)
        self.assertIn("/totally_unknown_cmd_xyz", text)


if __name__ == "__main__":
    unittest.main()
