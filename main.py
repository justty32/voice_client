"""
main.py — Voice Client 主程式入口 + Main Loop (Router)

Main Loop 是純粹的路由器：輪詢所有 output queue，根據訊息類型轉發到對應的 input/cmd queue。
它不含任何業務邏輯，只做「從 Queue A 取出 → 轉發到 Queue B」。
"""

import configparser
import logging
import os
import queue
import time
from datetime import datetime, timezone

from config import load_config
from http_client import HttpClient
from keyboard_listener import KeyboardListener
from record import Recorder
from session_manager import SessionManager
from text_accumulator import TextAccumulator
from summary_generator import SummaryGenerator
from terminal_input import EXIT_SIGNAL, TerminalInput
from text_to_voice import AudioPriorityPlayer
from tui_renderer import TuiRenderer, UiEvent
from voice_to_text import VoiceToText


def _setup_logging(config):
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


def main():
    config = load_config()
    _setup_logging(config)
    log = logging.getLogger("main")

    # ── Create all Queues ──────────────────────────────────────────────
    key_signal_queue      = queue.Queue()   # KeyboardListener → Main Loop
    recorder_cmd_queue    = queue.Queue()   # Main Loop → Recorder
    audio_queue           = queue.Queue()   # Recorder → VoiceToText
    recorder_event_queue  = queue.Queue()   # Recorder → Main Loop
    stt_output_queue      = queue.Queue()   # VoiceToText → Main Loop
    cli_text_queue        = queue.Queue()   # TerminalInput → Main Loop
    cli_cmd_queue         = queue.Queue()   # TerminalInput → Main Loop
    acc_input_queue       = queue.Queue()   # Main Loop → TextAccumulator
    acc_cmd_queue         = queue.Queue()   # Main Loop → TextAccumulator
    summary_queue         = queue.Queue()   # Main Loop → SummaryGenerator
    acc_output_queue      = queue.Queue()   # TextAccumulator → Main Loop
    summary_output_queue  = queue.Queue()   # SummaryGenerator → Main Loop
    send_queue            = queue.Queue()   # Main Loop → HttpClient
    recv_queue            = queue.Queue()   # HttpClient → Main Loop
    tts_input_queue       = queue.Queue()   # Main Loop → AudioPriorityPlayer
    tts_cmd_queue         = queue.Queue()   # Main Loop → AudioPriorityPlayer
    ui_event_queue        = queue.Queue()   # Main Loop → TuiRenderer

    # ── Session Manager (sync, no Queue) ──────────────────────────────
    session_manager = SessionManager(config)
    if not session_manager.current_title:
        # 優先嘗試切換回上次可能存在的 default，不存在才建新的
        if not session_manager.switch_session("default"):
            session_manager.new_session("default")

    # ── Instantiate modules ────────────────────────────────────────────
    keyboard_listener = KeyboardListener(config, key_signal_queue)
    terminal_input    = TerminalInput(config, cli_text_queue, cli_cmd_queue)
    tui_renderer      = TuiRenderer(config, ui_event_queue)
    recorder          = Recorder(config, recorder_cmd_queue, audio_queue, recorder_event_queue)
    voice_to_text     = VoiceToText(config, audio_queue, stt_output_queue)
    text_accumulator  = TextAccumulator(config, acc_input_queue, acc_cmd_queue, acc_output_queue)
    summary_generator = SummaryGenerator(config, summary_queue, summary_output_queue)
    http_client       = HttpClient(config, send_queue, recv_queue)
    tts_player        = AudioPriorityPlayer(config, tts_input_queue, tts_cmd_queue)

    # ── Start all modules ──────────────────────────────────────────────
    keyboard_listener.start()
    terminal_input.start()
    tui_renderer.start()
    recorder.start()
    voice_to_text.start()
    text_accumulator.start()
    summary_generator.start()
    http_client.start()
    tts_player.start()

    ui_event_queue.put(UiEvent("status", "待機"))
    log.info("Voice Client started. Session: %s", session_manager.current_title)

    # ── State ──────────────────────────────────────────────────────────
    is_recording = False
    is_command_mode = False
    last_full_response = ""

    # ── Main Loop (Router) ─────────────────────────────────────────────
    try:
        while True:
            # ── A. Keyboard signals ────────────────────────────────────
            while not key_signal_queue.empty():
                signal = key_signal_queue.get_nowait()
                if signal == "RECORD_TOGGLE":
                    is_recording = not is_recording
                    is_command_mode = False
                    recorder_cmd_queue.put("START" if is_recording else "STOP")
                elif signal == "RECORD_COMMAND_TOGGLE":
                    is_recording = not is_recording
                    is_command_mode = True if is_recording else is_command_mode
                    recorder_cmd_queue.put("START" if is_recording else "STOP")
                elif signal == "QUICK_SEND":
                    acc_cmd_queue.put({"cmd": "flush", "msg_type": "TextChat"})

                elif signal == "FORCE_STOP_TTS":
                    tts_cmd_queue.put("STOP_SPEECH")
                    ui_event_queue.put(UiEvent("status", "待機"))
                
                elif signal == "PLAY_LAST_ORIGINAL":
                    if last_full_response:
                        ui_event_queue.put(UiEvent("message", {"role": "system", "text": "播放最後一次回覆原文"}))
                        tts_input_queue.put({"text": last_full_response, "priority": "medium"})

            # ── B. Recorder events → UI ────────────────────────────────
            while not recorder_event_queue.empty():
                event = recorder_event_queue.get_nowait()
                evt = event.get("event", "")
                if evt == "recording_started":
                    is_recording = True
                    ui_event_queue.put(UiEvent("status", "錄音中" if not is_command_mode else "語音指令中"))
                elif evt == "recording_stopped":
                    is_recording = False
                    ui_event_queue.put(UiEvent("status", "處理中"))
                # Volume events are no longer needed by the UI

            # ── C. STT output → UI + SLM ──────────────────────────────
            while not stt_output_queue.empty():
                text = stt_output_queue.get_nowait()
                if text.strip():
                    if is_command_mode:
                        ui_event_queue.put(UiEvent("message", {"role": "system", "text": f"[語音指令] {text}"}))
                        _handle_voice_command(text, session_manager, ui_event_queue, acc_cmd_queue, summary_queue, tts_cmd_queue)
                    else:
                        ui_event_queue.put(UiEvent("message", {"role": "voice", "text": text}))
                        acc_input_queue.put({"type": "text", "text": text, "msg_type": "VoiceChat"})

            # ── D. CLI text → SLM ─────────────────────────────────────
            while not cli_text_queue.empty():
                text = cli_text_queue.get_nowait()
                if text == EXIT_SIGNAL:
                    raise KeyboardInterrupt
                if text.strip():
                    ui_event_queue.put(UiEvent("message", {"role": "user", "text": text}))
                    acc_input_queue.put({"type": "text", "text": text, "msg_type": "TextChat"})

            # ── E. CLI commands → Session operations ───────────────────
            while not cli_cmd_queue.empty():
                cmd_item = cli_cmd_queue.get_nowait()
                _route_cli_cmd(cmd_item, session_manager, ui_event_queue, acc_cmd_queue, tts_cmd_queue)

            # ── F. Accumulator output → HTTP ───────────────────────────
            while not acc_output_queue.empty():
                item = acc_output_queue.get_nowait()
                if item.get("type") == "payload":
                    payload = item["payload"]
                    payload["Title"] = session_manager.current_title or "default"
                    payload.setdefault("Metadata", {})["ClientTime"] = (
                        datetime.now(timezone.utc).isoformat()
                    )
                    
                    # 將最終發送的內容加入對話歷史
                    session_manager.add_message("user", payload["Content"])

                    ui_event_queue.put(UiEvent("message", {
                        "role": "sending",
                        "text": f"[傳送內容] {payload['Content']}",
                    }))
                    send_queue.put(payload)
                    ui_event_queue.put(UiEvent("status", "傳送中"))
                elif item.get("type") == "buffer_peek":
                    ui_event_queue.put(UiEvent("message", {"role": "system", "text": item["text"]}))

            # ── F1. Summary output → UI/TTS ────────────────────────────
            while not summary_output_queue.empty():
                item = summary_output_queue.get_nowait()
                if item.get("type") == "status":
                    ui_event_queue.put(UiEvent("status", item["text"]))
                elif item.get("type") == "summary":
                    #session_name = session_manager.current_title or "預設"
                    #display = f"{session_name} 大語言模型回覆摘要：{item['text']}"
                    display = f"回覆摘要：{item['text']}"
                    ui_event_queue.put(UiEvent("message", {"role": "summary", "text": display}))
                    tts_input_queue.put({"text": display, "priority": "medium"})

            # ── G. HTTP response → TUI + TTS + SLM ────────────────────
            while not recv_queue.empty():
                response = recv_queue.get_nowait()
                res_text = _route_response(response, ui_event_queue, tts_input_queue, acc_cmd_queue, summary_queue,
                                send_queue, session_manager, config)
                if res_text:
                    last_full_response = res_text

            time.sleep(0.05)

    except KeyboardInterrupt:
        log.info("Shutting down...")
    finally:
        tts_cmd_queue.put("TERMINATE")
        keyboard_listener.stop()
        terminal_input.stop()
        tui_renderer.stop()
        recorder.stop()
        voice_to_text.stop()
        text_accumulator.stop()
        summary_generator.stop()
        http_client.stop()
        tts_player.stop()
        log.info("Voice Client stopped.")


