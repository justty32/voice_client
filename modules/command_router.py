"""modules.command_router — 指令流唯一消費者。

消費 commands 通道，統一處理熱鍵訊號、終端斜線指令與語音指令。
熱鍵的舊字串訊號（"RECORD_TOGGLE" 等）在 handle() 內正規化為指令 dict，
keyboard_listener.py 毋須修改。

各指令領域的實作位於 modules.command_handlers；本模組保留公開入口、
派發及錄音／播放控制。
"""

import logging

from core.message import Message
from core.module import TunnelModule
from modules.command_handlers import (
    SessionCommandMixin,
    VoiceCommandMixin,
    WorkspaceCommandMixin,
)

log = logging.getLogger(__name__)

# 舊熱鍵字串 → 標準化 cmd 名稱
_STR_TO_CMD = {
    "RECORD_TOGGLE": "record_toggle",
    "RECORD_COMMAND_TOGGLE": "record_command_toggle",
    "QUICK_SEND": "quick_send",
    "FORCE_STOP_TTS": "force_stop_tts",
    "PLAY_LAST_ORIGINAL": "play_last",
}


class CommandRouter(
    WorkspaceCommandMixin,
    SessionCommandMixin,
    VoiceCommandMixin,
    TunnelModule,
):
    """commands 與 recorder_event 通道的消費者；持有 WorkspaceManager 與 SessionManager 參照。"""

    name = "command_router"
    consumes = ("commands", "recorder_event")

    def __init__(self, workspace_manager, session_manager, export_dir="."):
        super().__init__()
        self._wm = workspace_manager
        self._sm = session_manager
        self._export_dir = export_dir
        self._is_recording: bool = False
        self._last_mode: str = "normal"

    # ── 公開入口 ──────────────────────────────────────────────────────────

    def handle(self, message: Message) -> None:
        # 依 topic 分派：recorder_event 走獨立處理路徑
        if message.topic == "recorder_event":
            self._handle_recorder_event(message.payload)
            return

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
        """依 cmd_item["cmd"] 路由到對應處理方法。"""
        cmd = cmd_item.get("cmd", "")

        if cmd == "record_toggle":
            self._handle_record_toggle(mode="normal", set_mode_on_stop=True)
        elif cmd == "record_command_toggle":
            self._handle_record_toggle(mode="command", set_mode_on_stop=False)
        elif cmd == "quick_send":
            self._handle_send()
        elif cmd == "force_stop_tts":
            self._handle_force_stop_tts()
        elif cmd == "play_last":
            self._handle_play_last()
        # ── 工作區指令 ───────────────────────────────────────────────────
        elif cmd == "/ws":
            self._handle_ws(cmd_item.get("args", []))
        elif cmd == "/show":
            self._handle_show()
        elif cmd == "/clear":
            self._handle_clear(cmd_item.get("args", []))
        elif cmd == "/del":
            self._handle_del(cmd_item.get("args", []))
        elif cmd == "/move":
            self._handle_move(cmd_item.get("args", []))
        elif cmd == "/to_top":
            self._handle_to_top(cmd_item.get("args", []))
        elif cmd == "/concat":
            self._handle_concat()
        elif cmd == "/copy":
            self._handle_copy()
        elif cmd == "/paste":
            self._handle_paste()
        elif cmd == "/export":
            self._handle_export(cmd_item.get("args", []))
        elif cmd == "/import":
            self._handle_import(cmd_item.get("args", []))
        elif cmd == "/send":
            self._handle_send()
        # ── 對話管理指令 ─────────────────────────────────────────────────
        elif cmd in ("/new", "/switch", "/list", "/delete", "/rename",
                     "/history", "/save", "/load") and self._sm is None:
            # 防禦：未接 SessionManager 時給友善訊息而非 AttributeError
            self._ui_msg("[系統] 對話管理功能尚未接入。")
        elif cmd == "/new":
            self._handle_new(cmd_item.get("args", []))
        elif cmd == "/switch":
            self._handle_switch(cmd_item.get("args", []))
        elif cmd == "/list":
            self._handle_list()
        elif cmd == "/delete":
            self._handle_delete(cmd_item.get("args", []))
        elif cmd == "/rename":
            self._handle_rename(cmd_item.get("args", []))
        elif cmd == "/history":
            self._handle_history()
        elif cmd == "/save":
            self._handle_save(cmd_item.get("args", []))
        elif cmd == "/load":
            self._handle_load(cmd_item.get("args", []))
        elif cmd == "/stop":
            self._handle_force_stop_tts()
        elif cmd == "/help":
            self._handle_help()
        elif cmd == "/exit":
            self.emit("app_ctl", "EXIT")
        # ── 語音指令 ─────────────────────────────────────────────────────
        elif cmd == "voice":
            self._handle_voice(cmd_item.get("args", []))
        elif cmd == "unknown":
            # terminal_input 發 {"cmd":"unknown","args":[原始行]}，顯示 args[0]
            args = cmd_item.get("args", [])
            self._ui_msg(f"未知指令: {args[0] if args else ''}")
        else:
            # 未知指令（Task 4-5 未覆蓋的 cmd 最終落到這裡）
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
            self._last_mode = mode
            self.emit("recorder_ctl", "START")
            self.emit("gate_ctl", {"mode": mode})
        else:
            self.emit("recorder_ctl", "STOP")
            if set_mode_on_stop:
                self._last_mode = mode
                self.emit("gate_ctl", {"mode": mode})

    # ── Recorder 事件處理（port main.py:143-158）─────────────────────────

    def _handle_recorder_event(self, payload: dict) -> None:
        """處理來自 recorder_event 通道的事件。

        Port 自 main.py 段落 B（lines 143-158）：
        - recording_started → _is_recording=True；依 _last_mode 顯示狀態
        - recording_stopped → _is_recording=False；顯示「處理中」
        - error → 重設狀態、emit gate_ctl normal、顯示錯誤訊息與「待機」
        - 未知事件 → 忽略（log debug）
        """
        evt = payload.get("event", "") if isinstance(payload, dict) else ""

        if evt == "recording_started":
            self._is_recording = True
            status_text = "語音指令中" if self._last_mode == "command" else "錄音中"
            self.emit("ui_event", {"type": "status", "text": status_text})

        elif evt == "recording_stopped":
            self._is_recording = False
            self.emit("ui_event", {"type": "status", "text": "處理中"})

        elif evt == "error":
            self._is_recording = False
            self._last_mode = "normal"
            self.emit("gate_ctl", {"mode": "normal"})
            msg = payload.get("message", "未知錄音錯誤") if isinstance(payload, dict) else "未知錄音錯誤"
            self.emit("ui_event", {
                "type": "message",
                "role": "system",
                "text": f"[錄音錯誤] {msg}",
            })
            self.emit("ui_event", {"type": "status", "text": "待機"})

        else:
            log.debug("CommandRouter: 忽略未知 recorder_event: %s", evt)

    def _ui_msg(self, text: str) -> None:
        """便利方法：發 ui_event system 訊息。"""
        self.emit("ui_event", {"type": "message", "role": "system", "text": text})

    def _handle_force_stop_tts(self) -> None:
        self.emit("tts_ctl", "STOP_SPEECH")
        self.emit("ui_event", {"type": "status", "text": "待機"})

    def _handle_play_last(self) -> None:
        # 發 chat_ctl play_last；由 ChatFlow（階段④）消費並重播最後一次回覆。
        self.emit("chat_ctl", {"cmd": "play_last"})
