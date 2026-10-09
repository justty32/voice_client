"""SessionManager chat 歷史遷移與存取的測試（chat 工作區）。

執行：python3 -m unittest tests.test_session_manager
"""

import configparser
import json
import os
import sys
import tempfile
import threading
import unittest
from unittest import mock

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


class TestHistoryEdit(SessionManagerTestBase):
    def _seed(self):
        sm = SessionManager(self.cfg)
        sm.new_session("s")
        sm.add_message("user", "m1")
        sm.add_message("assistant", "m2")
        sm.add_message("user", "m3")
        return sm

    def test_delete_message(self):
        sm = self._seed()
        self.assertTrue(sm.delete_message(1))  # 刪除 m2
        hist = sm.get_current_session()["history"]
        self.assertEqual([h[1] for h in hist], ["m1", "m3"])
        self.assertFalse(sm.delete_message(9))

    def test_move_message(self):
        sm = self._seed()
        self.assertTrue(sm.move_message(0, 2))  # m1 移到最後
        hist = sm.get_current_session()["history"]
        self.assertEqual([h[1] for h in hist], ["m2", "m3", "m1"])
        self.assertFalse(sm.move_message(0, 9))

    def test_move_message_to_top_default_last(self):
        sm = self._seed()
        self.assertTrue(sm.move_message_to_top())  # m3 移到最前
        hist = sm.get_current_session()["history"]
        self.assertEqual([h[1] for h in hist], ["m3", "m1", "m2"])

    def test_edit_persists(self):
        sm = self._seed()
        sm.delete_message(0)
        sm2 = SessionManager(self.cfg)
        sm2.switch_session("s")
        hist = sm2.get_current_session()["history"]
        self.assertEqual([h[1] for h in hist], ["m2", "m3"])

    def test_edit_preserves_three_columns(self):
        sm = self._seed()
        sm.move_message(0, 1)
        for h in sm.get_current_session()["history"]:
            self.assertEqual(len(h), 3)



class TestThreadSafetyAndPersistence(SessionManagerTestBase):
    """階段 3：鎖、原子寫入、壞檔備份、深複本（B3、B4）。"""

    def test_concurrent_add_message(self):
        sm = SessionManager(self.cfg)
        sm.new_session("c")

        def worker(tag):
            for i in range(50):
                sm.add_message("user", f"{tag}-{i}")

        threads = [threading.Thread(target=worker, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)
        self.assertEqual(sm.message_count(), 200)
        with open(self.sessions_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(len(data["sessions"]["c"]["history"]), 200)
        leftovers = [n for n in os.listdir(os.path.dirname(self.sessions_file)) if n.endswith(".tmp")]
        self.assertEqual(leftovers, [])

    def test_save_is_atomic_via_replace(self):
        """寫入一律經暫存檔＋os.replace，正式檔不會被直接以 "w" 開啟。"""
        sm = SessionManager(self.cfg)
        real_replace = os.replace
        calls = []

        def spy(src, dst):
            calls.append((src, dst))
            return real_replace(src, dst)

        with mock.patch("session_manager.os.replace", side_effect=spy):
            sm.new_session("a")
        self.assertIn((f"{self.sessions_file}.tmp", self.sessions_file), calls)

    def test_corrupt_file_backed_up(self):
        os.makedirs(os.path.dirname(self.sessions_file), exist_ok=True)
        with open(self.sessions_file, "w", encoding="utf-8") as f:
            f.write("garbage")
        with self.assertLogs("session_manager", level="ERROR"):
            sm = SessionManager(self.cfg)
        self.assertEqual(sm.list_sessions(), [])
        names = os.listdir(os.path.dirname(self.sessions_file))
        backups = [n for n in names if n.startswith(".sessions.json.corrupt-")]
        self.assertEqual(len(backups), 1)
        with open(os.path.join(os.path.dirname(self.sessions_file), backups[0]), encoding="utf-8") as f:
            self.assertEqual(f.read(), "garbage")

    def test_new_session_same_title_rejected(self):
        sm = SessionManager(self.cfg)
        self.assertIsNotNone(sm.new_session("default"))
        sm.add_message("user", "keep")
        sm.new_session("other")
        self.assertIsNone(sm.new_session("default"))
        self.assertEqual(sm.current_title, "other")
        sm.switch_session("default")
        self.assertEqual([m[1] for m in sm.get_current_session()["history"]], ["keep"])

    def test_next_auto_title(self):
        sm = SessionManager(self.cfg)
        self.assertEqual(sm.next_auto_title(), "session_1")
        sm.new_session("session_1")
        sm.new_session("session_3")
        self.assertEqual(sm.next_auto_title(), "session_2")

    def test_get_current_session_returns_copy(self):
        sm = SessionManager(self.cfg)
        sm.new_session("s")
        sm.add_message("user", "x")
        snap = sm.get_current_session()
        snap["history"].append(["user", "injected", "t"])
        snap["title"] = "hacked"
        self.assertEqual(sm.message_count(), 1)
        self.assertEqual(sm.get_current_session()["title"], "s")

if __name__ == "__main__":
    unittest.main()
