"""
app.py — Voice Client 純接線入口（資料隧道架構）

此模組負責兩件事：
1. wire()：將所有既有模組（裸 queue 介面）與新原生模組（TunnelModule）
   透過 OutboxAdapter / InboxAdapter 登錄進 Exchange，完成全系統接線。
   此函式不含任何業務邏輯；邏輯由各模組自行持有。
2. main()：建立所有元件、呼叫 wire()、啟動所有模組、
   阻塞等待 app_ctl "EXIT" 或 KeyboardInterrupt，最後統一停機。

main.py 為薄殼，僅做 `from app import main; main()` 的委派。
"""

import logging
import os
import queue

from config import load_config
from core.adapter import InboxAdapter, OutboxAdapter
from core.exchange import Exchange
from modules.chat_flow import ChatFlow
from modules.cli_text_bridge import CliTextBridge
from modules.command_router import CommandRouter
from modules.stt_gate import SttGate
from modules.workspace_manager import WorkspaceManager

# tui_renderer 依賴 rich，採延遲匯入。
# _dict_to_ui_event 使用 _make_ui_event() 工廠以保持可測試性：
# 成功時回傳真實 UiEvent（供 TuiRenderer 使用），
# 失敗時（rich 未安裝）回傳等效的 _FallbackUiEvent（屬性相容）。
try:
    from tui_renderer import UiEvent as _UiEventClass
except ImportError:  # pragma: no cover
    from dataclasses import dataclass as _dataclass, field as _field
    from typing import Any as _Any

    @_dataclass
    class _UiEventClass:  # type: ignore[no-redef]
        """rich 未安裝時的輕量替代（屬性與 UiEvent 相容）。"""
        event_type: str
        data: _Any = _field(default=None)


# ── 日誌設定（port main.py:29-41）────────────────────────────────────────────

def _setup_logging(config):
    """設定全域日誌：等級與輸出路徑均從 config 讀取。

    完整 port 自 main.py:29-41；行為完全相同。
    """
    level_str = config.get("LOGGING", "level", fallback="INFO")
    level = getattr(logging, level_str.upper(), logging.INFO)
    log_file = config.get("WORKSPACE", "log_file", fallback="output/system.log")
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


# ── UI 事件轉換（dict → UiEvent）─────────────────────────────────────────────

def _dict_to_ui_event(payload: dict):
    """將 Exchange 內流通的 ui_event dict 轉換為 TuiRenderer 需要的 UiEvent 物件。

    支援三種形狀：
    - {"type":"status","text":str}   → UiEvent("status", text)
    - {"type":"message","role":str,"text":str}
                                     → UiEvent("message", {"role":..., "text":...})
    - {"type":"clear"}               → UiEvent("clear", None)

    未知 type → 安全 fallback：UiEvent("message", {"role":"system","text":str(payload)})

    使用模組頂層的 _UiEventClass（rich 可用時為真實 UiEvent，否則為相容替代），
    確保此函式在測試環境中不依賴 rich 亦可呼叫。
    """
    kind = payload.get("type", "")

    if kind == "status":
        return _UiEventClass("status", payload.get("text", ""))

    if kind == "message":
        return _UiEventClass("message", {
            "role": payload.get("role", "system"),
            "text": payload.get("text", ""),
        })

    if kind == "clear":
        return _UiEventClass("clear", None)

    # 未知型別 → 安全 fallback，以 system 訊息顯示原始 payload
    return _UiEventClass("message", {"role": "system", "text": str(payload)})


# ── 純接線（不含業務邏輯）───────────────────────────────────────────────────

