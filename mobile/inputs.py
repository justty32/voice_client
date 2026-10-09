"""mobile/inputs.py — 前端輸入轉送：音訊 blob、文字、斜線指令、訊號與剪貼簿。

全部轉送進 build_core() 的 legacy queue（與桌面同一條 Data Tunnel）：

| 前端 | queue | 桌面對應 |
|---|---|---|
| binary frame | recorder_event（recording_stopped, flushed）＋ audio_out | Recorder |
| text | cli_text | TerminalInput 文字 |
| cmd | cli_cmd（command(cmd, args)） | TerminalInput 指令 |
| signal | key_signal（QUICK_SEND／FORCE_STOP_TTS） | 熱鍵 |
| clipboard_data | 直接寫入當前工作區 | `_handle_paste` 後半 |

`/exit`（手機無此功能）與 `/paste`（需瀏覽器往返）在邊緣攔截，不送 CommandRouter。
"""

import json
import logging

from mobile.audio import _to_wav
from mobile.push import _push, _push_system
from mobile.state import MobileState
from protocol import payloads as P
from protocol.commands import HOTKEY_FORCE_STOP_TTS, HOTKEY_QUICK_SEND

log = logging.getLogger("mobile_server")

# 前端可送的熱鍵訊號（錄音由瀏覽器控制，不轉送 RECORD_* 類）。
_MOBILE_SIGNALS = frozenset({HOTKEY_QUICK_SEND, HOTKEY_FORCE_STOP_TTS})


def _handle_audio(state: MobileState, data: bytes):
    """在 thread 中執行音訊轉換（pydub 為同步操作）。

    先送 recording_stopped（flushed=True）讓 CommandRouter 顯示「處理中」，
    轉檔成功後送 audio_out → VoiceToText → stt_event 讓狀態列回「待機」；
    轉檔失敗則送 recorder_event error（CommandRouter 顯示「[錄音錯誤] …」並回「待機」）。
    """
    q = state.parts.queues
    q["recorder_event"].put(P.recorder_event("recording_stopped", flushed=True))
    wav, err = _to_wav(data)
    if wav:
        q["audio_out"].put(wav)
        log.debug("Audio queued (%d bytes raw)", len(data))
    else:
        q["recorder_event"].put(P.recorder_event("error", message=err or "音訊轉換失敗"))


def _handle_text(state: MobileState, raw: str):
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return
    if not isinstance(data, dict):
        return

    t = data.get("type")
    if t == "text":
        content = str(data.get("content", "")).strip()
        if content:
            state.parts.queues["cli_text"].put(content)
    elif t == "cmd":
        _route_cmd(state, data.get("cmd", ""), data.get("args", []))
    elif t == "signal":
        _route_signal(state, data.get("signal", ""))
    elif t == "clipboard_data":
        # 前端讀取瀏覽器剪貼簿後回傳的內容 → 貼到當前工作區
        _mobile_paste(state, data.get("text", ""))


def _mobile_paste(state: MobileState, text: str):
    """把前端回傳的剪貼簿文字貼到當前工作區（每個非空行為一筆；文案同桌面 /paste）。"""
    lines = [ln.strip() for ln in str(text).splitlines() if ln.strip()]
    wm = state.wm
    name = wm.current
    ws = wm.get(name)
    for line in lines:
        ws.append(line)  # Workspace 自帶鎖（階段 3），可與 WorkspaceManager 執行緒並行
    _push_system(state, f"[系統] 已從剪貼簿貼上 {len(lines)} 筆到 {name} 工作區。")


def _route_signal(state: MobileState, signal: str):
    if signal in _MOBILE_SIGNALS:
        state.parts.queues["key_signal"].put(signal)
    else:
        log.debug("mobile: 忽略未知訊號 %r", signal)


def _route_cmd(state: MobileState, cmd: str, args):
    if not isinstance(args, list):
        args = []
    if cmd == "/exit":
        # 手機沒有 /exit（不可讓瀏覽器關掉伺服器）
        _push_system(state, f"未知指令: {cmd}")
        return
    if cmd == "/paste":
        # 請前端讀取剪貼簿並回傳 clipboard_data；不送 CommandRouter，避免「[錯誤] 等待瀏覽器回傳」
        _push(state, {"type": "clipboard_read"})
        return
    state.parts.queues["cli_cmd"].put(P.command(cmd, [str(a) for a in args]))
