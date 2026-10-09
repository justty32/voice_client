"""app_wiring/topology.py — 純接線：把 legacy queue 與原生 TunnelModule 登錄進 Exchange。

此模組不含任何業務邏輯；邏輯由各模組自行持有。
"""

import queue

from app_wiring.ui_events import _dict_to_ui_event
from core.adapter import InboxAdapter, OutboxAdapter
from core.exchange import Exchange  # noqa: F401  (型別註記字串引用)
from protocol import topics as T


def wire(
    exchange: "Exchange",
    *,
    native_modules: dict,
    legacy_queues: dict,
    ui_event_transform=_dict_to_ui_event,
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
          "stt_event"     — VoiceToText 處理結果事件輸出（stt_error／stt_empty／stt_done）
          "http_send"     — HttpClient 發送輸入
          "http_recv"     — HttpClient 接收輸出
          "summary_in"    — SummaryGenerator 請求輸入
          "summary_out_q" — SummaryGenerator 結果輸出
          "tts_input"     — AudioPriorityPlayer 語音輸入
          "tts_cmd"       — AudioPriorityPlayer 控制輸入
          "ui_event_q"    — TuiRenderer 事件輸入
    ui_event_transform
        ui_event 投遞進 ui_event_q 前的轉換；預設 dict→UiEvent（TuiRenderer 用）。
        手機入口傳 None，讓 WS 推送端拿到原始 dict。

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
        OutboxAdapter(lq["key_signal"], topic=T.COMMANDS, source="keyboard_listener"),
    )
    exchange.register_producer(
        "cli_cmd",
        OutboxAdapter(lq["cli_cmd"], topic=T.COMMANDS, source="terminal_input_cmd"),
    )
    exchange.register_producer(
        "cli_text",
        OutboxAdapter(lq["cli_text"], topic=T.CLI_TEXT, source="terminal_input_text"),
    )
    exchange.register_producer(
        "recorder_audio_out",
        OutboxAdapter(lq["audio_out"], topic=T.AUDIO, source="recorder"),
    )
    exchange.register_producer(
        "recorder_event",
        OutboxAdapter(lq["recorder_event"], topic=T.RECORDER_EVENT, source="recorder"),
    )
    exchange.register_producer(
        "stt_out",
        OutboxAdapter(lq["stt_out"], topic=T.STT_TEXT, source="voice_to_text"),
    )
    exchange.register_producer(
        "stt_event",
        OutboxAdapter(lq["stt_event"], topic=T.STT_EVENT, source="voice_to_text"),
    )
    exchange.register_producer(
        "http_recv",
        OutboxAdapter(lq["http_recv"], topic=T.INBOUND, source="http_client"),
    )
    exchange.register_producer(
        "summary_out_q",
        OutboxAdapter(lq["summary_out_q"], topic=T.SUMMARY_OUT, source="summary_generator"),
    )

    # ── 消費者（InboxAdapter）：Exchange topic → legacy queue ─────────────
    exchange.register_consumer(
        T.RECORDER_CTL,
        InboxAdapter(lq["recorder_cmd"]),
    )
    exchange.register_consumer(
        T.AUDIO,
        InboxAdapter(lq["audio_in"]),
    )
    exchange.register_consumer(
        T.OUTBOUND,
        InboxAdapter(lq["http_send"]),
    )
    exchange.register_consumer(
        T.SUMMARY_REQ,
        InboxAdapter(lq["summary_in"]),
    )
    exchange.register_consumer(
        T.TTS,
        InboxAdapter(lq["tts_input"]),
    )
    exchange.register_consumer(
        T.TTS_CTL,
        InboxAdapter(lq["tts_cmd"]),
    )
    exchange.register_consumer(
        T.UI_EVENT,
        InboxAdapter(lq["ui_event_q"], transform=ui_event_transform),
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
    exchange.register_consumer(T.APP_CTL, InboxAdapter(app_ctl_q))

    return app_ctl_q
