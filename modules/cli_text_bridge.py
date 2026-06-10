"""modules.cli_text_bridge — 終端文字輸入橋接模組。

消費 cli_text topic（來自 TerminalInput 的純文字輸出）：
- payload == EXIT_SIGNAL（"__EXIT__"）→ 僅發射 app_ctl "EXIT"，終止應用程式。
- payload.strip() 為空白 → 直接丟棄，不發任何訊息。
- 其他有效文字 → 依序：
    1. 先發射 ui_event {"type":"message","role":"user","text":text}
       （讓使用者在 TUI 看到自己輸入的文字，對齊 main.py:178 行為）
    2. 再發射 raw_text text
       （供 WorkspaceManager 寫入工作區，對齊 main.py:179 行為）
  順序不可對調，與舊版 main.py D 段落 177-179 完全一致。
"""

from core.message import Message
from core.module import TunnelModule
from terminal_input import EXIT_SIGNAL


class CliTextBridge(TunnelModule):
    """終端文字輸入橋接模組，將 cli_text 分流為 UI 顯示與工作區寫入。"""

    name = "cli_text_bridge"
    consumes = ("cli_text",)

    def handle(self, message: Message) -> None:
        """處理 cli_text 訊息。

        EXIT_SIGNAL → emit app_ctl "EXIT"；
        空白 → 忽略；
        其他 → 先 emit ui_event(user)，後 emit raw_text。
        """
        text: str = message.payload

        if text == EXIT_SIGNAL:
            self.emit("app_ctl", "EXIT")
            return

        if not text.strip():
            return

        # 先 UI 顯示，後寫入工作區（main.py:178-179 順序）
        self.emit("ui_event", {"type": "message", "role": "user", "text": text})
        self.emit("raw_text", text)
