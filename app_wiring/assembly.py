"""app_wiring/assembly.py — 核心組裝（build_core）與啟停註冊表（Lifecycle）。

`build_core()` 只建立 queue、SessionManager、原生 TunnelModule 與 Exchange 並呼叫 `wire()`，
**不匯入任何硬體／網路模組**（record、voice_to_text、http_client、text_to_voice…），
因此在沒有 pyaudio 的環境也能呼叫與測試。legacy 元件由入口（`app.py:main()`）
以 `parts.queues[...]` 自行建構。

`Lifecycle` 依登記順序啟動；停機預設**正序**（與重構前 `app.py` 的手寫順序一致），
`reverse=True` 保留給日後的 drain 設計。
"""

import logging
import queue
from dataclasses import dataclass, field

from app_wiring.settings import ensure_default_session, export_dir_from, slm_settings
from app_wiring.topology import wire
from app_wiring.ui_events import _dict_to_ui_event
from core.exchange import Exchange
from modules.chat_flow import ChatFlow
from modules.cli_text_bridge import CliTextBridge
from modules.command_router import CommandRouter
from modules.stt_gate import SttGate
from modules.workspace_manager import WorkspaceManager

log = logging.getLogger("app.lifecycle")

# wire() 的 legacy_queues 鍵名（見 app_wiring/topology.py docstring）。
# Recorder 與 VoiceToText 不共用 audio queue：audio_out／audio_in 各自獨立，由 Exchange 路由。
LEGACY_QUEUE_KEYS = (
    "key_signal",      # KeyboardListener／LocalControl 輸出
    "cli_cmd",         # TerminalInput 指令輸出
    "cli_text",        # TerminalInput 文字輸出
    "recorder_cmd",    # Recorder 控制輸入
    "audio_out",       # Recorder 音訊輸出
    "audio_in",        # VoiceToText 音訊輸入
    "recorder_event",  # Recorder 事件輸出
    "stt_out",         # VoiceToText STT 結果輸出
    "stt_event",       # VoiceToText 處理結果事件輸出
    "http_send",       # HttpClient 發送輸入
    "http_recv",       # HttpClient 接收輸出
    "summary_in",      # SummaryGenerator 請求輸入
    "summary_out_q",   # SummaryGenerator 結果輸出
    "tts_input",       # AudioPriorityPlayer 語音輸入
    "tts_cmd",         # AudioPriorityPlayer 控制輸入
    "ui_event_q",      # TuiRenderer 事件輸入
)

# 原生模組鍵名；順序即 main() 的啟動順序。
NATIVE_KEYS = ("wm", "stt_gate", "command_router", "chat_flow", "cli_text_bridge")


@dataclass
class CoreParts:
    """build_core() 的產物。"""

    queues: dict
    native: dict
    exchange: Exchange
    app_ctl: queue.Queue
    session_manager: object
    export_dir: str


def build_core(
    config,
    *,
    session_manager=None,
    exchange=None,
    queues=None,
    clipboard=None,
    ui_event_transform=_dict_to_ui_event,
) -> CoreParts:
    """建立 queue → SessionManager（＋default 對話）→ 原生模組 → Exchange → wire()。

    不啟動任何執行緒。`session_manager`／`exchange` 可由呼叫端（測試）注入；
    注入的 SessionManager 同樣會經 `ensure_default_session()`。

    手機入口（`mobile/state.py`）額外使用：
    - `queues`：覆寫部分 legacy queue（鍵須屬 LEGACY_QUEUE_KEYS；物件只需
      put_nowait／empty 等 InboxAdapter／OutboxAdapter 用到的方法）。
    - `clipboard`：傳給 CommandRouter 的剪貼簿實作（None＝本機 utils.clipboard）。
    - `ui_event_transform`：傳給 wire()；None 表示 ui_event_q 收原始 dict。
    """
    overrides = dict(queues or {})
    unknown = set(overrides) - set(LEGACY_QUEUE_KEYS)
    if unknown:
        raise ValueError(f"未知的 queue 鍵: {sorted(unknown)}")
    queues = {key: overrides[key] if key in overrides else queue.Queue() for key in LEGACY_QUEUE_KEYS}

    if session_manager is None:
        from session_manager import SessionManager
        session_manager = SessionManager(config)
    ensure_default_session(session_manager)

    export_dir = export_dir_from(config)
    summary_threshold, slm_enabled = slm_settings(config)

    wm = WorkspaceManager()
    native = {
        "wm":              wm,
        "stt_gate":        SttGate(),
        "command_router":  CommandRouter(wm, session_manager, export_dir, clipboard=clipboard),
        "chat_flow":       ChatFlow(
            session_manager,
            summary_threshold=summary_threshold,
            slm_enabled=slm_enabled,
        ),
        "cli_text_bridge": CliTextBridge(),
    }

    if exchange is None:
        exchange = Exchange()
    app_ctl = wire(
        exchange,
        native_modules=native,
        legacy_queues=queues,
        ui_event_transform=ui_event_transform,
    )

    return CoreParts(
        queues=queues,
        native=native,
        exchange=exchange,
        app_ctl=app_ctl,
        session_manager=session_manager,
        export_dir=export_dir,
    )


@dataclass
class Lifecycle:
    """啟停註冊表：依 add() 順序啟動；stop_all() 預設正序、個別 stop() 例外只 log。"""

    _entries: list = field(default_factory=list)
    started: list = field(default_factory=list)

    def add(self, name: str, obj) -> None:
        self._entries.append((name, obj))

    def names(self) -> list:
        return [name for name, _ in self._entries]

    def start_all(self) -> None:
        """依序 start()；某個 start() 拋例外時直接上拋（與重構前相同），已啟動者記在 started。"""
        for name, obj in self._entries:
            obj.start()
            self.started.append(name)

    def stop_all(self, *, reverse: bool = False) -> None:
        """停止已啟動的元件；預設正序，reverse=True 倒序。個別例外 log 後繼續。"""
        started = set(self.started)
        entries = [(n, o) for n, o in self._entries if n in started]
        if reverse:
            entries.reverse()
        for name, obj in entries:
            try:
                obj.stop()
            except Exception:
                log.exception("停止 %s 時發生例外（略過，繼續停其他元件）", name)
        self.started.clear()
