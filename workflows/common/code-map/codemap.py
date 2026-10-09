#!/usr/bin/env python3
"""codemap — 以 AST 自動掃描專案，產生／查詢機器可讀的程式碼地圖。

人工維護的導航在 CODE_MAP.md；本工具每次即時掃描、不留產物，所以不會過期。
掃描內容：每個 .py 的行數、docstring 首行、頂層類別／函式、
專案內 import 依賴，以及 Data Tunnel topic 的生產者／消費者
（topic 可為字面字串或 protocol/topics.py 的常數）。

用法（在 repo 根目錄）：
  python workflows/common/code-map/codemap.py            # 總覽：各檔行數＋docstring
  python workflows/common/code-map/codemap.py json       # 完整地圖（JSON）輸出到 stdout
  python workflows/common/code-map/codemap.py big [N]    # 列出超過 N 行（預設 300）的檔
  python workflows/common/code-map/codemap.py topics     # topic 生產者 → 消費者表
  python workflows/common/code-map/codemap.py deps MOD   # MOD 匯入誰、被誰匯入
  python workflows/common/code-map/codemap.py show PATH  # 單檔摘要
"""

import argparse
import ast
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
EXCLUDE_PREFIXES = ("server_sample/", "wf/", "workflows/")
TOPICS_MODULE = "protocol.topics"  # topic 常數的單一來源；掃描時解析其常數


def load_topic_constants(path: Path | None = None) -> dict[str, str]:
    """讀 protocol/topics.py 的頂層 `NAME = "字串"` 指派，回傳 {NAME: 值}。"""
    path = path or ROOT / "protocol" / "topics.py"
    if not path.is_file():
        return {}
    consts = {}
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)
                and (v := _str_const(node.value)) is not None):
            consts[node.targets[0].id] = v
    return consts


def list_py_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "*.py"],
        cwd=ROOT, capture_output=True, text=True, check=True,
    ).stdout.split()
    return sorted(p for p in out
                  if not p.startswith(EXCLUDE_PREFIXES) and (ROOT / p).is_file())


def module_name(path: str) -> str:
    mod = path[:-3].replace("/", ".")
    return mod[:-9] if mod.endswith(".__init__") else mod


def _str_const(node) -> str | None:
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _call_name(func) -> str:
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


class _Scanner(ast.NodeVisitor):
    """收集 import 與 topic 使用；以最近的類別（或模組）作為 topic 的擁有者。"""

    def __init__(self, mod: str, known: set[str], is_pkg: bool = False,
                 topic_consts: dict[str, str] | None = None):
        self.mod = mod
        self.is_pkg = is_pkg
        self.known = known
        self.topic_consts = topic_consts or {}
        self._topic_mod_aliases: set[str] = set()     # `from protocol import topics as T` 的 T
        self._topic_name_aliases: dict[str, str] = {}  # `from protocol.topics import TTS as X` 的 X→TTS
        self.imports: set[str] = set()
        self.produces: list[tuple[str, str]] = []  # (topic, owner)
        self.consumes: list[tuple[str, str]] = []
        self._owner = [mod]

    def _resolve(self, name: str) -> str | None:
        parts = name.split(".")
        for i in range(len(parts), 0, -1):
            cand = ".".join(parts[:i])
            if cand in self.known:
                return cand
        return None

    def _topic(self, node) -> str | None:
        """topic 引數 → 字串：字面值，或 protocol.topics 常數（T.TTS／TTS）。"""
        if (t := _str_const(node)) is not None:
            return t
        if (isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name)
                and node.value.id in self._topic_mod_aliases):
            return self.topic_consts.get(node.attr)
        if isinstance(node, ast.Name) and node.id in self._topic_name_aliases:
            return self.topic_consts.get(self._topic_name_aliases[node.id])
        return None

    def visit_Import(self, node):
        for alias in node.names:
            if (m := self._resolve(alias.name)):
                self.imports.add(m)
            if alias.name == TOPICS_MODULE and alias.asname:
                self._topic_mod_aliases.add(alias.asname)

    def visit_ImportFrom(self, node):
        base = node.module or ""
        if node.level:
            pkg = self.mod.split(".")
            # 相對 import 的起點：套件 __init__ 是自己，一般模組是其所在套件
            pkg = pkg[: len(pkg) - node.level + (1 if self.is_pkg else 0)]
            base = ".".join(pkg + ([base] if base else []))
        for alias in node.names:
            m = self._resolve(f"{base}.{alias.name}") or self._resolve(base)
            if m:
                self.imports.add(m)
            local = alias.asname or alias.name
            if f"{base}.{alias.name}" == TOPICS_MODULE:
                self._topic_mod_aliases.add(local)
            elif base == TOPICS_MODULE:
                self._topic_name_aliases[local] = alias.name

    def visit_ClassDef(self, node):
        owner = f"{self.mod}.{node.name}"
        for stmt in node.body:
            if (isinstance(stmt, ast.Assign) and len(stmt.targets) == 1
                    and isinstance(stmt.targets[0], ast.Name)
                    and stmt.targets[0].id == "consumes"
                    and isinstance(stmt.value, (ast.Tuple, ast.List))):
                for elt in stmt.value.elts:
                    if (t := self._topic(elt)):
                        self.consumes.append((t, owner))
        self._owner.append(owner)
        self.generic_visit(node)
        self._owner.pop()

    def visit_Call(self, node):
        name = _call_name(node.func)
        owner = self._owner[-1]
        if name == "emit" and node.args and (t := self._topic(node.args[0])):
            self.produces.append((t, owner))
        elif name == "register_consumer" and len(node.args) >= 2 and (t := self._topic(node.args[0])):
            target = node.args[1]
            label = _call_name(target.func) if isinstance(target, ast.Call) else ast.unparse(target)
            if isinstance(target, ast.Call) and target.args:
                label += f"({ast.unparse(target.args[0])})"
            self.consumes.append((t, f"{owner}:{label}"))
        elif name in ("OutboxAdapter", "InboxAdapter"):
            kw = {k.arg: k.value for k in node.keywords}
            topic = self._topic(kw["topic"]) if "topic" in kw else None
            if topic:
                label = _str_const(kw.get("source")) or name
                pair = (topic, f"{owner}:{label}")
                (self.produces if name == "OutboxAdapter" else self.consumes).append(pair)
        self.generic_visit(node)


