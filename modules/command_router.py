"""modules.command_router — 指令流唯一消費者。

消費 commands 通道，統一處理熱鍵訊號、終端斜線指令與語音指令；
另消費 recorder_event、stt_event 以維護錄音／STT 狀態列。
熱鍵的舊字串訊號（"RECORD_TOGGLE" 等）在 handle() 內正規化為指令 dict，
keyboard_listener.py 毋須修改。

各指令領域的實作位於 modules.command_handlers；本模組保留公開入口、
派發表（_build_handlers，指令集見 protocol/commands.py）及錄音／播放控制。
"""

import logging

from core.message import Message
from core.module import TunnelModule
from modules.command_handlers import (
    SessionCommandMixin,
    VoiceCommandMixin,
    WorkspaceCommandMixin,
)
from protocol import payloads as P
from protocol import topics as T
from protocol.commands import HOTKEY_TO_CMD, SESSION_COMMANDS

log = logging.getLogger(__name__)

# 舊熱鍵字串 → 標準化 cmd 名稱（單一來源在 protocol/commands.py）
_STR_TO_CMD = HOTKEY_TO_CMD


class CommandRouter(
    WorkspaceCommandMixin,
    SessionCommandMixin,
    VoiceCommandMixin,
    TunnelModule,
):
    """commands、recorder_event 與 stt_event 通道的消費者；持有 WorkspaceManager 與 SessionManager 參照。"""

    name = "command_router"
    consumes = (T.COMMANDS, T.RECORDER_EVENT, T.STT_EVENT)

    def __init__(self, workspace_manager, session_manager, export_dir=".", clipboard=None):
        """`clipboard`：提供 copy(text)／paste() 並回傳 (ok, str) 的物件；
        None（預設）使用本機 `utils.clipboard`。手機入口注入瀏覽器往返版本。"""
        super().__init__()
        self._wm = workspace_manager
        self._sm = session_manager
        self._export_dir = export_dir
        self._clipboard = clipboard
        self._is_recording: bool = False
        self._last_mode: str = "normal"
        self._handlers: dict = self._build_handlers()

    # ── 公開入口 ──────────────────────────────────────────────────────────

    def handle(self, message: Message) -> None:
        # 依 topic 分派：recorder_event 走獨立處理路徑
        if message.topic == T.RECORDER_EVENT:
            self._handle_recorder_event(message.payload)
            return
        if message.topic == T.STT_EVENT:
            self._handle_stt_event(message.payload)
            return

        payload = message.payload

        # 第一層：舊字串訊號正規化
        if isinstance(payload, str):
            cmd_name = _STR_TO_CMD.get(payload)
            if cmd_name is None:
                self.emit(T.UI_EVENT, P.ui_message("system", f"未知指令: {payload}"))
                return
            cmd_item = {"cmd": cmd_name}
        else:
            cmd_item = payload

        self._dispatch(cmd_item)

    # ── 內部派發 ─────────────────────────────────────────────────────────

    def _build_handlers(self) -> dict:
        """建立派發表：cmd 名稱 → handler(cmd_item)。

        鍵涵蓋熱鍵標準化 cmd、protocol.commands.SLASH_COMMANDS、voice、unknown；
        由契約測試（tests/test_protocol_commands.py）鎖住。各 handler 簽章不變，
        需要 args 的以 lambda 包 cmd_item.get("args", [])。
        """
        def args(item: dict) -> list:
            return item.get("args", [])

        return {
            # ── 熱鍵（HOTKEY_TO_CMD 的值）────────────────────────────────
            "record_toggle": lambda item: self._handle_record_toggle(
                mode="normal", set_mode_on_stop=True),
            "record_command_toggle": lambda item: self._handle_record_toggle(
                mode="command", set_mode_on_stop=False),
            "quick_send": lambda item: self._handle_send(),
            "force_stop_tts": lambda item: self._handle_force_stop_tts(),
            "play_last": lambda item: self._handle_play_last(),
            # ── 工作區指令 ───────────────────────────────────────────────
            "/ws": lambda item: self._handle_ws(args(item)),
            "/show": lambda item: self._handle_show(),
            "/clear": lambda item: self._handle_clear(args(item)),
            "/del": lambda item: self._handle_del(args(item)),
            "/move": lambda item: self._handle_move(args(item)),
            "/to_top": lambda item: self._handle_to_top(args(item)),
            "/concat": lambda item: self._handle_concat(),
            "/copy": lambda item: self._handle_copy(),
            "/paste": lambda item: self._handle_paste(),
            "/export": lambda item: self._handle_export(args(item)),
            "/import": lambda item: self._handle_import(args(item)),
            "/send": lambda item: self._handle_send(),
            # ── 對話管理指令（SESSION_COMMANDS；_dispatch 先做 _sm 防禦）──
            "/new": lambda item: self._handle_new(args(item)),
            "/switch": lambda item: self._handle_switch(args(item)),
            "/list": lambda item: self._handle_list(),
            "/delete": lambda item: self._handle_delete(args(item)),
            "/rename": lambda item: self._handle_rename(args(item)),
            "/history": lambda item: self._handle_history(),
            "/save": lambda item: self._handle_save(args(item)),
            "/load": lambda item: self._handle_load(args(item)),
            # ── 其他斜線指令 ─────────────────────────────────────────────
            "/stop": lambda item: self._handle_force_stop_tts(),
            "/help": lambda item: self._handle_help(),
            "/exit": lambda item: self._handle_exit(),
            # ── 語音指令與終端未知行 ─────────────────────────────────────
            "voice": lambda item: self._handle_voice(args(item)),
            "unknown": lambda item: self._handle_unknown_line(item),
        }

    def _dispatch(self, cmd_item: dict) -> None:
        """依 cmd_item["cmd"] 查派發表路由到對應處理方法。"""
        cmd = cmd_item.get("cmd", "")
        # 非字串 cmd（手寫 payload）不查表，落到「未知指令」，與舊 if/elif 鏈一致
        known = isinstance(cmd, str)

        if known and cmd in SESSION_COMMANDS and self._sm is None:
            # 防禦：未接 SessionManager 時給友善訊息而非 AttributeError
            self._ui_msg("[系統] 對話管理功能尚未接入。")
            return

        handler = self._handlers.get(cmd) if known else None
        if handler is None:
            # 派發表沒有的 cmd（例如手寫 payload）
            self.emit(T.UI_EVENT, P.ui_message("system", f"未知指令: {cmd}"))
            return
        handler(cmd_item)

    def _handle_unknown_line(self, cmd_item: dict) -> None:
        # terminal_input 發 {"cmd":"unknown","args":[原始行]}，顯示 args[0]
        args = cmd_item.get("args", [])
        self._ui_msg(f"未知指令: {args[0] if args else ''}")

    def _handle_exit(self) -> None:
        self.emit(T.APP_CTL, P.APP_EXIT)

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
            self.emit(T.RECORDER_CTL, P.RECORDER_START)
            self.emit(T.GATE_CTL, P.gate_mode(mode))
        else:
            self.emit(T.RECORDER_CTL, P.RECORDER_STOP)
            if set_mode_on_stop:
                self._last_mode = mode
                self.emit(T.GATE_CTL, P.gate_mode(mode))

    # ── Recorder 事件處理（port main.py:143-158）─────────────────────────

    def _handle_recorder_event(self, payload: dict) -> None:
        """處理來自 recorder_event 通道的事件。

        Port 自 main.py 段落 B（lines 143-158）：
        - recording_started → _is_recording=True；依 _last_mode 顯示狀態
        - recording_stopped → _is_recording=False；flushed is False（無音訊送往 STT）
          顯示「待機」，否則（含舊 payload 無 flushed 鍵）顯示「處理中」
        - error → 重設狀態、emit gate_ctl normal、顯示錯誤訊息與「待機」
        - 未知事件 → 忽略（log debug）
        """
        evt = payload.get("event", "") if isinstance(payload, dict) else ""

        if evt == "recording_started":
            self._is_recording = True
            status_text = "語音指令中" if self._last_mode == "command" else "錄音中"
            self.emit(T.UI_EVENT, P.ui_status(status_text))

        elif evt == "recording_stopped":
            self._is_recording = False
            flushed = payload.get("flushed") if isinstance(payload, dict) else None
            self.emit(T.UI_EVENT, P.ui_status("待機" if flushed is False else "處理中"))

        elif evt == "error":
            self._is_recording = False
            self._last_mode = "normal"
            self.emit(T.GATE_CTL, P.gate_mode("normal"))
            msg = payload.get("message", "未知錄音錯誤") if isinstance(payload, dict) else "未知錄音錯誤"
            self.emit(T.UI_EVENT, P.ui_message("system", f"[錄音錯誤] {msg}"))
            self.emit(T.UI_EVENT, P.ui_status("待機"))

        else:
            log.debug("CommandRouter: 忽略未知 recorder_event: %s", evt)

    # ── STT 事件處理（錯誤與狀態閉環）───────────────────────────────────

    def _handle_stt_event(self, payload: dict) -> None:
        """處理來自 stt_event 通道的事件：STT 結束（不論成敗）一律讓狀態列回「待機」。

        - stt_error → system 訊息「[STT 錯誤] {message}」＋「待機」
        - stt_empty／stt_done → 「待機」（D6：「處理中」指 STT 處理，完成即待機）
        - 未知事件 → 忽略（log debug）

        錄音中途也會因靜音切片送出音訊，此時 STT 結果抵達仍在錄音；
        為免把「錄音中」覆蓋成「待機」，_is_recording 為真時不改狀態列（錯誤訊息照發）。
        """
        evt = payload.get("event", "") if isinstance(payload, dict) else ""

        if evt == "stt_error":
            msg = payload.get("message", "未知 STT 錯誤")
            self.emit(T.UI_EVENT, P.ui_message("system", f"[STT 錯誤] {msg}"))
            self._stt_finished_status()
        elif evt in ("stt_empty", "stt_done"):
            self._stt_finished_status()
        else:
            log.debug("CommandRouter: 忽略未知 stt_event: %s", evt)

    def _stt_finished_status(self) -> None:
        if not self._is_recording:
            self.emit(T.UI_EVENT, P.ui_status("待機"))

    def _ui_msg(self, text: str) -> None:
        """便利方法：發 ui_event system 訊息。"""
        self.emit(T.UI_EVENT, P.ui_message("system", text))

    def _handle_force_stop_tts(self) -> None:
        self.emit(T.TTS_CTL, P.TTS_STOP_SPEECH)
        self.emit(T.UI_EVENT, P.ui_status("待機"))

    def _handle_play_last(self) -> None:
        # 發 chat_ctl play_last；由 ChatFlow（階段④）消費並重播最後一次回覆。
        self.emit(T.CHAT_CTL, P.chat_cmd("play_last"))