# ── Router helpers (pure routing, no business logic) ──────────────────────


def _route_cli_cmd(cmd_item: dict, session_manager: SessionManager, ui_event_queue: queue.Queue, acc_cmd_queue: queue.Queue, tts_cmd_queue: queue.Queue):
    cmd = cmd_item.get("cmd", "")
    args = cmd_item.get("args", [])

    if cmd == "/new":
        title = " ".join(args) if args else f"session_{len(session_manager.list_sessions()) + 1}"
        session_manager.new_session(title)
        ui_event_queue.put(UiEvent("message", {"role": "system", "text": f"新建對話: {title}"}))
    elif cmd == "/switch":
        title = " ".join(args) if args else "default"
        if session_manager.switch_session(title):
            ui_event_queue.put(UiEvent("message", {"role": "system", "text": f"切換至: {title}"}))
        elif not args and title == "default":
            # 如果是預設且不存在，則新建
            session_manager.new_session("default")
            ui_event_queue.put(UiEvent("message", {"role": "system", "text": f"建立並切換至: default"}))
        else:
            ui_event_queue.put(UiEvent("message", {"role": "system", "text": f"找不到對話: {title}"}))
    elif cmd == "/list":
        sessions = session_manager.list_sessions()
        current = session_manager.current_title or "無"
        text = "對話列表:\n" + "\n".join(f"  - {s}" for s in sessions)
        text += f"\n\n當前使用session：{current}"
        ui_event_queue.put(UiEvent("message", {"role": "system", "text": text}))
    elif cmd == "/delete":
        title = " ".join(args)
        success, msg = session_manager.delete_session(title)
        ui_event_queue.put(UiEvent("message", {"role": "system", "text": msg}))
    elif cmd == "/load":
        if not args:
            ui_event_queue.put(UiEvent("message", {"role": "system", "text": "請指定要載入的檔名。"}))
        else:
            filename = args[0]
            success, msg = session_manager.load_session_from_file(filename)
            ui_event_queue.put(UiEvent("message", {"role": "system", "text": msg}))
    elif cmd == "/rename":
        if len(args) < 2:
            ui_event_queue.put(UiEvent("message", {"role": "system", "text": "用法: /rename [舊名稱] [新名稱]"}))
        else:
            old_t, new_t = args[0], args[1]
            success, msg = session_manager.rename_session(old_t, new_t)
            ui_event_queue.put(UiEvent("message", {"role": "system", "text": msg}))
    elif cmd == "/history":
        history = session_manager.get_history()
        ui_event_queue.put(UiEvent("message", {"role": "system", "text": history}))
    elif cmd == "/save":
        filename = " ".join(args) if args else None
        success, msg = session_manager.save_session_to_file(filename)
        ui_event_queue.put(UiEvent("message", {"role": "system", "text": msg}))
    elif cmd == "/clear":
        arg = args[0].lower() if args else None
        if arg == "buffer":
            acc_cmd_queue.put({"cmd": "clear"})
        else:
            # 預設清除 UI
            ui_event_queue.put(UiEvent("clear"))
            ui_event_queue.put(UiEvent("status", "待機"))
    elif cmd == "/concat":
        acc_cmd_queue.put({"cmd": "concat"})
    elif cmd == "/to_top":
        acc_cmd_queue.put({"cmd": "to_top"})
    elif cmd == "/send":
        acc_cmd_queue.put({"cmd": "flush", "msg_type": "TextChat"})
    elif cmd == "/export":
        acc_cmd_queue.put({"cmd": "export", "args": args})
    elif cmd == "/import":
        acc_cmd_queue.put({"cmd": "import", "args": args})
    elif cmd == "/stop":
        tts_cmd_queue.put("STOP_SPEECH")
        ui_event_queue.put(UiEvent("status", "待機"))
    elif cmd == "/show":
        acc_cmd_queue.put({"cmd": "peek"})
    elif cmd == "/help":
        help_text = "/new [title]  /switch [title]  /list  /delete [title]  /save [file]  /load [file]  /rename [old] [new]  /history  /concat  /to_top  /send  /export  /import  /stop  /show  /clear [buffer]  /help  /exit"
        ui_event_queue.put(UiEvent("message", {"role": "system", "text": help_text}))
    elif cmd == "unknown":
        ui_event_queue.put(UiEvent("message", {"role": "system", "text": f"未知指令: {args[0] if args else ''}"}))


