"""modules.workspace_manager — 工作區管理者。

raw_text 通道的唯一消費者：持有多個具名工作區與「當前工作區」指標，
新的辨識文字只會進入當前工作區。切換目標靠 switch()（之後由
CommandRouter 在階段③接上 /ws 指令）。
"""

from core.message import Message
from core.module import TunnelModule
from workspace import Workspace


class WorkspaceManager(TunnelModule):
    name = "workspace_manager"
    consumes = ("raw_text",)

    DEFAULT_NAMES = ("buffer", "stt")

    def __init__(self, names: tuple = DEFAULT_NAMES, current: str = "buffer"):
        super().__init__()
        self._spaces = {n: Workspace(n) for n in names}
        if current not in self._spaces:
            raise ValueError(f"未知工作區: {current}")
        self._current = current

    # ── 查詢 ──────────────────────────────────────────────────────
    @property
    def current(self) -> str:
        return self._current

    def names(self) -> list:
        return list(self._spaces)

    def get(self, name: str) -> Workspace | None:
        return self._spaces.get(name)

    # ── 操作 ──────────────────────────────────────────────────────
    def switch(self, name: str) -> bool:
        """切換當前工作區；未知名稱回 False 且不變更。

        可能由其它執行緒（CommandRouter）呼叫：_current 僅為單一屬性
        指派且永遠指向既存的 key，在 CPython（GIL）下無需加鎖。
        """
        if name not in self._spaces:
            return False
        self._current = name
        return True

    # ── 消費 ──────────────────────────────────────────────────────
    def handle(self, message: Message) -> None:
        self._spaces[self._current].append(message.payload)
