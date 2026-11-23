#!/usr/bin/env python3
"""Validate existing wf indexes; optional argument is the project root."""

import argparse
import json
import os
from pathlib import Path
import subprocess


def ignored_paths(folder, paths):
    if not paths:
        return set()
    result = subprocess.run(
        ["git", "-C", str(folder), "check-ignore", "--no-index", "-z", "--stdin"],
        input="\0".join(str(path) for path in paths) + "\0",
        text=True, capture_output=True,
    )
    if result.returncode not in (0, 1):
        probe = subprocess.run(
            ["git", "-C", str(folder), "rev-parse", "--show-toplevel"],
            text=True, capture_output=True,
        )
        if probe.returncode == 0:
            raise OSError(result.stderr.strip())
        # Standalone trees have no Git ignore context.
        return set()
    return set(result.stdout.split("\0")) - {""}


def valid_description(value):
    if isinstance(value, str):
        return bool(value.strip())
    return (isinstance(value, list) and bool(value)
            and all(isinstance(item, str) and item.strip() for item in value))


def target_exists(value, table):
    if not isinstance(value, str) or not value.strip():
        return False
    filename = value.split("#", 1)[0]
    return (table.parent / filename if filename else table).exists()


def check_table(table, children):
    problems = []
    try:
        data = json.loads(table.read_text(encoding="utf-8"))
    except (ValueError, OSError) as error:
        return [f"invalid JSON: {error}"]
    if not isinstance(data, dict):
        return ["index must be a JSON object"]
    for name in sorted(children - data.keys()):
        problems.append(f"missing entry: {name}")
    for name, entry in data.items():
        if not name or name in (".", "..") or "/" in name:
            problems.append(f"key must be a child name: {name!r}")
        elif not (table.parent / name).exists():
            problems.append(f"entry does not exist: {name}")
        if isinstance(entry, dict) and "$ref" in entry:
            if not target_exists(entry["$ref"], table):
                problems.append(f"{name}: $ref target does not exist or is invalid")
            continue
        description = (entry.get("description") if isinstance(entry, dict)
                       else entry if isinstance(entry, str) else None)
        if not valid_description(description):
            problems.append(f"{name}: description must be a non-empty string or string array")
        if isinstance(entry, dict) and "index" in entry:
            if not target_exists(entry["index"], table):
                problems.append(f"{name}: index target does not exist or is invalid")
    return problems


def check(root):
    root = Path(root).resolve()
    findings = []

    def report(path, reason):
        findings.append(f"INDEX {path}: {' '.join(reason.splitlines())}")

    def walk_error(error):
        report(error.filename, str(error))

    if not (root / "wf").is_dir():
        report(root / "wf", "directory does not exist")
        return findings
    for folder_name, dirs, files in os.walk(root / "wf", onerror=walk_error):
        folder = Path(folder_name)
        try:
            ignored = ignored_paths(folder, [folder / name for name in dirs + files])
        except OSError as error:
            report(folder, str(error))
            dirs[:] = []
            continue

        def included(name):
            return (not name.startswith(".") and name != "__pycache__"
                    and str(folder / name) not in ignored)

        children = {name for name in dirs + files
                    if included(name) and name != "_index.json"}
        dirs[:] = sorted(name for name in dirs if included(name) and name != "archive")
        if "_index.json" in files and str(folder / "_index.json") not in ignored:
            table = folder / "_index.json"
            for reason in check_table(table, children):
                report(table, reason)
    return findings


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("root", nargs="?", default=Path(__file__).resolve().parents[2])
    args = parser.parse_args()
    findings = check(args.root)
    for finding in findings:
        print(finding)
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
