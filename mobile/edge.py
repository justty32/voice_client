"""mobile/edge.py — 手機的「邊緣裝置」：把 Data Tunnel 的消費端 queue 接到 WebSocket 推送。

桌面由 TuiRenderer／AudioPriorityPlayer／Recorder 消費 `ui_event_q`、`tts_input`、`tts_cmd`、
`recorder_cmd`；手機改用 `EdgeSink` 代替這些 queue（經 `build_core(queues=...)` 注入），
Exchange 投遞時立刻轉成前端事件放進**同一條**輸出 queue（`MobileState.ui_event_queue`），
因此 ui_event 與 tts 之間的先後順序與 Exchange 投遞順序一致。

前端事件型別（`static/app.js`）：message／status／clear／tts／tts_control／
clipboard_write／clipboard_read／sessions。本模組不依賴 MobileState，避免循環匯入。
"""

import logging

from protocol import payloads as P

log = logging.getLogger("mobile_server")


class EdgeSink:
    """偽裝成 queue 的投遞端：put 時以 `convert(payload)` 轉成 WS 事件；回傳 None 表示丟棄。

    只實作 InboxAdapter 會用到的 put_nowait／empty（另附 put 供邊緣直接呼叫）。
    """

    def __init__(self, out_q, convert, name: str = ""):
        self._out = out_q
        self._convert = convert
        self._name = name

    def put_nowait(self, item) -> None:
        event = self._convert(item)
        if event is None:
            log.debug("mobile edge: 丟棄 %s payload %r", self._name, item)
            return
        self._out.put_nowait(event)

    put = put_nowait

    def empty(self) -> bool:
        return self._out.empty()


# ── payload → WS 事件 ───────────────────────────────────────────────

def ui_event_to_ws(payload):
    """ui_event dict（status／message／clear）原樣推送；非 dict 以 system 訊息顯示。"""
    if isinstance(payload, dict):
        return payload
    return P.ui_message("system", str(payload))


def tts_to_ws(payload):
    """tts {"text","priority"} → {"type":"tts","text","priority"}（瀏覽器 SpeechSynthesis 播放）。"""
    if not isinstance(payload, dict):
        return None
    return {"type": "tts", "text": payload.get("text", ""),
            "priority": payload.get("priority", "medium")}


def tts_cmd_to_ws(payload):
    """tts_ctl：STOP_SPEECH → tts_control stop；TERMINATE 等其他值丟棄。"""
    if payload == P.TTS_STOP_SPEECH:
        return {"type": "tts_control", "action": "stop"}
    return None


def discard(_payload):
    """手機不控桌面錄音：recorder_ctl 消費後丟棄。"""
    return None


# ── 剪貼簿（瀏覽器往返）────────────────────────────────────────────

class BrowserClipboard:
    """注入 CommandRouter 的剪貼簿：copy 推 clipboard_write；paste 推 clipboard_read。

    瀏覽器回傳的 clipboard_data 由 `mobile/inputs.py:_mobile_paste` 完成貼上；
    `/paste` 指令在邊緣先攔截（不經 CommandRouter），因此 paste() 只在語音指令路徑才會被呼叫。
    """

    WAITING = "等待瀏覽器回傳"

    def __init__(self, out_q):
        self._out = out_q

    def copy(self, text: str) -> tuple[bool, str]:
        self._out.put_nowait({"type": "clipboard_write", "text": text})
        return True, ""

    def paste(self) -> tuple[bool, str]:
        self._out.put_nowait({"type": "clipboard_read"})
        return False, self.WAITING
