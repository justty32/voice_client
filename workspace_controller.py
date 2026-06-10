"""
workspace_controller.py — 前端無關的工作區指令派發核心。

管理「當前工作區」指標，並把統一 CRUD 指令（/ws、/show、/clear、/send）轉換為
一組「意圖（intent）」交給前端套用。這樣 TUI 與 mobile 共用同一套邏輯，且可單元測試。

為何用「意圖」而非直接執行：
  - stt、chat 兩個工作區是同步物件（Workspace / SessionManager），可直接操作。
  - buffer 工作區由 TextAccumulator 在自己的執行緒中持有，必須透過 acc_cmd_queue
    指令操作（不可跨執行緒直接改）。因此 buffer 相關動作以 acc_cmds 形式回傳，
    由前端送入佇列。

未來擴展（plans/workspace_unification.md §7）：可改以 WorkspaceRegistry 管理任意多個、
多型別工作區，此控制器的派發介面不需大改。
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

from utils import clipboard
from workspace import Workspace, resolve_filename


@dataclass
class WSResult:
    """指令派發結果，由前端套用到各自的輸出通道。"""
    messages: list[tuple[str, str]] = field(default_factory=list)  # (role, text)
    acc_cmds: list[dict] = field(default_factory=list)             # 送入 acc_cmd_queue
    clear_ui: bool = False                                         # 是否清畫面


class WorkspaceController:
    NAMES = ("stt", "buffer", "chat")

    def __init__(self, session_manager, export_dir: str = "."):
        self.stt = Workspace("stt")
        self._sm = session_manager
        self._export_dir = export_dir or "."
        self.current = "buffer"

    # ── 狀態 ────────────────────────────────────────────────────────────
    def is_valid(self, name: str) -> bool:
        return name in self.NAMES

    @staticmethod
    def _to_int(s) -> int | None:
        try:
            return int(s)
        except (ValueError, TypeError):
            return None

    def set_current(self, name: str) -> bool:
        if self.is_valid(name):
            self.current = name
            return True
        return False

    # ── /ws ─────────────────────────────────────────────────────────────
    def handle_ws(self, args: list[str], buffer_count: int) -> WSResult:
        """無參數 → 列出工作區與筆數；有參數 → 切換當前工作區。"""
        if not args:
            counts = {
                "stt": self.stt.count(),
                "buffer": buffer_count,
                "chat": self._sm.message_count(),
            }
            lines = ["工作區列表:"]
            for name in self.NAMES:
                mark = " (當前)" if name == self.current else ""
                lines.append(f"  - {name}{mark} · {counts[name]} 筆")
            return WSResult(messages=[("system", "\n".join(lines))])

        name = args[0].lower()
        if self.set_current(name):
            return WSResult(messages=[("system", f"已切換當前工作區至: {name}")])
        return WSResult(messages=[("system", f"未知工作區: {name}（可用: {'/'.join(self.NAMES)}）")])

    # ── /show ───────────────────────────────────────────────────────────
    def handle_show(self) -> WSResult:
        target = self.current
        if target == "buffer":
            return WSResult(acc_cmds=[{"cmd": "peek"}])
        if target == "stt":
            if self.stt.is_empty():
                return WSResult(messages=[("system", "[stt 工作區是空的]")])
            body = "\n".join(f"  [{i+1}] {t}" for i, t in enumerate(self.stt.lines()))
            return WSResult(messages=[("system", f"[stt 工作區 · {self.stt.count()} 筆]\n{body}")])
        # chat
        return WSResult(messages=[("system", self._sm.get_history())])

    # ── /clear ──────────────────────────────────────────────────────────
    def handle_clear(self, args: list[str]) -> WSResult:
        target = args[0].lower() if args else self.current

        if target == "ui":
            return WSResult(clear_ui=True)
        if target == "buffer":
            return WSResult(acc_cmds=[{"cmd": "clear"}])
        if target == "stt":
            n = self.stt.clear()
            return WSResult(messages=[("system", f"[系統] stt 工作區已清空（原含 {n} 筆）。")])
        if target == "chat":
            n = self._sm.clear_history()
            return WSResult(messages=[("system", f"[系統] chat 工作區（對話歷史）已清空（原含 {n} 筆）。")])
        return WSResult(messages=[("system", f"未知的清除目標: {target}（可用: ui/{'/'.join(self.NAMES)}）")])

    # ── /send ───────────────────────────────────────────────────────────
    def handle_send(self) -> WSResult:
        if self.current == "buffer":
            return WSResult(acc_cmds=[{"cmd": "flush", "msg_type": "TextChat"}])
        return WSResult(messages=[("system", f"[系統] /send 僅適用於 buffer 工作區（當前: {self.current}）。")])

    # ── /copy ───────────────────────────────────────────────────────────
    def handle_copy(self) -> WSResult:
        """把當前工作區內容複製到系統剪貼簿。"""
        if self.current == "buffer":
            return WSResult(acc_cmds=[{"cmd": "copy"}])
        if self.current == "stt":
            if self.stt.is_empty():
                return WSResult(messages=[("system", "[stt 工作區是空的，沒有可複製的內容]")])
            text = self.stt.flatten(seg_sep=" ", entry_sep="\n")
            ok, err = clipboard.copy(text)
            msg = f"[系統] 已複製 stt 工作區 {self.stt.count()} 筆到剪貼簿。" if ok else f"[錯誤] {err}"
            return WSResult(messages=[("system", msg)])
        # chat
        ok, err = clipboard.copy(self._sm.get_history())
        msg = "[系統] 已複製對話歷史到剪貼簿。" if ok else f"[錯誤] {err}"
        return WSResult(messages=[("system", msg)])

    # ── /paste ──────────────────────────────────────────────────────────
    def handle_paste(self) -> WSResult:
        """把剪貼簿內容貼到當前工作區（每個非空行為一筆，追加至末尾）。"""
        if self.current == "buffer":
            return WSResult(acc_cmds=[{"cmd": "paste"}])
        if self.current == "stt":
            ok, data = clipboard.paste()
            if not ok:
                return WSResult(messages=[("system", f"[錯誤] {data}")])
            lines = [ln.strip() for ln in data.splitlines() if ln.strip()]
            for ln in lines:
                self.stt.append(ln)
            return WSResult(messages=[("system", f"[系統] 已從剪貼簿貼上 {len(lines)} 筆到 stt 工作區。")])
        # chat
        return WSResult(messages=[("system", "[系統] chat 工作區不支援貼上（請切換到 buffer 或 stt）。")])

    # ── /del ────────────────────────────────────────────────────────────
    def handle_del(self, args: list[str]) -> WSResult:
        if not args:
            return WSResult(messages=[("system", "用法: /del <編號>")])
        if self.current == "buffer":
            return WSResult(acc_cmds=[{"cmd": "delete", "args": args}])
        i = self._to_int(args[0])
        if i is None:
            return WSResult(messages=[("system", "用法: /del <編號>（需為數字）")])
        if self.current == "stt":
            ok = self.stt.delete(i - 1)
            return WSResult(messages=[("system", f"[系統] 已刪除 stt 第 {i} 筆。" if ok else f"[錯誤] stt 沒有第 {i} 筆。")])
        ok = self._sm.delete_message(i - 1)
        return WSResult(messages=[("system", f"[系統] 已刪除 chat 第 {i} 筆。" if ok else f"[錯誤] chat 沒有第 {i} 筆。")])

    # ── /move ───────────────────────────────────────────────────────────
    def handle_move(self, args: list[str]) -> WSResult:
        if len(args) < 2:
            return WSResult(messages=[("system", "用法: /move <來源編號> <目標編號>")])
        if self.current == "buffer":
            return WSResult(acc_cmds=[{"cmd": "move", "args": args}])
        src = self._to_int(args[0])
        dst = self._to_int(args[1])
        if src is None or dst is None:
            return WSResult(messages=[("system", "用法: /move <來源編號> <目標編號>（需為數字）")])
        ws_obj = self.stt if self.current == "stt" else None
        if ws_obj is not None:
            ok = ws_obj.move(src - 1, dst - 1)
        else:
            ok = self._sm.move_message(src - 1, dst - 1)
        label = self.current
        return WSResult(messages=[("system", f"[系統] 已將 {label} 第 {src} 筆移到第 {dst} 位。" if ok else "[錯誤] 移動失敗（編號超出範圍）。")])

    # ── /to_top ─────────────────────────────────────────────────────────
    def handle_totop(self, args: list[str]) -> WSResult:
        if self.current == "buffer":
            return WSResult(acc_cmds=[{"cmd": "to_top", "args": args}])
        idx = self._to_int(args[0]) if args else None
        if args and idx is None:
            return WSResult(messages=[("system", "用法: /to_top [編號]（需為數字）")])
        target0 = (idx - 1) if idx else -1
        if self.current == "stt":
            ok = self.stt.move_to_top(target0)
        else:
            ok = self._sm.move_message_to_top(target0)
        if not ok:
            if idx:
                return WSResult(messages=[("system", f"[錯誤] {self.current} 沒有第 {idx} 筆，或筆數不足。")])
            return WSResult()
        where = f"第 {idx} 筆" if idx else "最後一筆"
        return WSResult(messages=[("system", f"[系統] 已將 {self.current} {where}移至最前方。")])

    # ── /concat ─────────────────────────────────────────────────────────
    def handle_concat(self) -> WSResult:
        if self.current == "buffer":
            return WSResult(acc_cmds=[{"cmd": "concat"}])
        if self.current == "stt":
            if self.stt.is_empty():
                return WSResult()
            count = self.stt.count()
            self.stt.concat_all(" ")
            return WSResult(messages=[("system", f"[系統] 已連接 stt 工作區（將 {count} 筆壓縮為 1 筆）。")])
        return WSResult(messages=[("system", "[系統] chat 工作區不支援 /concat。")])

    # ── /export ─────────────────────────────────────────────────────────
    def handle_export(self, args: list[str]) -> WSResult:
        if self.current == "buffer":
            return WSResult(acc_cmds=[{"cmd": "export", "args": args}])
        if self.current == "stt":
            if not args:
                return WSResult(messages=[("system", "[錯誤] 請指定匯出檔名。例如: /export my_data")])
            path = resolve_filename(" ".join(args), self._export_dir)
            try:
                self.stt.export(path)
                return WSResult(messages=[("system", f"[系統] stt 工作區已匯出至: {path}")])
            except Exception as e:
                return WSResult(messages=[("system", f"[錯誤] 匯出失敗: {e}")])
        return WSResult(messages=[("system", "[系統] chat 工作區請改用 /save 儲存對話。")])

    # ── /import ─────────────────────────────────────────────────────────
    def handle_import(self, args: list[str]) -> WSResult:
        if self.current == "buffer":
            return WSResult(acc_cmds=[{"cmd": "import", "args": args}])
        if self.current == "stt":
            if not args:
                return WSResult(messages=[("system", "[錯誤] 請指定匯入檔名。")])
            path = resolve_filename(" ".join(args), self._export_dir)
            if not os.path.exists(path):
                return WSResult(messages=[("system", f"[錯誤] 找不到檔案: {path}")])
            try:
                added = self.stt.import_file(path, append=True)
                return WSResult(messages=[("system", f"[系統] 已從 {path} 匯入 {added} 筆到 stt 工作區。")])
            except ValueError as e:
                return WSResult(messages=[("system", f"[錯誤] {e}")])
            except Exception as e:
                return WSResult(messages=[("system", f"[錯誤] 匯入失敗: {e}")])
        return WSResult(messages=[("system", "[系統] chat 工作區請改用 /load 載入對話。")])
