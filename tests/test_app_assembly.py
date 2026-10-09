"""build_core() 與 app_wiring.settings 的組裝測試（不啟動任何執行緒、不需硬體）。

執行：python3 -m unittest tests.test_app_assembly
"""

import configparser
import os
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app_wiring.assembly import LEGACY_QUEUE_KEYS, NATIVE_KEYS, CoreParts, build_core
from app_wiring.settings import ensure_default_session, export_dir_from, slm_settings
from core.exchange import Exchange
from protocol import topics as T
from domain.session_manager import SessionManager


def _make_config(tmp: str) -> configparser.ConfigParser:
    cfg = configparser.ConfigParser()
    cfg["WORKSPACE"] = {
        "sessions_file": os.path.join(tmp, ".sessions.json"),
        "deleted_sessions_dir": os.path.join(tmp, "deleted"),
        "export_file": os.path.join(tmp, "out", "export.json"),
    }
    cfg["SLM"] = {"summary_threshold": "7", "enabled": "false"}
    return cfg


def _topology_queue_keys() -> set:
    """wire() 實際讀取的 legacy queue 鍵名（解析 topology.py 的 lq["..."]）。"""
    with open(os.path.join(ROOT, "app_wiring", "topology.py"), encoding="utf-8") as fh:
        return set(re.findall(r'lq\["(\w+)"\]', fh.read()))


class _FakeSessionManager:
    """記錄 switch_session／new_session 呼叫的替身。"""

    def __init__(self, current=None, existing=()):
        self.current_title = current
        self._existing = set(existing)
        self.calls = []

    def switch_session(self, title):
        self.calls.append(("switch", title))
        if title in self._existing:
            self.current_title = title
            return True
        return False

    def new_session(self, title):
        self.calls.append(("new", title))
        self.current_title = title
        return True


class TestBuildCore(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.config = _make_config(self._tmp)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_routes_equal_protocol_all(self):
        parts = build_core(self.config)
        self.assertIsInstance(parts, CoreParts)
        self.assertEqual(set(parts.exchange.routes()), set(T.ALL))

    def test_queue_keys_match_wire(self):
        parts = build_core(self.config)
        self.assertEqual(set(parts.queues), _topology_queue_keys())
        self.assertEqual(set(parts.queues), set(LEGACY_QUEUE_KEYS))
        self.assertIn("stt_event", parts.queues)

    def test_native_modules_and_settings_applied(self):
        parts = build_core(self.config)
        self.assertEqual(tuple(parts.native), NATIVE_KEYS)
        self.assertEqual(parts.export_dir, os.path.join(self._tmp, "out"))
        router = parts.native["command_router"]
        self.assertIs(router._wm, parts.native["wm"])
        self.assertEqual(router._export_dir, parts.export_dir)
        chat = parts.native["chat_flow"]
        self.assertEqual((chat._summary_threshold, chat._slm_enabled), (7, False))
        self.assertEqual(parts.session_manager.current_title, "default")

    def test_injected_session_manager_and_exchange_are_used(self):
        sm = SessionManager(self.config)
        ex = Exchange(idle_sleep=0.001)
        parts = build_core(self.config, session_manager=sm, exchange=ex)
        self.assertIs(parts.session_manager, sm)
        self.assertIs(parts.exchange, ex)
        self.assertEqual(sm.current_title, "default")

    def test_does_not_import_hardware_or_network_modules(self):
        code = textwrap.dedent(f"""
            import sys
            sys.path.insert(0, {ROOT!r})
            import configparser
            from app_wiring.assembly import build_core
            cfg = configparser.ConfigParser()
            cfg["WORKSPACE"] = {{
                "sessions_file": {os.path.join(self._tmp, "s.json")!r},
                "deleted_sessions_dir": {os.path.join(self._tmp, "d")!r},
            }}
            build_core(cfg)
            heavy = ("speech.record", "llm.http_client", "speech.voice_to_text", "speech.text_to_voice",
                     "llm.summary_generator", "ui.keyboard_listener", "pyaudio", "requests")
            print(",".join(m for m in heavy if m in sys.modules))
        """)
        out = subprocess.run([sys.executable, "-c", code], capture_output=True,
                             text=True, check=True, cwd=self._tmp)
        self.assertEqual(out.stdout.strip(), "")


class TestBuildCoreEdgeInjection(unittest.TestCase):
    """階段 7b：手機入口用的 queues／clipboard／ui_event_transform 注入（預設值維持桌面行為）。"""

    def setUp(self):
        self._tmp = tempfile.mkdtemp()
        self.config = _make_config(self._tmp)

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def _deliver_ui(self, parts, payload):
        from core.message import Message
        parts.exchange._routes[T.UI_EVENT].put_nowait(Message(T.UI_EVENT, payload))

    def test_default_ui_event_is_transformed(self):
        parts = build_core(self.config)
        self._deliver_ui(parts, {"type": "status", "text": "待機"})
        item = parts.queues["ui_event_q"].get_nowait()
        self.assertEqual((item.event_type, item.data), ("status", "待機"))
        self.assertIsNone(parts.native["command_router"]._clipboard)

    def test_overrides_clipboard_and_raw_ui_events(self):
        import queue as _queue
        sink = _queue.Queue()
        clip = object()
        parts = build_core(self.config, queues={"ui_event_q": sink}, clipboard=clip,
                           ui_event_transform=None)
        self.assertIs(parts.queues["ui_event_q"], sink)
        self.assertIs(parts.native["command_router"]._clipboard, clip)
        self._deliver_ui(parts, {"type": "status", "text": "待機"})
        self.assertEqual(sink.get_nowait(), {"type": "status", "text": "待機"})
        self.assertEqual(set(parts.exchange.routes()), set(T.ALL))

    def test_unknown_queue_key_rejected(self):
        with self.assertRaises(ValueError):
            build_core(self.config, queues={"nope": object()})


class TestSettings(unittest.TestCase):
    def test_ensure_default_creates_when_missing(self):
        sm = _FakeSessionManager()
        ensure_default_session(sm)
        self.assertEqual(sm.calls, [("switch", "default"), ("new", "default")])
        self.assertEqual(sm.current_title, "default")

    def test_ensure_default_switches_when_exists(self):
        sm = _FakeSessionManager(existing={"default"})
        ensure_default_session(sm)
        self.assertEqual(sm.calls, [("switch", "default")])

    def test_ensure_default_noop_with_current(self):
        sm = _FakeSessionManager(current="工作")
        ensure_default_session(sm)
        self.assertEqual(sm.calls, [])
        self.assertEqual(sm.current_title, "工作")

    def test_export_dir(self):
        cfg = configparser.ConfigParser()
        self.assertEqual(export_dir_from(cfg), "output")
        cfg["WORKSPACE"] = {"export_file": "export.json"}
        self.assertEqual(export_dir_from(cfg), ".")
        cfg["WORKSPACE"] = {"export_file": "/a/b/x.json"}
        self.assertEqual(export_dir_from(cfg), "/a/b")

    def test_slm_settings(self):
        cfg = configparser.ConfigParser()
        self.assertEqual(slm_settings(cfg), (20, True))
        cfg["SLM"] = {"summary_threshold": "5", "enabled": "false"}
        self.assertEqual(slm_settings(cfg), (5, False))


if __name__ == "__main__":
    unittest.main()
