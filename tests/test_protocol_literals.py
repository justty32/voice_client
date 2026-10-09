"""產品碼不得以字面字串指定 topic：一律使用 protocol.topics 常數。

掃描 modules/、app_wiring/、app.py，下列寫法若用 str 字面值即失敗：
- emit("...")、register_consumer("...") 的第一個引數
- 任何呼叫的 topic="..." 關鍵字（OutboxAdapter 等；register_producer 的第一個引數是生產者名稱，不是 topic）
- 類別屬性 consumes = ("...", ...)
- message.topic == "..." 比較

執行：python3 -m unittest tests.test_protocol_literals
"""

import ast
import os
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCAN_TARGETS = ("modules", "app_wiring", "app.py")


def _py_files():
    for target in SCAN_TARGETS:
        path = os.path.join(ROOT, target)
        if os.path.isfile(path):
            yield path
            continue
        for dirpath, _dirs, files in os.walk(path):
            if "__pycache__" in dirpath:
                continue
            for f in sorted(files):
                if f.endswith(".py"):
                    yield os.path.join(dirpath, f)


def _is_str(node) -> bool:
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def _call_name(func) -> str:
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def find_topic_literals(tree) -> list[tuple[int, str]]:
    """回傳 [(行號, 說明)]：所有以字面字串指定 topic 的位置。"""
    hits = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name in ("emit", "register_consumer") and node.args and _is_str(node.args[0]):
                hits.append((node.lineno, f"{name}({node.args[0].value!r})"))
            for kw in node.keywords:
                if kw.arg == "topic" and _is_str(kw.value):
                    hits.append((node.lineno, f"{name}(topic={kw.value.value!r})"))
        elif isinstance(node, ast.ClassDef):
            for stmt in node.body:
                if (isinstance(stmt, ast.Assign)
                        and any(isinstance(t, ast.Name) and t.id == "consumes" for t in stmt.targets)
                        and isinstance(stmt.value, (ast.Tuple, ast.List))):
                    for elt in stmt.value.elts:
                        if _is_str(elt):
                            hits.append((stmt.lineno, f"{node.name}.consumes {elt.value!r}"))
        elif isinstance(node, ast.Compare):
            operands = [node.left, *node.comparators]
            if (any(isinstance(o, ast.Attribute) and o.attr == "topic" for o in operands)
                    and any(_is_str(o) for o in operands)):
                hits.append((node.lineno, "比較 .topic 與字面字串"))
    return hits


class TestScannerSelf(unittest.TestCase):
    def test_detects_each_literal_form(self):
        src = (
            "class M:\n"
            "    consumes = ('a', T.B)\n"
            "    def handle(self, message):\n"
            "        if message.topic == 'a':\n"
            "            self.emit('c', 1)\n"
            "        self.emit(T.C, 1)\n"
            "ex.register_consumer('d', x)\n"
            "OutboxAdapter(q, topic='e', source='s')\n"
            "ex.register_producer('producer_name', OutboxAdapter(q, topic=T.E))\n"
        )
        lines = sorted(line for line, _ in find_topic_literals(ast.parse(src)))
        self.assertEqual(lines, [2, 4, 5, 7, 8])


class TestNoTopicLiterals(unittest.TestCase):
    def test_product_code_uses_protocol_constants(self):
        offenders = []
        for path in _py_files():
            with open(path, encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=path)
            rel = os.path.relpath(path, ROOT)
            offenders += [f"{rel}:{line} {desc}" for line, desc in find_topic_literals(tree)]
        self.assertEqual(offenders, [], "改用 protocol.topics 常數：\n" + "\n".join(offenders))


if __name__ == "__main__":
    unittest.main()
