"""協定契約測試：protocol.topics、wire() 實際路由、codemap 掃描、docs 表四方一致。

任一方漂移（新增 topic 沒登錄、文件生產者寫錯…）都會讓本檔變紅。

執行：python3 -m unittest tests.test_protocol_contract
"""

import configparser
import importlib.util
import os
import queue
import re
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from app_wiring.topology import wire
from core.exchange import Exchange
from modules.chat_flow import ChatFlow
from modules.cli_text_bridge import CliTextBridge
from modules.command_router import CommandRouter
from modules.stt_gate import SttGate
from modules.workspace_manager import WorkspaceManager
from protocol import payloads as P
from protocol import topics as T
from domain.session_manager import SessionManager

_spec = importlib.util.spec_from_file_location(
    "codemap", os.path.join(ROOT, "workflows", "common", "code-map", "codemap.py"))
codemap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(codemap)

DOCS_TOPICS = os.path.join(ROOT, "docs", "architecture", "topics.md")

# wire() 期望的 legacy queue 鍵名（見 app_wiring/topology.py docstring）
LEGACY_QUEUE_KEYS = (
    "key_signal", "cli_cmd", "cli_text", "recorder_cmd", "audio_out", "audio_in",
    "recorder_event", "stt_out", "stt_event", "http_send", "http_recv", "summary_in",
    "summary_out_q", "tts_input", "tts_cmd", "ui_event_q",
)

# 文件生產者欄的別名 → codemap 識別字
PRODUCER_ALIASES = {
    "ChatFlow": "modules.chat_flow.ChatFlow",
    "SttGate": "modules.stt_gate.SttGate",
    "CommandRouter": "modules.command_router.CommandRouter",
    "CliTextBridge": "modules.cli_text_bridge.CliTextBridge",
    "WorkspaceCommandMixin": "modules.command_handlers.workspace.WorkspaceCommandMixin",
    "Recorder": "app_wiring.topology:recorder",
    "STT": "app_wiring.topology:voice_to_text",
    "HttpClient": "app_wiring.topology:http_client",
    "SummaryGenerator": "app_wiring.topology:summary_generator",
    "熱鍵": "app_wiring.topology:keyboard_listener",
    "終端指令": "app_wiring.topology:terminal_input_cmd",
    "終端文字": "app_wiring.topology:terminal_input_text",
}
# 基底類別的錯誤回報（TunnelModule._run）不列入文件
IGNORED_PRODUCERS = {"core.module.TunnelModule"}

_ROW = re.compile(r"^\|\s*`([a-z_]+)`\s*\|([^|]*)\|")
_PAREN = re.compile(r"（[^）]*）|\([^)]*\)")


def parse_docs_table(text: str) -> dict[str, set[str]]:
    """解析 topics.md 的表格列：{topic: 生產者別名集合}（括號註記略去）。"""
    rows = {}
    for line in text.splitlines():
        m = _ROW.match(line.strip())
        if not m:
            continue
        cell = _PAREN.sub("", m.group(2))
        rows[m.group(1)] = {p.strip() for p in cell.split("、") if p.strip()}
    return rows


def _make_session_manager(tmp: str) -> SessionManager:
    cfg = configparser.ConfigParser()
    cfg["WORKSPACE"] = {
        "sessions_file": os.path.join(tmp, ".sessions.json"),
        "deleted_sessions_dir": os.path.join(tmp, "deleted"),
    }
    return SessionManager(cfg)


def build_wired(tmp: str) -> Exchange:
    """與 tests/test_app_wiring.py 相同方式接線（不啟動任何執行緒）。"""
    sm = _make_session_manager(tmp)
    wm = WorkspaceManager()
    exchange = Exchange()
    wire(
        exchange,
        native_modules={
            "wm": wm,
            "stt_gate": SttGate(),
            "command_router": CommandRouter(wm, sm, tmp),
            "chat_flow": ChatFlow(sm, summary_threshold=20, slm_enabled=False),
            "cli_text_bridge": CliTextBridge(),
        },
        legacy_queues={k: queue.Queue() for k in LEGACY_QUEUE_KEYS},
    )
    return exchange


class TestProtocolContract(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_wire_routes_equal_protocol_all(self):
        exchange = build_wired(self._tmp)
        self.assertEqual(set(exchange.routes()), set(T.ALL))

    def test_codemap_topics_equal_protocol_all(self):
        self.assertEqual(set(codemap.scan()["topics"]), set(T.ALL))

    def test_docs_table_matches_codemap(self):
        with open(DOCS_TOPICS, encoding="utf-8") as f:
            docs = parse_docs_table(f.read())
        self.assertEqual(set(docs), set(T.ALL), "docs 表的 topic 集合與 protocol.topics.ALL 不符")

        scanned = codemap.scan()["topics"]
        for topic in sorted(T.ALL):
            with self.subTest(topic=topic):
                unknown = docs[topic] - set(PRODUCER_ALIASES)
                self.assertFalse(unknown, f"{topic}: 生產者別名未登錄 {unknown}")
                documented = {PRODUCER_ALIASES[a] for a in docs[topic]}
                actual = set(scanned[topic]["producers"]) - IGNORED_PRODUCERS
                self.assertEqual(documented, actual)


class TestPayloadShapes(unittest.TestCase):
    """建構函式必須產出與既有線上格式完全相同的值。"""

    def test_builders_match_wire_format(self):
        cases = [
            (P.ui_status("待機"), {"type": "status", "text": "待機"}),
            (P.ui_message("voice", "hi"), {"type": "message", "role": "voice", "text": "hi"}),
            (P.ui_clear(), {"type": "clear"}),
            (P.command("voice", ("x",)), {"cmd": "voice", "args": ["x"]}),
            (P.command("/list"), {"cmd": "/list", "args": []}),
            (P.recorder_event("error", message="m"), {"event": "error", "message": "m"}),
            (P.recorder_event("recording_stopped", flushed=False),
             {"event": "recording_stopped", "flushed": False}),
            (P.stt_event("stt_error", message="m"), {"event": "stt_error", "message": "m"}),
            (P.stt_event("stt_done"), {"event": "stt_done"}),
            (P.gate_mode("command"), {"mode": "command"}),
            (P.chat_cmd("play_last"), {"cmd": "play_last"}),
            (P.tts_item("t", "high"), {"text": "t", "priority": "high"}),
            (P.summary_request("t", "default"), {"cmd": "summary", "text": "t", "title": "default"}),
            (P.outbound_chat("c", "default", "2026-01-01T00:00:00+00:00"),
             {"Content": "c", "Title": "default",
              "Metadata": {"ClientTime": "2026-01-01T00:00:00+00:00"}}),
        ]
        for got, expected in cases:
            with self.subTest(expected=expected):
                self.assertEqual(got, expected)

    def test_control_strings_unchanged(self):
        self.assertEqual(
            (P.RECORDER_START, P.RECORDER_STOP, P.TTS_STOP_SPEECH, P.TTS_TERMINATE, P.APP_EXIT),
            ("START", "STOP", "STOP_SPEECH", "TERMINATE", "EXIT"),
        )


class TestDocsTableParser(unittest.TestCase):
    def test_strips_annotations_and_splits(self):
        text = (
            "| topic | 生產者 | 消費者 | payload |\n"
            "|---|---|---|---|\n"
            "| `app_ctl` | CommandRouter（/exit）、CliTextBridge（EOF） | app.py | 裸字串 |\n"
        )
        self.assertEqual(parse_docs_table(text), {"app_ctl": {"CommandRouter", "CliTextBridge"}})


if __name__ == "__main__":
    unittest.main()
