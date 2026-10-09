"""protocol.payloads — topic payload 建構函式與控制字串常數。

所有值沿用既有線上格式（behavior-preserving）；建構函式只負責組出
與舊碼完全相同的 dict，不做驗證。
"""

# ── 控制字串（裸字串 payload）──────────────────────────────────────
RECORDER_START = "START"          # recorder_ctl
RECORDER_STOP = "STOP"            # recorder_ctl
TTS_STOP_SPEECH = "STOP_SPEECH"   # tts_ctl
TTS_TERMINATE = "TERMINATE"       # tts_cmd queue（app.py 停機時直接放入）
APP_EXIT = "EXIT"                 # app_ctl

# ui_event message 的 role：TuiRenderer 支援的全部值。
# 桌面目前的生產者只用 system／assistant／summary／voice／user／sending；
# error、buffer_peek 只有 TuiRenderer 支援、桌面無生產者。
UI_ROLES: frozenset = frozenset({
    "system", "assistant", "summary", "voice", "user", "sending",
    "error", "buffer_peek",
})


# ── ui_event ──────────────────────────────────────────────────────
def ui_status(text: str) -> dict:
    """狀態列：{"type":"status","text":...}。"""
    return {"type": "status", "text": text}


def ui_message(role: str, text: str) -> dict:
    """訊息：{"type":"message","role":...,"text":...}。"""
    return {"type": "message", "role": role, "text": text}


def ui_clear() -> dict:
    """清畫面：{"type":"clear"}。"""
    return {"type": "clear"}


# ── commands / recorder_event / stt_event / gate_ctl / chat_ctl ───────────────
def command(cmd: str, args=()) -> dict:
    """commands 指令：{"cmd":...,"args":[...]}（args 一律轉 list）。"""
    return {"cmd": cmd, "args": list(args)}


def recorder_event(event: str, **extra) -> dict:
    """recorder_event：{"event":..., 其他欄位如 message、flushed}。

    recording_stopped 帶 flushed: bool（本次停止是否有音訊送往 STT）。
    """
    return {"event": event, **extra}


def stt_event(event: str, **extra) -> dict:
    """stt_event：{"event":"stt_error"|"stt_empty"|"stt_done", 其他欄位如 message}。"""
    return {"event": event, **extra}


def gate_mode(mode: str) -> dict:
    """gate_ctl：{"mode":"normal"|"command"}。"""
    return {"mode": mode}


def chat_cmd(cmd: str) -> dict:
    """chat_ctl：{"cmd":...}（目前只有 play_last）。"""
    return {"cmd": cmd}


# ── tts / summary_req / outbound ──────────────────────────────────
def tts_item(text: str, priority: str) -> dict:
    """tts：{"text":...,"priority":"high"|"medium"|"low"}。"""
    return {"text": text, "priority": priority}


def summary_request(text: str, title) -> dict:
    """summary_req：{"cmd":"summary","text":...,"title":...}。"""
    return {"cmd": "summary", "text": text, "title": title}


def outbound_chat(content: str, title: str, client_time: str) -> dict:
    """outbound：伺服器協定使用大寫鍵 Content／Title／Metadata.ClientTime。"""
    return {
        "Content": content,
        "Title": title,
        "Metadata": {"ClientTime": client_time},
    }
