"""modules.stt_gate — 語音指令模式分流閘。

消費 stt_text 與 gate_ctl 兩個 topic：
- gate_ctl 訊息依 {"mode": "normal"|"command"} 切換內部模式；非法值忽略。
- stt_text 訊息依當前模式分流：
  - normal  → 先 emit ui_event {"type":"message","role":"voice","text":text}
              讓使用者看到辨識結果（對齊 main.py:168），
              再 emit raw_text（進 WorkspaceManager）。
  - command → emit commands {"cmd": "voice", "args": [text]}（進 CommandRouter）；
              [語音指令] 的 UI 顯示由 CommandRouter 負責，此處不重複發射。
  空白文字（strip() 為空）兩種模式下均直接丟棄，不發任何訊息。

模式在語音指令轉發後維持 command，直到 gate_ctl 切換為止，
與 main.py 舊版 is_command_mode 旗標語意一致。
"""

import logging

from core.message import Message
from core.module import TunnelModule

log = logging.getLogger(__name__)

_VALID_MODES = frozenset({"normal", "command"})


class SttGate(TunnelModule):
    name = "stt_gate"
    consumes = ("stt_text", "gate_ctl")

    def __init__(self):
        super().__init__()
        self._mode = "normal"

    @property
    def mode(self) -> str:
        """當前模式（唯讀）：'normal' 或 'command'。"""
        return self._mode

    def handle(self, message: Message) -> None:
        if message.topic == "gate_ctl":
            self._handle_gate_ctl(message.payload)
        elif message.topic == "stt_text":
            self._handle_stt_text(message.payload)

    def _handle_gate_ctl(self, payload) -> None:
        if not isinstance(payload, dict):
            log.warning("gate_ctl: payload 非 dict，忽略：%r", payload)
            return
        mode = payload.get("mode")
        if mode not in _VALID_MODES:
            log.warning("gate_ctl: 未知 mode 值 %r，忽略", mode)
            return
        self._mode = mode

    def _handle_stt_text(self, text: str) -> None:
        if not text.strip():
            return
        if self._mode == "normal":
            # 先讓使用者看到辨識結果（port main.py:168）
            self.emit("ui_event", {"type": "message", "role": "voice", "text": text})
            self.emit("raw_text", text)
        else:
            self.emit("commands", {"cmd": "voice", "args": [text]})
