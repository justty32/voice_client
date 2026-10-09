"""protocol.commands — `commands` 通道的指令集單一事實來源。

斜線指令（終端輸入）、對話管理指令子集、熱鍵訊號與其正規化名稱集中於此；
terminal_input、local_control、keyboard_listener、CommandRouter 一律從這裡取用。
只依賴標準庫。值沿用既有線上格式（behavior-preserving）。
"""

# 終端可辨識的斜線指令（不在此集合者，terminal_input 送 {"cmd":"unknown"}）。
SLASH_COMMANDS: frozenset = frozenset({
    "/new", "/switch", "/list", "/exit", "/help", "/clear", "/show", "/send",
    "/stop", "/export", "/import", "/delete", "/save", "/concat", "/to_top",
    "/load", "/rename", "/history", "/ws", "/copy", "/paste", "/del", "/move",
})

# 需要 SessionManager 的對話管理指令；未接 SessionManager 時回友善訊息。
SESSION_COMMANDS: frozenset = frozenset({
    "/new", "/switch", "/list", "/delete", "/rename", "/history", "/save", "/load",
})

# 熱鍵訊號（裸字串 payload）：keyboard_listener 與 local_control 的生產者白名單。
HOTKEY_RECORD_TOGGLE = "RECORD_TOGGLE"
HOTKEY_RECORD_COMMAND_TOGGLE = "RECORD_COMMAND_TOGGLE"
HOTKEY_QUICK_SEND = "QUICK_SEND"
HOTKEY_FORCE_STOP_TTS = "FORCE_STOP_TTS"
HOTKEY_PLAY_LAST_ORIGINAL = "PLAY_LAST_ORIGINAL"

# 熱鍵訊號 → CommandRouter 內部標準化 cmd 名稱。
HOTKEY_TO_CMD: dict = {
    HOTKEY_RECORD_TOGGLE: "record_toggle",
    HOTKEY_RECORD_COMMAND_TOGGLE: "record_command_toggle",
    HOTKEY_QUICK_SEND: "quick_send",
    HOTKEY_FORCE_STOP_TTS: "force_stop_tts",
    HOTKEY_PLAY_LAST_ORIGINAL: "play_last",
}

HOTKEY_SIGNALS: frozenset = frozenset(HOTKEY_TO_CMD)
