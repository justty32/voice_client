"""protocol.commands 契約測試：指令集 == 派發表鍵 == /help 內容 == 使用手冊。

鎖住「斜線指令與熱鍵訊號只有一份定義」：terminal_input、local_control、
keyboard_listener、CommandRouter 皆取自 protocol/commands.py。

執行：python3 -m unittest tests.test_protocol_commands
"""

import configparser
import os
import re
import sys
import tempfile
import unittest
from queue import Queue
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ui import keyboard_listener
from ui import local_control
from ui import terminal_input
from core.message import Message
from modules import command_router
from modules.command_router import CommandRouter
from modules.workspace_manager import WorkspaceManager
from protocol.commands import (
    HOTKEY_SIGNALS,
    HOTKEY_TO_CMD,
    SESSION_COMMANDS,
    SLASH_COMMANDS,
)
from tests._helpers import drain
from tests._router_helpers import cmd, make_router, ui_texts

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class TestCommandSets(unittest.TestCase):
    """常數本身的一致性。"""

    def test_slash_commands_count(self):
        self.assertEqual(len(SLASH_COMMANDS), 23)
        self.assertTrue(all(c.startswith("/") for c in SLASH_COMMANDS))

    def test_session_commands_subset_of_slash(self):
        self.assertLessEqual(SESSION_COMMANDS, SLASH_COMMANDS)
        self.assertEqual(len(SESSION_COMMANDS), 8)

    def test_hotkey_to_cmd_keys_equal_signals(self):
        self.assertEqual(set(HOTKEY_TO_CMD), set(HOTKEY_SIGNALS))
        self.assertEqual(len(HOTKEY_SIGNALS), 5)


class TestSingleSource(unittest.TestCase):
    """各使用端引用同一份常數，不再自帶副本。"""

    def test_terminal_input_uses_shared_set(self):
        self.assertIs(terminal_input._SLASH_COMMANDS, SLASH_COMMANDS)

    def test_local_control_allow_list(self):
        self.assertEqual(local_control.ALLOWED_COMMANDS, HOTKEY_SIGNALS)

    def test_command_router_hotkey_map(self):
        self.assertIs(command_router._STR_TO_CMD, HOTKEY_TO_CMD)

    def test_keyboard_listener_emits_only_hotkey_signals(self):
        cfg = configparser.ConfigParser()
        cfg["CONTROL"] = {}
        q = Queue()
        kl = keyboard_listener.KeyboardListener(cfg, q)
        for key in ("f8", "f7", "f9", "f10", "f6"):
            kl._on_press(SimpleNamespace(name=key))
        emitted = [q.get_nowait() for _ in range(q.qsize())]
        self.assertEqual(set(emitted), set(HOTKEY_SIGNALS))
        self.assertEqual(len(emitted), 5)


class TestDispatchTable(unittest.TestCase):
    """CommandRouter 派發表涵蓋全部指令。"""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.router, self.wm, self.sm = make_router(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_handlers_cover_all_commands(self):
        expected = SLASH_COMMANDS | set(HOTKEY_TO_CMD.values()) | {"voice", "unknown"}
        self.assertLessEqual(expected, set(self.router._handlers))

    def test_help_mentions_every_slash_command(self):
        texts = ui_texts(cmd(self.router, "/help"))
        self.assertEqual(len(texts), 1)
        tokens = set(re.findall(r"/\w+", texts[0]))
        self.assertEqual(tokens, set(SLASH_COMMANDS))

    def test_unlisted_cmd_reports_unknown(self):
        self.assertEqual(ui_texts(cmd(self.router, "/nope")), ["未知指令: /nope"])

    def test_non_string_cmd_reports_unknown(self):
        # 舊 if/elif 鏈對非字串 cmd 落到 else；派發表須保持同一訊息而非 TypeError
        self.router.handle(Message(topic="commands", payload={"cmd": ["x"]}))
        self.assertEqual(ui_texts(drain(self.router)), ["未知指令: ['x']"])

    def test_session_commands_without_session_manager(self):
        router = CommandRouter(workspace_manager=WorkspaceManager(), session_manager=None)
        for name in sorted(SESSION_COMMANDS):
            with self.subTest(cmd=name):
                self.assertEqual(ui_texts(cmd(router, name)), ["[系統] 對話管理功能尚未接入。"])


class TestUserManualTable(unittest.TestCase):
    """docs/user_manual/commands.md §6 的三張表合起來 == SLASH_COMMANDS。"""

    def test_manual_slash_tables_match(self):
        path = os.path.join(ROOT, "docs", "user_manual", "commands.md")
        with open(path, encoding="utf-8") as f:
            text = f.read()
        section = text.split("## 6.", 1)[1].split("\n## ", 1)[0]
        documented = set()
        for line in section.splitlines():
            if line.startswith("| `/"):
                first_cell = line.split("|")[1]
                documented.update(re.findall(r"`(/\w+)", first_cell))
        self.assertEqual(documented, set(SLASH_COMMANDS))


if __name__ == "__main__":
    unittest.main()
