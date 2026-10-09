"""手機入口的 Data Tunnel 接線測試（階段 7b）：不需 fastapi、不啟動執行緒、不寫 repo 的 output/。

執行：python3 -m unittest tests.test_mobile_wiring
"""

import ast
import os
import queue
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from core.message import Message  # noqa: E402
from mobile.edge import BrowserClipboard, EdgeSink  # noqa: E402
from mobile.state import autosave_buffer, build_mobile_state  # noqa: E402
from protocol import payloads as P  # noqa: E402
from protocol import topics as T  # noqa: E402
from tests._mobile_fakes import make_state  # noqa: E402

_LEGACY = ("text_accumulator", "workspace_controller")


class TestMobileStateUsesBuildCore(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.state = make_state(self._tmp.name)

    def tearDown(self):
        self._tmp.cleanup()

    def test_routes_equal_protocol_all(self):
        self.assertEqual(set(self.state.parts.exchange.routes()), set(T.ALL))

    def test_no_legacy_attributes(self):
        for name in ("text_accumulator", "wsc", "acc_input_queue", "acc_cmd_queue",
                     "acc_output_queue"):
            self.assertFalse(hasattr(self.state, name), name)

    def test_lifecycle_order(self):
        self.assertEqual(self.state.lifecycle.names(), [
            "voice_to_text", "summary_generator", "http_client",
            "wm", "stt_gate", "command_router", "chat_flow", "cli_text_bridge",
            "exchange",
        ])

    def test_edge_queues_and_clipboard_injected(self):
        q = self.state.parts.queues
        for key in ("ui_event_q", "tts_input", "tts_cmd", "recorder_cmd"):
            self.assertIsInstance(q[key], EdgeSink, key)
        self.assertIsInstance(self.state.parts.native["command_router"]._clipboard,
                              BrowserClipboard)
        self.assertIs(self.state.session_manager, self.state.parts.session_manager)

    def _deliver(self, topic, payload):
        self.state.parts.exchange._routes[topic].put_nowait(Message(topic, payload))

    def test_edge_converts_in_delivery_order(self):
        self._deliver(T.UI_EVENT, P.ui_message("assistant", "答"))
        self._deliver(T.TTS, P.tts_item("答", "medium"))
        self._deliver(T.TTS_CTL, P.TTS_STOP_SPEECH)
        self._deliver(T.TTS_CTL, P.TTS_TERMINATE)
        self._deliver(T.RECORDER_CTL, P.RECORDER_START)
        self._deliver(T.UI_EVENT, P.ui_status("待機"))
        out = []
        while True:
            try:
                out.append(self.state.ui_event_queue.get_nowait())
            except queue.Empty:
                break
        self.assertEqual(out, [
            {"type": "message", "role": "assistant", "text": "答"},
            {"type": "tts", "text": "答", "priority": "medium"},
            {"type": "tts_control", "action": "stop"},
            {"type": "status", "text": "待機"},
        ])

    def test_browser_clipboard(self):
        clip = BrowserClipboard(self.state.ui_event_queue)
        self.assertEqual(clip.copy("字"), (True, ""))
        self.assertEqual(clip.paste(), (False, BrowserClipboard.WAITING))
        self.assertEqual(self.state.ui_event_queue.get_nowait(),
                         {"type": "clipboard_write", "text": "字"})
        self.assertEqual(self.state.ui_event_queue.get_nowait(), {"type": "clipboard_read"})


class TestAutosaveBuffer(unittest.TestCase):
    """D10：停機匯出 buffer 到 <export_dir>/_buffer_temp.json。"""

    def test_exports_only_when_nonempty(self):
        with tempfile.TemporaryDirectory() as tmp:
            state = make_state(tmp)
            self.assertIsNone(autosave_buffer(state))
            state.wm.get("buffer").append("留著")
            path = autosave_buffer(state)
            self.assertEqual(path, os.path.join(state.export_dir, "_buffer_temp.json"))
            self.assertTrue(path.startswith(tmp))
            self.assertTrue(os.path.exists(path))


class TestNoLegacyImports(unittest.TestCase):
    """產品碼（手機入口）不得匯入 text_accumulator／workspace_controller（D4）。"""

    def test_mobile_sources_do_not_import_legacy(self):
        files = [os.path.join(ROOT, "mobile_server.py")]
        mobile_dir = os.path.join(ROOT, "mobile")
        files += [os.path.join(mobile_dir, f) for f in sorted(os.listdir(mobile_dir))
                  if f.endswith(".py")]
        for path in files:
            with open(path, encoding="utf-8") as fh:
                tree = ast.parse(fh.read())
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [a.name for a in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                for name in names:
                    self.assertNotIn(name.split(".")[0], _LEGACY, f"{path}: {name}")

    def test_build_mobile_state_signature_unchanged(self):
        import inspect
        params = inspect.signature(build_mobile_state).parameters
        self.assertEqual(list(params), ["config", "voice_to_text_cls", "http_client_cls",
                                        "summary_cls", "setup_logging"])


if __name__ == "__main__":
    unittest.main()