def _route_response(
    response: dict,
    ui_event_queue: queue.Queue,
    tts_input_queue: queue.Queue,
    acc_cmd_queue: queue.Queue,
    summary_queue: queue.Queue,
    send_queue: queue.Queue,
    session_manager: SessionManager,
    config: "configparser.ConfigParser",
) -> str | None:
    resp_type = response.get("type", "ChatReply")
    summary_threshold = config.getint("SLM", "summary_threshold", fallback=20)

    if resp_type == "ChatReply":
        content = response.get("Content", {})
        full_response = content.get("full_response", "")
        if full_response:
            session_manager.add_message("assistant", full_response)
            display = full_response
            ui_event_queue.put(UiEvent("message", {"role": "assistant", "text": display}))
            
            if len(full_response) < summary_threshold:
                # 少於 threshold 字，直接播放，不生成摘要
                tts_input_queue.put({"text": full_response, "priority": "medium"})
            else:
                # 達到 threshold 字，放入摘要佇列
                summary_queue.put({"cmd": "summary", "text": full_response,
                                   "title": session_manager.current_title})
            ui_event_queue.put(UiEvent("status", "待機"))
            return full_response
        ui_event_queue.put(UiEvent("status", "待機"))

    elif resp_type == "StatusUpdate":
        text = response.get("text", "")
        ui_event_queue.put(UiEvent("status", text))
        tts_input_queue.put({"text": text, "priority": "low"})

    elif resp_type == "Error":
        msg = response.get("message", "Unknown error")
        ui_event_queue.put(UiEvent("message", {"role": "system", "text": f"[錯誤] {msg}"}))
        tts_input_queue.put({"text": f"發生錯誤：{msg}", "priority": "high"})
    
    return None


