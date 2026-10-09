"""modules.CommandRouter 對話管理與雜項指令單元測試（Task 4）——對話新增、切換、列表、刪除、改名。

執行：python3 -m unittest tests.test_command_router_session_manage
"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests._router_helpers import cmd, make_router


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
        """Test 1b: /new 無參數使用第一個未用的 session_N（N 從 1 起，B5／D5）"""
        # 初始只有 default，沒有 session_1 → 應建立 session_1
        msgs = cmd(self.router, "/new")
        self.assertEqual(len(msgs), 1)
        text = msgs[0].payload["text"]
        self.assertIn("新建對話", text)
        self.assertIn("session_1", text)
        self.assertEqual(self.sm.current_title, "session_1")

    def test_new_default_title_skips_used(self):
        """Test 1b-2: 已有 session_1 時，/new 無參數建立 session_2"""
        self.sm.new_session("session_1")
        msgs = cmd(self.router, "/new")
        self.assertIn("session_2", msgs[0].payload["text"])
        self.assertEqual(self.sm.current_title, "session_2")

    def test_new_default_title_fills_gap(self):
        """Test 1b-3: 編號有空缺時取第一個未用者（session_1、session_3 已存在 → session_2）"""
        self.sm.new_session("session_1")
        self.sm.new_session("session_3")
        cmd(self.router, "/new")
        self.assertEqual(self.sm.current_title, "session_2")

    def test_new_existing_title_rejected(self):
        """Test 1d: /new default 同名已存在 → 回報「已存在」，不覆蓋歷史、不切換"""
        self.sm.switch_session("default")
        self.sm.add_message("user", "保留我")
        self.sm.new_session("other")  # 當前變 other
        msgs = cmd(self.router, "/new", ["default"])
        self.assertEqual(len(msgs), 1)
        text = msgs[0].payload["text"]
        self.assertIn("對話已存在", text)
        self.assertIn("default", text)
        self.assertEqual(self.sm.current_title, "other")
        self.sm.switch_session("default")
        self.assertEqual(
            [m[1] for m in self.sm.get_current_session()["history"]], ["保留我"]
        )

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


if __name__ == "__main__":
    unittest.main()
