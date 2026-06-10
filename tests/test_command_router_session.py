"""modules.CommandRouter 對話管理與雜項指令單元測試（Task 4）。

執行：python3 -m unittest tests.test_command_router_session
"""

import configparser
import os
import queue
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.message import Message
from modules.command_router import CommandRouter
from modules.workspace_manager import WorkspaceManager
from session_manager import SessionManager


# ── 共用 fixtures ──────────────────────────────────────────────────────────────


def make_sm(tmp: str) -> SessionManager:
    cfg = configparser.ConfigParser()
    cfg["WORKSPACE"] = {
        "sessions_file": os.path.join(tmp, "output", ".sessions.json"),
        "deleted_sessions_dir": os.path.join(tmp, "output", "deleted"),
    }
    sm = SessionManager(cfg)
    sm.new_session("default")
    return sm


def make_router(tmp: str, sm=None) -> tuple:
    """回傳 (router, wm, sm)；export_dir 指向 tmp。"""
    wm = WorkspaceManager()
    if sm is None:
        sm = make_sm(tmp)
    router = CommandRouter(workspace_manager=wm, session_manager=sm, export_dir=tmp)
    return router, wm, sm


def drain(router) -> list:
    """取出所有 outbox 訊息，回傳 list[Message]。"""
    msgs = []
    while True:
        try:
            msgs.append(router.outbox.get_nowait())
        except queue.Empty:
            break
    return msgs


def cmd(router, cmd_str: str, args: list = None):
    """送出一個 /cmd 指令並回傳所有輸出訊息。"""
    payload = {"cmd": cmd_str, "args": args if args is not None else []}
    router.handle(Message(topic="commands", payload=payload))
    return drain(router)


# ── Test classes ───────────────────────────────────────────────────────────────


class TestNewCommand(unittest.TestCase):
    """Test 1: /new"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_new_with_title(self):
        """Test 1a: /new mytitle 建立指定名稱對話並回傳訊息"""
        msgs = cmd(self.router, "/new", ["mytitle"])
        self.assertEqual(len(msgs), 1)
        text = msgs[0].payload["text"]
        self.assertIn("新建對話", text)
        self.assertIn("mytitle", text)
        self.assertEqual(self.sm.current_title, "mytitle")

    def test_new_default_title(self):
        """Test 1b: /new 無參數使用 session_N 格式預設標題"""
        # 初始有 1 個 session（default），所以下一個應為 session_2
        count_before = len(self.sm.list_sessions())
        msgs = cmd(self.router, "/new")
        self.assertEqual(len(msgs), 1)
        text = msgs[0].payload["text"]
        self.assertIn("新建對話", text)
        expected_title = f"session_{count_before + 1}"
        self.assertIn(expected_title, text)
        self.assertEqual(self.sm.current_title, expected_title)

    def test_new_multi_word_title(self):
        """Test 1c: /new my big title 多詞標題以空格接合"""
        msgs = cmd(self.router, "/new", ["my", "big", "title"])
        text = msgs[0].payload["text"]
        self.assertIn("my big title", text)
        self.assertEqual(self.sm.current_title, "my big title")


class TestSwitchCommand(unittest.TestCase):
    """Test 2: /switch"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_switch_existing(self):
        """Test 2a: /switch default 切換至已存在的 session"""
        # 先建立 session2 使當前不是 default
        self.sm.new_session("session2")
        msgs = cmd(self.router, "/switch", ["default"])
        text = msgs[0].payload["text"]
        self.assertIn("切換至", text)
        self.assertIn("default", text)
        self.assertEqual(self.sm.current_title, "default")

    def test_switch_missing(self):
        """Test 2b: /switch nonexistent → 找不到對話訊息"""
        msgs = cmd(self.router, "/switch", ["nonexistent"])
        text = msgs[0].payload["text"]
        self.assertIn("找不到對話", text)
        self.assertIn("nonexistent", text)

    def test_switch_default_create_when_missing(self):
        """Test 2c: /switch 無參數且 default 不存在 → 建立並切換"""
        # 先刪掉 default（改名確保 default 不存在）
        self.sm.rename_session("default", "other")
        msgs = cmd(self.router, "/switch")
        text = msgs[0].payload["text"]
        self.assertIn("建立並切換至", text)
        self.assertIn("default", text)
        self.assertEqual(self.sm.current_title, "default")

    def test_switch_no_args_existing_default(self):
        """Test 2d: /switch 無參數且 default 存在 → 正常切換"""
        self.sm.new_session("other")  # 當前變 other
        msgs = cmd(self.router, "/switch")
        text = msgs[0].payload["text"]
        self.assertIn("切換至", text)
        self.assertIn("default", text)
        self.assertEqual(self.sm.current_title, "default")


