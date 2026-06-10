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

from dataclasses import dataclass, field

from workspace import Workspace


@dataclass
class WSResult:
    """指令派發結果，由前端套用到各自的輸出通道。"""
    messages: list[tuple[str, str]] = field(default_factory=list)  # (role, text)
    acc_cmds: list[dict] = field(default_factory=list)             # 送入 acc_cmd_queue
    clear_ui: bool = False                                         # 是否清畫面


class WorkspaceController:
    NAMES = ("stt", "buffer", "chat")

    def __init__(self, session_manager):
        self.stt = Workspace("stt")
        self._sm = session_manager
        self.current = "buffer"

    # ── 狀態 ────────────────────────────────────────────────────────────
    def is_valid(self, name: str) -> bool:
        return name in self.NAMES

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
