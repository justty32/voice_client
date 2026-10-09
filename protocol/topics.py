"""protocol.topics — Data Tunnel 的 18 個 topic 名稱常數。

值即線上字串，修改任何一個都是協定變更：須同步生產者、消費者、
app_wiring/topology.py、接線測試與 docs/architecture/topics.md。
codemap（workflows/common/code-map/codemap.py）會讀本檔解析常數。
"""

# ── 語音與輸入 ────────────────────────────────────────────────────
AUDIO = "audio"
STT_TEXT = "stt_text"
RAW_TEXT = "raw_text"
COMMANDS = "commands"
CLI_TEXT = "cli_text"
RECORDER_EVENT = "recorder_event"
STT_EVENT = "stt_event"

# ── 控制 ──────────────────────────────────────────────────────────
GATE_CTL = "gate_ctl"
APP_CTL = "app_ctl"
RECORDER_CTL = "recorder_ctl"
TTS_CTL = "tts_ctl"
CHAT_CTL = "chat_ctl"

# ── 聊天與呈現 ────────────────────────────────────────────────────
OUTBOUND = "outbound"
INBOUND = "inbound"
SUMMARY_REQ = "summary_req"
SUMMARY_OUT = "summary_out"
TTS = "tts"
UI_EVENT = "ui_event"

ALL: frozenset = frozenset({
    AUDIO, STT_TEXT, RAW_TEXT, COMMANDS, CLI_TEXT, RECORDER_EVENT, STT_EVENT,
    GATE_CTL, APP_CTL, RECORDER_CTL, TTS_CTL, CHAT_CTL,
    OUTBOUND, INBOUND, SUMMARY_REQ, SUMMARY_OUT, TTS, UI_EVENT,
})