class TestListCommand(unittest.TestCase):
    """Test 3: /list"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_list_shows_sessions_and_current(self):
        """Test 3a: /list 顯示對話列表並標示當前"""
        self.sm.new_session("session2")
        msgs = cmd(self.router, "/list")
        self.assertEqual(len(msgs), 1)
        text = msgs[0].payload["text"]
        self.assertIn("對話列表", text)
        self.assertIn("default", text)
        self.assertIn("session2", text)
        self.assertIn("當前使用session", text)
        self.assertIn(self.sm.current_title, text)

    def test_list_current_title_shown(self):
        """Test 3b: /list 顯示的「當前」與 sm.current_title 一致"""
        msgs = cmd(self.router, "/list")
        text = msgs[0].payload["text"]
        current = self.sm.current_title or "無"
        self.assertIn(current, text)


class TestDeleteCommand(unittest.TestCase):
    """Test 4: /delete"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_delete_no_args_usage(self):
        """Test 4a: /delete 無參數 → 用法訊息"""
        msgs = cmd(self.router, "/delete")
        text = msgs[0].payload["text"]
        self.assertIn("用法", text)
        self.assertIn("/delete", text)

    def test_delete_success(self):
        """Test 4b: /delete 刪除不是當前的 session"""
        self.sm.new_session("to_delete")
        # 切回 default 讓 to_delete 可以被刪
        self.sm.switch_session("default")
        msgs = cmd(self.router, "/delete", ["to_delete"])
        text = msgs[0].payload["text"]
        # SessionManager.delete_session 回傳成功訊息
        self.assertIn("to_delete", text)

    def test_delete_nonexistent(self):
        """Test 4c: /delete 不存在的 session → 錯誤訊息"""
        msgs = cmd(self.router, "/delete", ["ghost"])
        text = msgs[0].payload["text"]
        self.assertIn("ghost", text)

    def test_delete_multi_word_title(self):
        """Test 4d: /delete 多詞標題以空格接合"""
        self.sm.new_session("my session")
        self.sm.switch_session("default")
        msgs = cmd(self.router, "/delete", ["my", "session"])
        text = msgs[0].payload["text"]
        self.assertIn("my session", text)


class TestRenameCommand(unittest.TestCase):
    """Test 5: /rename"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_rename_usage_too_few_args(self):
        """Test 5a: /rename 只有一個參數 → 用法訊息"""
        msgs = cmd(self.router, "/rename", ["only_one"])
        text = msgs[0].payload["text"]
        self.assertIn("用法", text)
        self.assertIn("/rename", text)

    def test_rename_no_args_usage(self):
        """Test 5b: /rename 無參數 → 用法訊息"""
        msgs = cmd(self.router, "/rename")
        text = msgs[0].payload["text"]
        self.assertIn("用法", text)
        self.assertIn("/rename", text)

    def test_rename_success(self):
        """Test 5c: /rename default newname → SessionManager 回傳成功訊息"""
        msgs = cmd(self.router, "/rename", ["default", "newname"])
        text = msgs[0].payload["text"]
        # SessionManager.rename_session 回傳訊息含新舊名稱
        self.assertIn("newname", text)
        self.assertEqual(self.sm.current_title, "newname")

    def test_rename_nonexistent(self):
        """Test 5d: /rename 舊名不存在 → 找不到訊息"""
        msgs = cmd(self.router, "/rename", ["ghost", "new"])
        text = msgs[0].payload["text"]
        self.assertIn("ghost", text)


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