def wire(
    exchange: "Exchange",
    *,
    native_modules: dict,
    legacy_queues: dict,
) -> "queue.Queue":
    """將所有模組接線到 Exchange，回傳 app_ctl queue 供主執行緒阻塞讀取。

    參數
    ----
    exchange
        已建立的 Exchange 實例（尚未 start）。
    native_modules
        原生 TunnelModule 字典，期望鍵名：
          "wm"           → WorkspaceManager
          "stt_gate"     → SttGate
          "command_router" → CommandRouter
          "chat_flow"    → ChatFlow
          "cli_text_bridge" → CliTextBridge
    legacy_queues
        既有模組的裸 queue 字典，期望鍵名（均為 queue.Queue）：
          "key_signal"    — KeyboardListener 輸出
          "cli_cmd"       — TerminalInput 指令輸出
          "cli_text"      — TerminalInput 文字輸出
          "recorder_cmd"  — Recorder 控制輸入
          "audio_out"     — Recorder 音訊輸出
          "audio_in"      — VoiceToText 音訊輸入
          "recorder_event"— Recorder 事件輸出
          "stt_out"       — VoiceToText STT 結果輸出
          "http_send"     — HttpClient 發送輸入
          "http_recv"     — HttpClient 接收輸出
          "summary_in"    — SummaryGenerator 請求輸入
          "summary_out_q" — SummaryGenerator 結果輸出
          "tts_input"     — AudioPriorityPlayer 語音輸入
          "tts_cmd"       — AudioPriorityPlayer 控制輸入
          "ui_event_q"    — TuiRenderer 事件輸入

    回傳
    ----
    queue.Queue
        app_ctl 裸 queue（已透過 InboxAdapter 登錄進 Exchange）。
        主執行緒以 get(timeout=...) 阻塞讀取，payload 直接為字串；
        收到 "EXIT" 時結束；KeyboardInterrupt 同樣退出。
    """
    lq = legacy_queues
    nm = native_modules

    # ── 生產者（OutboxAdapter）：legacy queue → Exchange topic ────────────
    exchange.register_producer(
        "key_signal",
        OutboxAdapter(lq["key_signal"], topic="commands", source="keyboard_listener"),
    )
    exchange.register_producer(
        "cli_cmd",
        OutboxAdapter(lq["cli_cmd"], topic="commands", source="terminal_input_cmd"),
    )
    exchange.register_producer(
        "cli_text",
        OutboxAdapter(lq["cli_text"], topic="cli_text", source="terminal_input_text"),
    )
    exchange.register_producer(
        "recorder_audio_out",
        OutboxAdapter(lq["audio_out"], topic="audio", source="recorder"),
    )
    exchange.register_producer(
        "recorder_event",
        OutboxAdapter(lq["recorder_event"], topic="recorder_event", source="recorder"),
    )
    exchange.register_producer(
        "stt_out",
        OutboxAdapter(lq["stt_out"], topic="stt_text", source="voice_to_text"),
    )
    exchange.register_producer(
        "http_recv",
        OutboxAdapter(lq["http_recv"], topic="inbound", source="http_client"),
    )
    exchange.register_producer(
        "summary_out_q",
        OutboxAdapter(lq["summary_out_q"], topic="summary_out", source="summary_generator"),
    )

    # ── 消費者（InboxAdapter）：Exchange topic → legacy queue ─────────────
    exchange.register_consumer(
        "recorder_ctl",
        InboxAdapter(lq["recorder_cmd"]),
    )
    exchange.register_consumer(
        "audio",
        InboxAdapter(lq["audio_in"]),
    )
    exchange.register_consumer(
        "outbound",
        InboxAdapter(lq["http_send"]),
    )
    exchange.register_consumer(
        "summary_req",
        InboxAdapter(lq["summary_in"]),
    )
    exchange.register_consumer(
        "tts",
        InboxAdapter(lq["tts_input"]),
    )
    exchange.register_consumer(
        "tts_ctl",
        InboxAdapter(lq["tts_cmd"]),
    )
    exchange.register_consumer(
        "ui_event",
        InboxAdapter(lq["ui_event_q"], transform=_dict_to_ui_event),
    )

    # ── 原生模組：attach(exchange) 自動登錄 outbox + inbox ───────────────
    nm["wm"].attach(exchange)
    nm["stt_gate"].attach(exchange)
    nm["command_router"].attach(exchange)
    nm["chat_flow"].attach(exchange)
    nm["cli_text_bridge"].attach(exchange)

    # ── app_ctl：主執行緒阻塞讀取的 Inbox ─────────────────────────────────
    # 使用 InboxAdapter 包裝裸 queue，使 app_ctl.get() 直接回傳 payload（字串）
    # 而非 Message 物件，簡化主執行緒的讀取邏輯。
    app_ctl_q = queue.Queue()
    exchange.register_consumer("app_ctl", InboxAdapter(app_ctl_q))

    return app_ctl_q


