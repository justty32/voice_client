"""SessionManager chat 歷史遷移與存取的測試（chat 工作區）。

執行：python3 -m unittest tests.test_session_manager
"""

import configparser
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from session_manager import SessionManager


def make_config(tmp: str) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg["WORKSPACE"] = {
        "sessions_file": os.path.join(tmp, "output", ".sessions.json"),
        "deleted_sessions_dir": os.path.join(tmp, "output", "deleted"),
    }
    return cfg


class SessionManagerTestBase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.cfg = make_config(self._tmp.name)
        self.sessions_file = self.cfg["WORKSPACE"]["sessions_file"]

    def tearDown(self):
        self._tmp.cleanup()

    def write_sessions_file(self, data: dict):
        os.makedirs(os.path.dirname(self.sessions_file), exist_ok=True)
        with open(self.sessions_file, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False)


class TestNewFormat(SessionManagerTestBase):
    def test_add_message_stores_list_entry(self):
        sm = SessionManager(self.cfg)
        sm.new_session("s1")
        sm.add_message("user", "hello")
        sm.add_message("assistant", "world")
        hist = sm.get_current_session()["history"]
        self.assertEqual(len(hist), 2)
        self.assertEqual(hist[0][0], "user")
        self.assertEqual(hist[0][1], "hello")
        self.assertEqual(hist[1][0], "assistant")
        self.assertEqual(hist[1][1], "world")
        # 每筆三欄，第三欄為 timestamp 字串
        self.assertEqual(len(hist[0]), 3)
        self.assertIsInstance(hist[0][2], str)

    def test_get_history_renders(self):
        sm = SessionManager(self.cfg)
        sm.new_session("s1")
        sm.add_message("user", "嗨")
        sm.add_message("assistant", "你好")
        text = sm.get_history()
        self.assertIn("用戶說：嗨", text)
        self.assertIn("AI回覆：你好", text)

    def test_persist_and_reload_keeps_list_format(self):
        sm = SessionManager(self.cfg)
        sm.new_session("s1")
        sm.add_message("user", "持久化")
        # 重新載入
        sm2 = SessionManager(self.cfg)
        sm2.switch_session("s1")
        hist = sm2.get_current_session()["history"]
        self.assertEqual(hist[0][:2], ["user", "持久化"])


class TestMigration(SessionManagerTestBase):
    def test_migrate_dict_history_container_format(self):
        self.write_sessions_file({
            "last_used_title": "default",
            "sessions": {
                "default": {
                    "title": "default",
                    "created_at": "t0",
                    "history": [
                        {"role": "user", "content": "hi", "timestamp": "t1"},
                        {"role": "assistant", "content": "yo", "timestamp": "t2"},
                    ],
                }
            },
        })
        sm = SessionManager(self.cfg)
        hist = sm.get_current_session()["history"]
        self.assertEqual(hist, [["user", "hi", "t1"], ["assistant", "yo", "t2"]])
        # 渲染也要正常
        text = sm.get_history()
        self.assertIn("用戶說：hi", text)
        self.assertIn("AI回覆：yo", text)

    def test_migrate_bare_old_format(self):
        # 舊「直接以 title 為鍵」的格式
        self.write_sessions_file({
            "default": {
                "title": "default",
                "history": [{"role": "user", "content": "x", "timestamp": "t"}],
            }
        })
        sm = SessionManager(self.cfg)
        sm.switch_session("default")
        self.assertEqual(sm.get_current_session()["history"], [["user", "x", "t"]])

    def test_migrate_missing_or_bad_history(self):
        self.write_sessions_file({
            "sessions": {
                "a": {"title": "a"},                    # 無 history
                "b": {"title": "b", "history": "oops"},  # history 非 list
            }
        })
        sm = SessionManager(self.cfg)
        self.assertEqual(sm._sessions["a"]["history"], [])
        self.assertEqual(sm._sessions["b"]["history"], [])

    def test_add_message_after_migration(self):
        self.write_sessions_file({
            "last_used_title": "default",
            "sessions": {
                "default": {
                    "title": "default",
                    "history": [{"role": "user", "content": "old", "timestamp": "t1"}],
                }
            },
        })
        sm = SessionManager(self.cfg)
        sm.add_message("assistant", "new")
        hist = sm.get_current_session()["history"]
        self.assertEqual(hist[0], ["user", "old", "t1"])
        self.assertEqual(hist[1][:2], ["assistant", "new"])


class TestSaveLoadFile(SessionManagerTestBase):
    def test_load_old_format_session_file_migrates(self):
        sm = SessionManager(self.cfg)
        # 手動寫一個舊格式的 session 檔
        path = os.path.join(self._tmp.name, "imported.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({
                "title": "imported",
                "history": [{"role": "user", "content": "c", "timestamp": "t"}],
            }, f, ensure_ascii=False)
        ok, _ = sm.load_session_from_file(path)
        self.assertTrue(ok)
        self.assertEqual(sm.get_current_session()["history"], [["user", "c", "t"]])

    def test_save_then_load_roundtrip(self):
        sm = SessionManager(self.cfg)
        sm.new_session("rt")
        sm.add_message("user", "data")
        ok, msg = sm.save_session_to_file("rt_out")
        self.assertTrue(ok, msg)
        # save 會放到 sessions_file 同目錄
        saved = os.path.join(os.path.dirname(self.sessions_file), "rt_out.json")
        # 用一個獨立、空白的 manager 載入存出的檔（避免同名 session 已存在而被拒）
        cfg2 = make_config(os.path.join(self._tmp.name, "ws2"))
        sm2 = SessionManager(cfg2)
        ok2, msg2 = sm2.load_session_from_file(saved)
        self.assertTrue(ok2, msg2)
        self.assertEqual(sm2.get_current_session()["history"][0][:2], ["user", "data"])


if __name__ == "__main__":
    unittest.main()
