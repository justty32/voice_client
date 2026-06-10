"""
workspace.py — 統一的工作區抽象。

一個 Workspace 是「有序的 entry 清單」，每個 entry 是「字串清單」（即 List[List[str]]）。
系統的三個工作區共用這個抽象與其 CRUD 操作：
  - raw STT：每個 entry 是一次語音辨識的逐段文字。
  - buffer ：每個 entry 是一筆待送暫存（一行文字或一段語音）。
  - chat   ：每個 entry 是一則訊息 [role, content, timestamp]。

設計原則：
  - 對外一律以 list[str] 作為 entry；傳入單一 str 會被正規化為單元素 entry [str]。
  - 讀取一律回傳複本，避免外部直接竄改內部狀態。
  - 序列化格式即為 List[List[str]]，與舊的扁平 List[str] 相容（載入時自動升級）。
"""

from __future__ import annotations

import json
import os
from typing import Iterable


def resolve_filename(filename: str, base_dir: str) -> str:
    """把使用者輸入的檔名正規化：補預設 .json 副檔名；若為純檔名則置於 base_dir 下。

    供各工作區的 /export、/import 共用，確保路徑解析行為一致。
    """
    if "." not in filename:
        filename += ".json"
    if os.sep not in filename and "/" not in filename and "\\" not in filename:
        return os.path.join(base_dir if base_dir else ".", filename)
    return filename


class Workspace:
    """有序的 entry 清單，每個 entry 為 list[str]。提供標準 CRUD、重排與匯出入。"""

    def __init__(self, name: str, entries: Iterable | None = None):
        self.name = name
        self._entries: list[list[str]] = []
        if entries:
            for e in entries:
                self._entries.append(self._coerce(e))

    @staticmethod
    def _coerce(entry) -> list[str]:
        """把輸入正規化為 list[str]：str → [str]；其它可迭代物 → 逐項轉 str。"""
        if isinstance(entry, str):
            return [entry]
        if isinstance(entry, Iterable):
            return [str(s) for s in entry]
        return [str(entry)]

    # ── Create ──────────────────────────────────────────────────────────
    def append(self, entry) -> int:
        """新增一個 entry，回傳其索引。"""
        self._entries.append(self._coerce(entry))
        return len(self._entries) - 1

    def extend(self, entries: Iterable) -> int:
        """逐一新增多個 entry，回傳新增筆數。"""
        added = 0
        for e in entries:
            self.append(e)
            added += 1
        return added

    # ── Read ────────────────────────────────────────────────────────────
    def read_all(self) -> list[list[str]]:
        return [list(e) for e in self._entries]

    def read(self, idx: int) -> list[str] | None:
        if 0 <= idx < len(self._entries):
            return list(self._entries[idx])
        return None

    def count(self) -> int:
        return len(self._entries)

    def is_empty(self) -> bool:
        return not self._entries

    # ── Update ──────────────────────────────────────────────────────────
    def replace(self, idx: int, entry) -> bool:
        if 0 <= idx < len(self._entries):
            self._entries[idx] = self._coerce(entry)
            return True
        return False

    def concat_all(self, seg_sep: str = " ") -> bool:
        """把所有 entry 的所有字串攤平、以 seg_sep 串成單一字串，壓縮為單一 entry。

        對應舊 buffer 的 /concat：[["a"],["b"]] → [["a b"]]。
        """
        if not self._entries:
            return False
        flat = [s for entry in self._entries for s in entry]
        self._entries = [[seg_sep.join(flat)]]
        return True

    def move(self, src: int, dst: int) -> bool:
        """把索引 src 的 entry 移動到索引 dst。"""
        n = len(self._entries)
        if not (0 <= src < n) or not (0 <= dst < n):
            return False
        entry = self._entries.pop(src)
        self._entries.insert(dst, entry)
        return True

    def move_to_top(self, idx: int = -1) -> bool:
        """把指定 entry 移到最前；idx 預設 -1 表示最後一筆（對應舊 /to_top）。"""
        n = len(self._entries)
        if n < 2:
            return False
        if idx < 0:
            idx = n - 1
        if not (0 <= idx < n):
            return False
        entry = self._entries.pop(idx)
        self._entries.insert(0, entry)
        return True

    # ── Delete ──────────────────────────────────────────────────────────
    def delete(self, idx: int) -> bool:
        if 0 <= idx < len(self._entries):
            del self._entries[idx]
            return True
        return False

    def clear(self) -> int:
        """清空，回傳被清除的筆數。"""
        n = len(self._entries)
        self._entries.clear()
        return n

    # ── Serialize ───────────────────────────────────────────────────────
    def to_list(self) -> list[list[str]]:
        return self.read_all()

    @classmethod
    def from_list(cls, name: str, data) -> "Workspace":
        """從序列化資料建立。data 可為 List[List[str]]（新格式）或 List[str]（舊格式）。"""
        ws = cls(name)
        if isinstance(data, list):
            for e in data:
                ws.append(e)
        return ws

    def flatten(self, seg_sep: str = " ", entry_sep: str = " ") -> str:
        """攤平為單一字串：entry 內以 seg_sep 串接，entry 間以 entry_sep 串接。"""
        return entry_sep.join(seg_sep.join(e) for e in self._entries)

    def lines(self, seg_sep: str = " ") -> list[str]:
        """每個 entry 攤平為一行字串，回傳行清單（顯示用）。"""
        return [seg_sep.join(e) for e in self._entries]

    # ── Persistence ─────────────────────────────────────────────────────
    def export(self, path: str, seg_sep: str = " ") -> None:
        """匯出至檔案。.txt → 每個 entry 一行；其它（預設 .json）→ List[List[str]]。"""
        directory = os.path.dirname(path)
        if directory:
            os.makedirs(directory, exist_ok=True)
        if path.lower().endswith(".txt"):
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(self.lines(seg_sep)))
        else:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(self._entries, f, ensure_ascii=False, indent=2)

    def import_file(self, path: str, append: bool = True) -> int:
        """從檔案匯入，回傳新增筆數。append=False 會先清空。

        .txt → 每個非空行為一個 entry；.json → List[List[str]] 或舊的 List[str]。
        """
        if not append:
            self._entries.clear()
        added = 0
        if path.lower().endswith(".txt"):
            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        self.append(line)
                        added += 1
        else:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            if not isinstance(data, list):
                raise ValueError("匯入格式不正確，應為 JSON 陣列。")
            for e in data:
                self.append(e)
                added += 1
        return added

    def __len__(self) -> int:
        return len(self._entries)

    def __repr__(self) -> str:
        return f"Workspace(name={self.name!r}, entries={len(self._entries)})"