# ── 主程式入口 ────────────────────────────────────────────────────────────────

def main():
    """Voice Client 主程式：建立所有元件、接線、啟動，阻塞至 EXIT。

    啟動順序：
      1. load_config / _setup_logging
      2. 建立所有裸 queue
      3. SessionManager + default session 初始化
      4. 建立既有（硬體/IO）模組
      5. 建立原生 TunnelModule
      6. Exchange + wire()
      7. 啟動所有模組 + exchange
      8. 發出啟動 UI 訊息（含熱鍵停用提示）
      9. 主執行緒阻塞於 app_ctl（get timeout 迴圈）
      10. finally 統一停機（TERMINATE → stop all → exchange.stop）
    """
    # 硬體／IO 模組延遲匯入（測試環境不需要這些相依性）
    from http_client import HttpClient
    from keyboard_listener import KeyboardListener
    from local_control import LocalControl
    from record import Recorder
    from session_manager import SessionManager
    from summary_generator import SummaryGenerator
    from terminal_input import TerminalInput
    from text_to_voice import AudioPriorityPlayer
    from tui_renderer import TuiRenderer, UiEvent
    from voice_to_text import VoiceToText

    config = load_config()
    _setup_logging(config)
    log = logging.getLogger("app")

    # ── 建立所有裸 queue ──────────────────────────────────────────────────
    # 注意：Recorder 與 VoiceToText 不再共用 audio_queue；
    # 各自有獨立 queue，Exchange 負責在兩者之間路由。
    key_signal_queue      = queue.Queue()   # KeyboardListener 輸出
    recorder_cmd_queue    = queue.Queue()   # Recorder 控制輸入
    audio_queue_out       = queue.Queue()   # Recorder 音訊輸出
    audio_queue_in        = queue.Queue()   # VoiceToText 音訊輸入
    recorder_event_queue  = queue.Queue()   # Recorder 事件輸出
    stt_output_queue      = queue.Queue()   # VoiceToText STT 結果輸出
    cli_text_queue        = queue.Queue()   # TerminalInput 文字輸出
    cli_cmd_queue         = queue.Queue()   # TerminalInput 指令輸出
    summary_queue         = queue.Queue()   # SummaryGenerator 請求輸入
    summary_output_queue  = queue.Queue()   # SummaryGenerator 結果輸出
    send_queue            = queue.Queue()   # HttpClient 發送輸入
    recv_queue            = queue.Queue()   # HttpClient 接收輸出
    tts_input_queue       = queue.Queue()   # AudioPriorityPlayer 語音輸入
    tts_cmd_queue         = queue.Queue()   # AudioPriorityPlayer 控制輸入
    ui_event_queue        = queue.Queue()   # TuiRenderer 事件輸入

    # ── SessionManager（port main.py:69-77）──────────────────────────────
    session_manager = SessionManager(config)
    if not session_manager.current_title:
        if not session_manager.switch_session("default"):
            session_manager.new_session("default")

    _export_dir = (
        os.path.dirname(config.get("WORKSPACE", "export_file", fallback="output/export.json"))
        or "."
    )

    # ── 建立既有（硬體/IO）模組（port main.py:79-88）─────────────────────
    keyboard_listener = KeyboardListener(config, key_signal_queue)
    local_control     = LocalControl(key_signal_queue)
    terminal_input    = TerminalInput(config, cli_text_queue, cli_cmd_queue)
    tui_renderer      = TuiRenderer(config, ui_event_queue)
    recorder          = Recorder(config, recorder_cmd_queue, audio_queue_out, recorder_event_queue)
    voice_to_text     = VoiceToText(config, audio_queue_in, stt_output_queue)
    summary_generator = SummaryGenerator(config, summary_queue, summary_output_queue)
    http_client       = HttpClient(config, send_queue, recv_queue, session_manager)
    tts_player        = AudioPriorityPlayer(config, tts_input_queue, tts_cmd_queue)

    # ── 建立原生 TunnelModule ─────────────────────────────────────────────
    wm              = WorkspaceManager()
    stt_gate        = SttGate()
    command_router  = CommandRouter(wm, session_manager, _export_dir)
    chat_flow       = ChatFlow(
        session_manager,
        summary_threshold=config.getint("SLM", "summary_threshold", fallback=20),
        slm_enabled=config.getboolean("SLM", "enabled", fallback=True),
    )
    cli_text_bridge = CliTextBridge()

    # ── Exchange + wire() ─────────────────────────────────────────────────
    exchange = Exchange()
    app_ctl = wire(
        exchange,
        native_modules={
            "wm":               wm,
            "stt_gate":         stt_gate,
            "command_router":   command_router,
            "chat_flow":        chat_flow,
            "cli_text_bridge":  cli_text_bridge,
        },
        legacy_queues={
            "key_signal":       key_signal_queue,
            "cli_cmd":          cli_cmd_queue,
            "cli_text":         cli_text_queue,
            "recorder_cmd":     recorder_cmd_queue,
            "audio_out":        audio_queue_out,
            "audio_in":         audio_queue_in,
            "recorder_event":   recorder_event_queue,
            "stt_out":          stt_output_queue,
            "http_send":        send_queue,
            "http_recv":        recv_queue,
            "summary_in":       summary_queue,
            "summary_out_q":    summary_output_queue,
            "tts_input":        tts_input_queue,
            "tts_cmd":          tts_cmd_queue,
            "ui_event_q":       ui_event_queue,
        },
    )

    # ── 啟動所有既有模組（port main.py:90-99）────────────────────────────
    keyboard_listener.start()
    local_control.start()
    terminal_input.start()
    tui_renderer.start()
    recorder.start()
    voice_to_text.start()
    summary_generator.start()
    http_client.start()
    tts_player.start()

    # ── 啟動原生模組與 Exchange ───────────────────────────────────────────
    wm.start()
    stt_gate.start()
    command_router.start()
    chat_flow.start()
    cli_text_bridge.start()
    exchange.start()

    # ── 發出啟動 UI 訊息（port main.py:101-110）──────────────────────────
    # 直接放 UiEvent 進 ui_event_queue（我們擁有此 queue，無需再走 Exchange）。
    # UiEvent 已在上方 main() 本地 import。
    ui_event_queue.put(UiEvent("status", "待機"))
    if not keyboard_listener.is_active() and not local_control.is_active():
        ui_event_queue.put(UiEvent("message", {
            "role": "system",
            "text": (
                f"全域熱鍵已停用（{keyboard_listener.inactive_reason()}）。\n"
                "請在終端輸入文字後按 Enter 送出；或使用 /send、/stop、/show 等指令。"
            ),
        }))
    elif not keyboard_listener.is_active():
        ui_event_queue.put(UiEvent("message", {
            "role": "system",
            "text": "Wayland 本機控制已啟用；可透過 KDE 全域快捷鍵操作錄音。",
        }))
    log.info("Voice Client started. Session: %s", session_manager.current_title)

    # ── 主迴圈：阻塞於 app_ctl Inbox ─────────────────────────────────────
    try:
        while True:
            try:
                payload = app_ctl.get(timeout=0.5)
                if payload == "EXIT":
                    log.info("收到 EXIT 訊號，開始停機。")
                    break
            except queue.Empty:
                continue
    except KeyboardInterrupt:
        log.info("Shutting down...")

    # ── 統一停機（port main.py:232-243）──────────────────────────────────
    finally:
        tts_cmd_queue.put("TERMINATE")
        keyboard_listener.stop()
        local_control.stop()
        terminal_input.stop()
        tui_renderer.stop()
        recorder.stop()
        voice_to_text.stop()
        summary_generator.stop()
        http_client.stop()
        tts_player.stop()
        wm.stop()
        stt_gate.stop()
        command_router.stop()
        chat_flow.stop()
        cli_text_bridge.stop()
        exchange.stop()
        log.info("Voice Client stopped.")


if __name__ == "__main__":
    main()
