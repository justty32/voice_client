"""
app.py — Voice Client 純接線入口（資料隧道架構）

此模組負責兩件事：
1. wire()：將所有既有模組（裸 queue 介面）與新原生模組（TunnelModule）
   透過 OutboxAdapter / InboxAdapter 登錄進 Exchange，完成全系統接線。
   此函式不含任何業務邏輯；邏輯由各模組自行持有。
   實作位於 app_wiring/topology.py，於此 re-export。
2. main()：呼叫 build_core() 取得核心（queue、原生模組、Exchange、wire()），
   以 parts.queues 建立 legacy 元件，用 Lifecycle 單一清單啟停，
   阻塞等待 app_ctl "EXIT" 或 KeyboardInterrupt，最後統一停機。

main.py 為薄殼，僅做 `from app import main; main()` 的委派。

拆分：wire() → app_wiring/topology.py；組裝與啟停 → app_wiring/assembly.py；
設定解讀 → app_wiring/settings.py；ui_event 轉換 → app_wiring/ui_events.py；
日誌設定 → utils/logging_setup.py。以下名稱自原路徑 re-export 維持相容：
wire、_dict_to_ui_event、_UiEventClass、_setup_logging。
"""

import logging
import queue

from app_wiring.assembly import Lifecycle, build_core
from app_wiring.topology import wire  # noqa: F401  (re-export)
from app_wiring.ui_events import _UiEventClass, _dict_to_ui_event  # noqa: F401
from config import load_config
from protocol import payloads as P
from utils.logging_setup import setup_logging as _setup_logging


# ── 主程式入口 ────────────────────────────────────────────────────────────────

def main():
    """Voice Client 主程式：組裝核心、建立 legacy 元件、啟動，阻塞至 EXIT。

    啟動順序：
      1. load_config / _setup_logging
      2. build_core()：裸 queue、SessionManager＋default 對話、原生 TunnelModule、Exchange＋wire()
      3. 以 parts.queues 建立既有（硬體/IO）模組
      4. Lifecycle 依序啟動：9 個 legacy → 5 個原生 → exchange
      5. 發出啟動 UI 訊息（含熱鍵停用提示）
      6. 主執行緒阻塞於 app_ctl（get timeout 迴圈）
      7. finally 統一停機（TERMINATE → Lifecycle 正序 stop）
    """
    # 硬體／IO 模組延遲匯入（測試環境不需要這些相依性）
    from llm.http_client import HttpClient
    from ui.keyboard_listener import KeyboardListener
    from ui.local_control import LocalControl
    from speech.record import Recorder
    from llm.summary_generator import SummaryGenerator
    from ui.terminal_input import TerminalInput
    from speech.text_to_voice import AudioPriorityPlayer
    from ui.tui_renderer import TuiRenderer, UiEvent
    from speech.voice_to_text import VoiceToText

    config = load_config()
    _setup_logging(config)
    log = logging.getLogger("app")

    parts = build_core(config)
    q = parts.queues
    session_manager = parts.session_manager

    # ── 建立既有（硬體/IO）模組 ───────────────────────────────────────────
    keyboard_listener = KeyboardListener(config, q["key_signal"])
    local_control     = LocalControl(q["key_signal"])

    # 登記順序＝啟動順序＝停機順序（正序，與重構前一致）
    lifecycle = Lifecycle()
    lifecycle.add("keyboard_listener", keyboard_listener)
    lifecycle.add("local_control", local_control)
    lifecycle.add("terminal_input", TerminalInput(config, q["cli_text"], q["cli_cmd"]))
    lifecycle.add("tui_renderer", TuiRenderer(config, q["ui_event_q"]))
    lifecycle.add("recorder", Recorder(config, q["recorder_cmd"], q["audio_out"], q["recorder_event"]))
    lifecycle.add("voice_to_text", VoiceToText(config, q["audio_in"], q["stt_out"],
                                               stt_event_queue=q["stt_event"]))
    lifecycle.add("summary_generator", SummaryGenerator(config, q["summary_in"], q["summary_out_q"]))
    lifecycle.add("http_client", HttpClient(config, q["http_send"], q["http_recv"], session_manager))
    lifecycle.add("tts_player", AudioPriorityPlayer(config, q["tts_input"], q["tts_cmd"]))
    for name, module in parts.native.items():
        lifecycle.add(name, module)
    lifecycle.add("exchange", parts.exchange)

    lifecycle.start_all()

    # ── 發出啟動 UI 訊息 ──────────────────────────────────────────────────
    # 直接放 UiEvent 進 ui_event_q（我們擁有此 queue，無需再走 Exchange）。
    ui_event_queue = q["ui_event_q"]
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
                payload = parts.app_ctl.get(timeout=0.5)
                if payload == P.APP_EXIT:
                    log.info("收到 EXIT 訊號，開始停機。")
                    break
            except queue.Empty:
                continue
    except KeyboardInterrupt:
        log.info("Shutting down...")

    # ── 統一停機 ──────────────────────────────────────────────────────────
    finally:
        q["tts_cmd"].put(P.TTS_TERMINATE)
        lifecycle.stop_all()
        log.info("Voice Client stopped.")


if __name__ == "__main__":
    main()
