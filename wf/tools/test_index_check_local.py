"""Temporary-tree tests for the project-owned index checker."""

import json
from pathlib import Path
import subprocess

import pytest

from index_check_local import check


@pytest.fixture
def tree(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "wf").mkdir()
    return tmp_path


def table(tree, data):
    path = tree / "wf/_index.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


def test_valid_forms(tree):
    (tree / "wf/a.md").touch()
    (tree / "wf/b.md").touch()
    (tree / "wf/sub").mkdir()
    table(tree, {"a.md": "A", "b.md": {"description": ["B", "use B"],
           "index": "a.md#/_index"}, "sub": {"$ref": "a.md#/anything"}})
    assert check(tree) == []


@pytest.mark.parametrize("data, expected", [
    ({}, "missing entry: a.md"),
    ({"a.md": "A", "ghost": "G"}, "entry does not exist: ghost"),
    ({"a.md": ""}, "description must"),
    ({"a.md": ["not an entry object"]}, "description must"),
    ({"a.md": {"description": []}}, "description must"),
    ({"a.md": {"description": ["ok", " "]}}, "description must"),
    ({"a.md": {"description": [1]}}, "description must"),
    ({"a.md": {"description": "A", "index": "missing#/x"}}, "index target"),
    ({"a.md": {"description": "A", "index": 1}}, "index target"),
    ({"a.md": {"$ref": "missing"}}, "$ref target"),
    ({"a.md": {"$ref": None}}, "$ref target"),
    ([], "JSON object"),
    ({"a.md": "A", "sub/": "S"}, "child name"),
])
def test_invalid_entries(tree, data, expected):
    (tree / "wf/a.md").touch()
    table(tree, data)
    findings = check(tree)
    assert any(expected in line for line in findings)
    assert all(line.startswith("INDEX ") for line in findings)


def test_bad_json(tree):
    table(tree, {}).write_text("{bad", encoding="utf-8")
    assert "invalid JSON" in check(tree)[0]


def test_skipped_trees_and_gitignore_negation(tree):
    (tree / ".gitignore").write_text("wf/ignored/\n*.tmp\n!keep.tmp\n", encoding="utf-8")
    for name in ("archive", "__pycache__", ".hidden", "ignored"):
        folder = tree / "wf" / name
        folder.mkdir()
        (folder / "_index.json").write_text("bad", encoding="utf-8")
    (tree / "wf/drop.tmp").touch()
    (tree / "wf/keep.tmp").touch()
    table(tree, {"archive": "Archive", "keep.tmp": "Keep"})
    assert check(tree) == []


def test_nested_index_and_no_index_requirement(tree):
    (tree / "wf/sub").mkdir()
    (tree / "wf/sub/a.md").touch()
    assert check(tree) == []
    (tree / "wf/sub/_index.json").write_text("{}", encoding="utf-8")
    assert "missing entry: a.md" in check(tree)[0]


def test_fragment_only_target(tree):
    (tree / "wf/a.md").touch()
    table(tree, {"a.md": {"description": "A", "index": "#/_index"}})
    assert check(tree) == []


def test_hook_exit_status_and_output(tree):
    hook = Path(__file__).with_name("wf-lint-local.sh")
    table(tree, {})
    result = subprocess.run(["bash", str(hook), str(tree), "1"], capture_output=True, text=True)
    assert result.returncode == 0
    (tree / "wf/missing.md").touch()
    result = subprocess.run(["bash", str(hook), str(tree), "0"], capture_output=True, text=True)
    assert result.returncode == 1
    assert result.stdout.startswith("INDEX ")


def test_missing_wf(tree):
    assert "directory does not exist" in check(tree / "absent")[0]
