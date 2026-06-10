"""modules.chat_flow — 聊天回應處理、摘要決策與重播模組。

消費三個 topic：
- inbound     : HTTP 回應字典（type="ChatReply"/"StatusUpdate"/"Error"）
- summary_out : 摘要器輸出（type="status"/"summary"）
- chat_ctl    : 控制指令（cmd="play_last"）

ChatReply 收到後依 SLM 設定決定走直接 TTS 或送出摘要請求；
summary_out 的摘要結果以「回覆摘要：{text}」格式呈現；
chat_ctl play_last 重播最後一次完整助理回覆原文。
語意與 main.py _route_response（346-389）及 F1 段落（208-218）、
PLAY_LAST（138-141）一致。
"""

import logging

from core.message import Message
from core.module import TunnelModule

log = logging.getLogger(__name__)


class ChatFlow(TunnelModule):
    """聊天流模組：歷史寫入、摘要決策、狀態呈現、重播。"""

    name = "chat_flow"
    consumes = ("inbound", "summary_out", "chat_ctl")

    def __init__(self, session_manager, summary_threshold: int = 20, slm_enabled: bool = True):
        super().__init__()
        self._sm = session_manager
        self._summary_threshold = summary_threshold
        self._slm_enabled = slm_enabled
        self._last_full_response: str = ""

    @property
    def last_full_response(self) -> str:
        """最後一次收到的完整助理回覆（唯讀）。"""
        return self._last_full_response

    # ── 主分派 ────────────────────────────────────────────────────────────────

    def handle(self, message: Message) -> None:
        if message.topic == "inbound":
            self._handle_inbound(message.payload)
        elif message.topic == "summary_out":
            self._handle_summary_out(message.payload)
        elif message.topic == "chat_ctl":
            self._handle_chat_ctl(message.payload)

    # ── inbound 處理 ──────────────────────────────────────────────────────────

    def _handle_inbound(self, payload: dict) -> None:
        resp_type = payload.get("type", "ChatReply")

        if resp_type == "ChatReply":
            self._handle_chat_reply(payload)
        elif resp_type == "StatusUpdate":
            self._handle_status_update(payload)
        elif resp_type == "Error":
            self._handle_error(payload)

    def _handle_chat_reply(self, payload: dict) -> None:
        content = payload.get("Content", {})
        full_response = content.get("full_response", "")

        if full_response:
            # 寫入會話歷史
            self._sm.add_message("assistant", full_response)
            # 顯示助理訊息
            self.emit("ui_event", {"type": "message", "role": "assistant", "text": full_response})
            # 記錄供重播
            self._last_full_response = full_response
            # 摘要決策
            if not self._slm_enabled or len(full_response) < self._summary_threshold:
                self.emit("tts", {"text": full_response, "priority": "medium"})
            else:
                self.emit("summary_req", {
                    "cmd": "summary",
                    "text": full_response,
                    "title": self._sm.current_title,
                })

        # 不論回覆是否為空，最後均發送待機狀態（main.py:375-377）
        self.emit("ui_event", {"type": "status", "text": "待機"})

    def _handle_status_update(self, payload: dict) -> None:
        text = payload.get("text", "")
        self.emit("ui_event", {"type": "status", "text": text})
        self.emit("tts", {"text": text, "priority": "low"})

    def _handle_error(self, payload: dict) -> None:
        msg = payload.get("message", "Unknown error")
        self.emit("ui_event", {"type": "message", "role": "system", "text": f"[錯誤] {msg}"})
        self.emit("tts", {"text": f"發生錯誤：{msg}", "priority": "high"})

    # ── summary_out 處理 ──────────────────────────────────────────────────────

    def _handle_summary_out(self, payload: dict) -> None:
        type_ = payload.get("type", "")
        if type_ == "status":
            self.emit("ui_event", {"type": "status", "text": payload.get("text", "")})
        elif type_ == "summary":
            display = f"回覆摘要：{payload['text']}"
            self.emit("ui_event", {"type": "message", "role": "summary", "text": display})
            self.emit("tts", {"text": display, "priority": "medium"})

    # ── chat_ctl 處理 ─────────────────────────────────────────────────────────

    def _handle_chat_ctl(self, payload: dict) -> None:
        cmd = payload.get("cmd", "")
        if cmd == "play_last":
            if self._last_full_response:
                self.emit("ui_event", {
                    "type": "message",
                    "role": "system",
                    "text": "播放最後一次回覆原文",
                })
                self.emit("tts", {"text": self._last_full_response, "priority": "medium"})
        else:
            log.debug("chat_ctl: 未知指令 %r，忽略", cmd)
