"""mobile/state.py — 手機伺服器的狀態容器 `MobileState` 與組裝工廠 `build_mobile_state()`。

手機與桌面共用 `app_wiring.assembly.build_core()`：同一組 Exchange＋原生模組
（WorkspaceManager、SttGate、CommandRouter、ChatFlow、CliTextBridge），只替換邊緣裝置：
瀏覽器錄音代替 Recorder、WebSocket 推送代替 TuiRenderer／AudioPriorityPlayer（見 mobile/edge.py）。

匯入本模組沒有任何副作用（不載入 config、不設日誌、不建元件、不寫檔）；
呼叫 `build_mobile_state(config)` 時才建立所有 queue 與元件實例。
`*_cls` 參數供測試注入替身（避免載入 Whisper 模型或連線 LLM）。
"""

import logging
import os
import queue
from collections import deque
from dataclasses import dataclass, field
from typing import Any

from app_wiring.assembly import CoreParts, Lifecycle, build_core
from http_client import HttpClient
from mobile.edge import BrowserClipboard, EdgeSink, discard, tts_cmd_to_ws, tts_to_ws, ui_event_to_ws
from summary_generator import SummaryGenerator
from utils.logging_setup import setup_logging as _setup_logging
from voice_to_text import VoiceToText

log = logging.getLogger("mobile_server")

# D10：手機停機時 buffer 非空則匯出到 <export_dir>/_buffer_temp.json（沿用舊手機 buffer 暫存檔名）。
BUFFER_AUTOSAVE_NAME = "_buffer_temp.json"


@dataclass
class MobileState:
    """單使用者手機伺服器的全部狀態。"""

    cfg: Any
    parts: CoreParts
    voice_to_text: Any
    summary_gen: Any
    http_client: Any
    lifecycle: Lifecycle
    # 已轉成前端格式的 WS 事件（Exchange 經 EdgeSink 投遞，邊緣 helper 直接 put）。
    ui_event_queue: queue.Queue
    # B6：唯一服務中的 WebSocket 連線（最新連線）；None 表示目前無人連線。
    current_ws: Any = None
    # B6：send_json 失敗的事件暫存於此，下一輪優先重送（等同放回 queue 頭）。
    pending_events: deque = field(default_factory=deque)
    # 最近一次推送給前端的 (對話清單, 當前對話)；變動時 pusher 補推 sessions。
    sessions_snapshot: Any = None

    @property
    def session_manager(self):
        return self.parts.session_manager

    @property
    def export_dir(self) -> str:
        return self.parts.export_dir

    @property
    def wm(self):
        return self.parts.native["wm"]


def build_mobile_state(
    config,
    *,
    voice_to_text_cls=VoiceToText,
    http_client_cls=HttpClient,
    summary_cls=SummaryGenerator,
    setup_logging: bool = True,
) -> MobileState:
    """依 config 建立 `MobileState`：build_core()＋手機邊緣 queue＋legacy 元件＋Lifecycle。"""
    if setup_logging:
        _setup_logging(config)

    out_q: queue.Queue = queue.Queue()
    edge_queues = {
        "ui_event_q":   EdgeSink(out_q, ui_event_to_ws, "ui_event"),
        "tts_input":    EdgeSink(out_q, tts_to_ws, "tts"),
        "tts_cmd":      EdgeSink(out_q, tts_cmd_to_ws, "tts_ctl"),
        "recorder_cmd": EdgeSink(out_q, discard, "recorder_ctl"),
    }
    parts = build_core(
        config,
        queues=edge_queues,
        clipboard=BrowserClipboard(out_q),
        ui_event_transform=None,
    )
    q = parts.queues

    voice_to_text = voice_to_text_cls(config, q["audio_in"], q["stt_out"],
                                      stt_event_queue=q["stt_event"])
    summary_gen = summary_cls(config, q["summary_in"], q["summary_out_q"])
    http_client = http_client_cls(config, q["http_send"], q["http_recv"], parts.session_manager)

    # 啟動順序：legacy（同舊手機 voice_to_text → summary → http）→ 原生模組 → exchange（同桌面）
    lifecycle = Lifecycle()
    lifecycle.add("voice_to_text", voice_to_text)
    lifecycle.add("summary_generator", summary_gen)
    lifecycle.add("http_client", http_client)
    for name, module in parts.native.items():
        lifecycle.add(name, module)
    lifecycle.add("exchange", parts.exchange)

    return MobileState(
        cfg=config,
        parts=parts,
        voice_to_text=voice_to_text,
        summary_gen=summary_gen,
        http_client=http_client,
        lifecycle=lifecycle,
        ui_event_queue=out_q,
    )


def autosave_buffer(state: MobileState) -> str | None:
    """D10：buffer 非空時匯出到 `<export_dir>/_buffer_temp.json`；回傳路徑，未匯出回 None。"""
    ws = state.wm.get("buffer")
    if ws is None or ws.is_empty():
        return None
    path = os.path.join(state.export_dir, BUFFER_AUTOSAVE_NAME)
    try:
        ws.export(path)
    except Exception as exc:
        log.error("Failed to auto-save buffer: %s", exc)
        return None
    log.info("Auto-saved buffer to %s", path)
    return path