def scan() -> dict:
    files = list_py_files()
    known = {module_name(p) for p in files}
    topic_consts = load_topic_constants()
    entries, topics = {}, {}
    for path in files:
        src = (ROOT / path).read_text(encoding="utf-8")
        try:
            tree = ast.parse(src, filename=path)
        except SyntaxError as exc:
            entries[path] = {"error": str(exc)}
            continue
        mod = module_name(path)
        sc = _Scanner(mod, known, path.endswith("__init__.py"), topic_consts)
        sc.visit(tree)
        doc = ast.get_docstring(tree) or ""
        entries[path] = {
            "module": mod,
            "lines": src.count("\n") + (0 if src.endswith("\n") or not src else 1),
            "doc": doc.strip().splitlines()[0] if doc.strip() else "",
            "classes": [n.name for n in tree.body if isinstance(n, ast.ClassDef)],
            "functions": [n.name for n in tree.body
                          if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))],
            "imports": sorted(sc.imports - {mod}),
        }
        if path.startswith("tests/"):
            continue  # 測試的假 topic 不進 topic 表，避免雜訊
        for topic, owner in sc.produces:
            topics.setdefault(topic, {"producers": set(), "consumers": set()})["producers"].add(owner)
        for topic, owner in sc.consumes:
            topics.setdefault(topic, {"producers": set(), "consumers": set()})["consumers"].add(owner)
    imported_by: dict[str, set[str]] = {}
    for path, e in entries.items():
        for dep in e.get("imports", []):
            imported_by.setdefault(dep, set()).add(e["module"])
    for e in entries.values():
        if "module" in e:
            e["imported_by"] = sorted(imported_by.get(e["module"], ()))
    return {
        "files": entries,
        "topics": {t: {k: sorted(v) for k, v in d.items()} for t, d in sorted(topics.items())},
    }


def cmd_overview(data) -> int:
    for p, e in data["files"].items():
        if p.startswith("tests/"):
            continue
        print(f"{e.get('lines', 0):5d}  {p:42s} {e.get('doc') or e.get('error', '')}")
    return 0


def cmd_big(data, limit: int) -> int:
    rows = sorted(((e["lines"], p) for p, e in data["files"].items()
                   if e.get("lines", 0) > limit), reverse=True)
    for n, p in rows:
        print(f"{n:5d}  {p}")
    return 0


def cmd_topics(data) -> int:
    for topic, d in data["topics"].items():
        flag = "" if d["producers"] and d["consumers"] else "  ⚠"
        print(f"{topic}{flag}")
        print(f"  ← {', '.join(d['producers']) or '(無生產者)'}")
        print(f"  → {', '.join(d['consumers']) or '(無消費者)'}")
    return 0


def _find(data, key: str):
    for p, e in data["files"].items():
        if key in (p, e.get("module")):
            return p, e
    sys.exit(f"找不到模組：{key}")


def cmd_deps(data, key: str) -> int:
    p, e = _find(data, key)
    print(f"{p}")
    print(f"  imports:     {', '.join(e['imports']) or '-'}")
    print(f"  imported_by: {', '.join(e['imported_by']) or '-'}")
    return 0


def cmd_show(data, key: str) -> int:
    p, e = _find(data, key)
    print(f"{p}  ({e['lines']} 行)  {e['doc']}")
    for k in ("classes", "functions", "imports", "imported_by"):
        print(f"  {k}: {', '.join(e[k]) or '-'}")
    owned = [t for t, d in data["topics"].items()
             if any(o.startswith(e["module"] + ".") or o.startswith(e["module"] + ":")
                    or o == e["module"] for o in d["producers"] + d["consumers"])]
    print(f"  topics: {', '.join(owned) or '-'}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd")
    sub.add_parser("json")
    b = sub.add_parser("big"); b.add_argument("limit", nargs="?", type=int, default=300)
    sub.add_parser("topics")
    d = sub.add_parser("deps"); d.add_argument("module")
    s = sub.add_parser("show"); s.add_argument("path")
    args = ap.parse_args(argv)

    data = scan()
    if args.cmd == "json":
        print(json.dumps(data, ensure_ascii=False, indent=1))
        return 0
    if args.cmd == "big":
        return cmd_big(data, args.limit)
    if args.cmd == "topics":
        return cmd_topics(data)
    if args.cmd == "deps":
        return cmd_deps(data, args.module)
    if args.cmd == "show":
        return cmd_show(data, args.path)
    return cmd_overview(data)


if __name__ == "__main__":
    sys.exit(main())
