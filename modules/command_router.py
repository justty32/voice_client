"""modules.command_router — 指令流唯一消費者。

消費 commands 通道，統一處理熱鍵訊號、終端斜線指令與語音指令。
熱鍵的舊字串訊號（"RECORD_TOGGLE" 等）在 handle() 內正規化為指令 dict，
keyboard_listener.py 毋須修改。

後續任務將在此類擴充工作區指令（Task 3）、對話管理指令（Task 4）
與語音指令解析（Task 5）；dispatch 以明確的 if/elif 分支實作，
保持與既有模組相同的純 Python 風格。
"""

import logging

from core.message import Message
from core.module import TunnelModule

log = logging.getLogger(__name__)

# 舊熱鍵字串 → 標準化 cmd 名稱
_STR_TO_CMD = {
    "RECORD_TOGGLE": "record_toggle",
    "RECORD_COMMAND_TOGGLE": "record_command_toggle",
    "QUICK_SEND": "quick_send",
    "FORCE_STOP_TTS": "force_stop_tts",
    "PLAY_LAST_ORIGINAL": "play_last",
}


class CommandRouter(TunnelModule):
    """commands 通道的唯一消費者；持有 WorkspaceManager 與 SessionManager 參照。"""

    name = "command_router"
    consumes = ("commands",)

    def __init__(self, workspace_manager, session_manager, export_dir="."):
        super().__init__()
        self._wm = workspace_manager
        self._sm = session_manager          # Task 4 接入，現階段未使用
        self._export_dir = export_dir
        self._is_recording: bool = False

    # ── 公開入口 ──────────────────────────────────────────────────────────

    def handle(self, message: Message) -> None:
        payload = message.payload

        # 第一層：舊字串訊號正規化
        if isinstance(payload, str):
            cmd_name = _STR_TO_CMD.get(payload)
            if cmd_name is None:
                self.emit("ui_event", {
                    "type": "message",
                    "role": "system",
                    "text": f"未知指令: {payload}",
                })
                return
            cmd_item = {"cmd": cmd_name}
        else:
            cmd_item = payload

        self._dispatch(cmd_item)

    # ── 內部派發 ─────────────────────────────────────────────────────────

    def _dispatch(self, cmd_item: dict) -> None:
        """依 cmd_item["cmd"] 路由到對應處理方法。

        後續任務（3-5）在此 if/elif 鏈末、fallthrough 之前插入新分支即可。
        """
        cmd = cmd_item.get("cmd", "")

        if cmd == "record_toggle":
            self._handle_record_toggle(mode="normal", set_mode_on_stop=True)
        elif cmd == "record_command_toggle":
            self._handle_record_toggle(mode="command", set_mode_on_stop=False)
        elif cmd == "quick_send":
            self._handle_quick_send()
        elif cmd == "force_stop_tts":
            self._handle_force_stop_tts()
        elif cmd == "play_last":
            self._handle_play_last()
        else:
            # 未知指令（Task 3-5 未覆蓋的 cmd 最終落到這裡）
            self.emit("ui_event", {
                "type": "message",
                "role": "system",
                "text": f"未知指令: {cmd}",
            })

    # ── 熱鍵處理（port main.py:120-141）─────────────────────────────────

    def _handle_record_toggle(self, mode: str, set_mode_on_stop: bool) -> None:
        """翻轉錄音狀態；依舊版語意設定 gate_ctl 模式。

        舊 main.py 語意：RECORD_TOGGLE 不論開始/停止一律把 is_command_mode
        清為 False；RECORD_COMMAND_TOGGLE 只在開始時設 True、停止時不變。

        :param mode: 傳給 SttGate 的模式（"normal" 或 "command"）。
        :param set_mode_on_stop: 停止錄音時是否也送 gate_ctl（F8=是、F7=否）。
        """
        self._is_recording = not self._is_recording
        if self._is_recording:
            self.emit("recorder_ctl", "START")
            self.emit("gate_ctl", {"mode": mode})
        else:
            self.emit("recorder_ctl", "STOP")
            if set_mode_on_stop:
                self.emit("gate_ctl", {"mode": mode})

    def _handle_quick_send(self) -> None:
        """Task 3 完整實作前的佔位處理。"""
        self.emit("ui_event", {
            "type": "message",
            "role": "system",
            "text": "/send 將於工作區指令任務接入",
        })

    def _handle_force_stop_tts(self) -> None:
        self.emit("tts_ctl", "STOP_SPEECH")
        self.emit("ui_event", {"type": "status", "text": "待機"})

    def _handle_play_last(self) -> None:
        self.emit("ui_event", {
            "type": "message",
            "role": "system",
            "text": "重播功能於階段④接入",
        })
