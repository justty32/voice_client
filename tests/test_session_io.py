"""domain.session_io 純函式單元測試（SessionManager 的持久化與格式 helper）。"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from domain import session_io


class TestParseSessionsData(unittest.TestCase):
    def test_new_format(self):
        data = {"last_used_title": "a", "sessions": {"a": {"title": "a"}}}
        self.assertEqual(session_io.parse_sessions_data(data), ({"a": {"title": "a"}}, "a"))

    def test_legacy_format_is_title_keyed_dict(self):
        data = {"a": {"title": "a"}}
        self.assertEqual(session_io.parse_sessions_data(data), (data, None))

    def test_other_types_become_empty(self):
        self.assertEqual(session_io.parse_sessions_data([1, 2]), ({}, None))


class TestResolveSessionPath(unittest.TestCase):
    def test_bare_name_goes_next_to_sessions_file(self):
        path = session_io.resolve_session_path("chat", os.path.join("out", ".sessions.json"))
        self.assertEqual(path, os.path.join("out", "chat.json"))

    def test_path_with_dir_is_kept(self):
        self.assertEqual(session_io.resolve_session_path("x/y.JSON", "out/.s.json"), "x/y.JSON")


class TestFormatHistory(unittest.TestCase):
    def test_empty(self):
        self.assertEqual(session_io.format_history(None), "目前沒有對話歷史。")

    def test_roles(self):
        session = {"title": "t", "history": [["user", "問", ""], ["assistant", "答", ""], ["tool", "x", ""]]}
        self.assertEqual(session_io.format_history(session),
                         "--- 對話歷史: t ---\n用戶說：問\nAI回覆：答\n[tool] x")


if __name__ == "__main__":
    unittest.main()
