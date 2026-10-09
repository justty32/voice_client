"""workflows/common/code-map/codemap.py 掃描器單元測試。

執行：python3 -m unittest tests.test_codemap
"""

import ast
import importlib.util
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_spec = importlib.util.spec_from_file_location(
    "codemap", os.path.join(ROOT, "workflows", "common", "code-map", "codemap.py"))
codemap = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(codemap)


def _scan(src, mod="modules.sample", known=(), is_pkg=False, topic_consts=None):
    sc = codemap._Scanner(mod, set(known) | {mod}, is_pkg, topic_consts)
    sc.visit(ast.parse(src))
    return sc


class TestScanner(unittest.TestCase):
    def test_emit_and_consumes_are_attributed_to_class(self):
        sc = _scan(
            "class Foo:\n"
            "    consumes = ('a', 'b')\n"
            "    def handle(self, m):\n"
            "        self.emit('c', 1)\n"
        )
        self.assertEqual(sorted(sc.consumes),
                         [("a", "modules.sample.Foo"), ("b", "modules.sample.Foo")])
        self.assertEqual(sc.produces, [("c", "modules.sample.Foo")])

    def test_adapters_and_register_consumer(self):
        sc = _scan(
            "def wire(ex, q):\n"
            "    OutboxAdapter(q, topic='audio', source='recorder')\n"
            "    ex.register_consumer('tts', InboxAdapter(q))\n"
        )
        self.assertEqual(sc.produces, [("audio", "modules.sample:recorder")])
        self.assertEqual(sc.consumes, [("tts", "modules.sample:InboxAdapter(q)")])

    def test_protocol_topic_constants_are_resolved(self):
        sc = _scan(
            "from protocol import topics as T\n"
            "from protocol.topics import AUDIO as A\n"
            "class Foo:\n"
            "    consumes = (T.TTS,)\n"
            "    def handle(self, m):\n"
            "        self.emit(T.UI_EVENT, 1)\n"
            "        self.emit(Other.UI_EVENT, 1)\n"
            "def wire(ex, q):\n"
            "    OutboxAdapter(q, topic=A, source='recorder')\n",
            topic_consts={"TTS": "tts", "UI_EVENT": "ui_event", "AUDIO": "audio"},
        )
        self.assertEqual(sc.consumes, [("tts", "modules.sample.Foo")])
        self.assertEqual(sorted(sc.produces),
                         [("audio", "modules.sample:recorder"), ("ui_event", "modules.sample.Foo")])

    def test_load_topic_constants_reads_protocol_file(self):
        consts = codemap.load_topic_constants()
        self.assertEqual(consts["UI_EVENT"], "ui_event")
        self.assertNotIn("ALL", consts)

    def test_imports_resolve_to_known_modules_only(self):
        sc = _scan(
            "import os\n"
            "from core.module import TunnelModule\n"
            "from .helpers import x\n",
            known={"core.module", "modules.helpers"},
        )
        self.assertEqual(sc.imports, {"core.module", "modules.helpers"})

    def test_relative_import_from_package_init(self):
        sc = _scan("from .voice import VoiceMixin\n",
                   mod="modules.command_handlers",
                   known={"modules.command_handlers.voice"}, is_pkg=True)
        self.assertEqual(sc.imports, {"modules.command_handlers.voice"})


class TestScanRepo(unittest.TestCase):
    def test_real_repo_topics_have_both_ends(self):
        data = codemap.scan()
        self.assertIn("app.py", data["files"])
        for topic in ("commands", "raw_text", "stt_text", "ui_event"):
            with self.subTest(topic=topic):
                d = data["topics"][topic]
                self.assertTrue(d["producers"])
                self.assertTrue(d["consumers"])


if __name__ == "__main__":
    unittest.main()