def _handle_voice_command(
    text: str,
    session_manager: SessionManager,
    ui_event_queue: queue.Queue,
    acc_cmd_queue: queue.Queue,
    summary_queue: queue.Queue,
    tts_cmd_queue: queue.Queue
):
    """將語音辨識出的文字解析為斜線指令並路由。"""
    text = text.lower().strip()
    # 簡單的關鍵字對應
    if "new" in text or "新建" in text or "開啟對話" in text:
        # 嘗試擷取名稱，例如 "new session apple" -> "session apple"
        parts = text.split()
        args = parts[1:] if len(parts) > 1 else []
        _route_cli_cmd({"cmd": "/new", "args": args}, session_manager, ui_event_queue, acc_cmd_queue, tts_cmd_queue)
    elif "switch" in text or "切換" in text:
        parts = text.split()
        args = parts[1:] if len(parts) > 1 else []
        _route_cli_cmd({"cmd": "/switch", "args": args}, session_manager, ui_event_queue, acc_cmd_queue, tts_cmd_queue)
    elif "list" in text or "列表" in text or "清單" in text:
        _route_cli_cmd({"cmd": "/list"}, session_manager, ui_event_queue, acc_cmd_queue, tts_cmd_queue)
    elif "delete" in text or "刪除" in text:
        parts = text.split()
        args = []
        for i, p in enumerate(parts):
            if "delete" in p or "刪除" in p:
                args = parts[i+1:]
                break
        _route_cli_cmd({"cmd": "/delete", "args": args}, session_manager, ui_event_queue, acc_cmd_queue, tts_cmd_queue)
    elif "save" in text or "保存" in text or "儲存" in text:
        parts = text.split()
        args = []
        for i, p in enumerate(parts):
            if "save" in p or "保存" in p or "儲存" in p:
                args = parts[i+1:]
                break
        _route_cli_cmd({"cmd": "/save", "args": args}, session_manager, ui_event_queue, acc_cmd_queue, tts_cmd_queue)
    elif "concat" in text or "壓縮" in text or "連接" in text:
        _route_cli_cmd({"cmd": "/concat"}, session_manager, ui_event_queue, acc_cmd_queue, tts_cmd_queue)
    elif "to top" in text or "置頂" in text or "移至最前" in text:
        _route_cli_cmd({"cmd": "/to_top"}, session_manager, ui_event_queue, acc_cmd_queue, tts_cmd_queue)
    elif "send" in text or "發送" in text or "傳送" in text:
        _route_cli_cmd({"cmd": "/send"}, session_manager, ui_event_queue, acc_cmd_queue, tts_cmd_queue)
    elif "export" in text or "匯出" in text:
        parts = text.split()
        # 尋找關鍵字後面的詞，例如 "匯出 測試" -> "測試"
        args = []
        for i, p in enumerate(parts):
            if "export" in p or "匯出" in p:
                args = parts[i+1:]
                break
        _route_cli_cmd({"cmd": "/export", "args": args}, session_manager, ui_event_queue, acc_cmd_queue, tts_cmd_queue)
    elif "import" in text or "匯入" in text:
        parts = text.split()
        args = []
        for i, p in enumerate(parts):
            if "import" in p or "匯入" in p:
                args = parts[i+1:]
                break
        _route_cli_cmd({"cmd": "/import", "args": args}, session_manager, ui_event_queue, acc_cmd_queue, tts_cmd_queue)
    elif "stop" in text or "停止" in text:
        _route_cli_cmd({"cmd": "/stop"}, session_manager, ui_event_queue, acc_cmd_queue, tts_cmd_queue)
    elif "show" in text or "顯示" in text:
        _route_cli_cmd({"cmd": "/show"}, session_manager, ui_event_queue, acc_cmd_queue, tts_cmd_queue)
    elif "clear" in text or "清除" in text:
        if "buffer" in text or "暫存" in text:
            _route_cli_cmd({"cmd": "/clear", "args": ["buffer"]}, session_manager, ui_event_queue, acc_cmd_queue, tts_cmd_queue)
        else:
            _route_cli_cmd({"cmd": "/clear"}, session_manager, ui_event_queue, acc_cmd_queue, tts_cmd_queue)
    else:
        ui_event_queue.put(UiEvent("message", {"role": "system", "text": f"無法識別的語音指令: {text}"}))


if __name__ == "__main__":
    main()
