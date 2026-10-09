"""modules.chat_flow — 聊天回應處理、摘要決策與重播模組。

消費三個 topic：
- inbound     : HTTP 回應字典（type="ChatReply"/"StatusUpdate"/"Error"）
- summary_out : 摘要器輸出（type="status"/"summary"/"summary_failed"）
- chat_ctl    : 控制指令（cmd="play_last"）

ChatReply 收到後依 SLM 設定決定走直接 TTS 或送出摘要請求；
summary_out 的摘要結果以「回覆摘要：{text}」格式呈現，摘要失敗時提示並改播原文；
chat_ctl play_last 重播最後一次完整助理回覆原文。
語意與 main.py _route_response（346-389）及 F1 段落（208-218）、
PLAY_LAST（138-141）一致。
"""

import logging

from core.message import Message
from core.module import TunnelModule
from protocol import payloads as P
from protocol import topics as T

log = logging.getLogger(__name__)


class ChatFlow(TunnelModule):
    """聊天流模組：歷史寫入、摘要決策、狀態呈現、重播。"""

    name = "chat_flow"
    consumes = (T.INBOUND, T.SUMMARY_OUT, T.CHAT_CTL)

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
        if message.topic == T.INBOUND:
            self._handle_inbound(message.payload)
        elif message.topic == T.SUMMARY_OUT:
            self._handle_summary_out(message.payload)
        elif message.topic == T.CHAT_CTL:
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
            self.emit(T.UI_EVENT, P.ui_message("assistant", full_response))
            # 記錄供重播
            self._last_full_response = full_response
            # 摘要決策
            if not self._slm_enabled or len(full_response) < self._summary_threshold:
                self.emit(T.TTS, P.tts_item(full_response, "medium"))
            else:
                self.emit(T.SUMMARY_REQ, P.summary_request(full_response, self._sm.current_title))

        # 不論回覆是否為空，最後均發送待機狀態（main.py:375-377）
        self.emit(T.UI_EVENT, P.ui_status("待機"))

    def _handle_status_update(self, payload: dict) -> None:
        text = payload.get("text", "")
        self.emit(T.UI_EVENT, P.ui_status(text))
        if text:
            self.emit(T.TTS, P.tts_item(text, "low"))

    def _handle_error(self, payload: dict) -> None:
        msg = payload.get("message", "Unknown error")
        self.emit(T.UI_EVENT, P.ui_message("system", f"[錯誤] {msg}"))
        self.emit(T.TTS, P.tts_item(f"發生錯誤：{msg}", "high"))

    # ── summary_out 處理 ──────────────────────────────────────────────────────

    def _handle_summary_out(self, payload: dict) -> None:
        type_ = payload.get("type", "")
        if type_ == "status":
            self.emit(T.UI_EVENT, P.ui_status(payload.get("text", "")))
        elif type_ == "summary":
            display = f"回覆摘要：{payload.get('text', '')}"
            self.emit(T.UI_EVENT, P.ui_message("summary", display))
            self.emit(T.TTS, P.tts_item(display, "medium"))
        elif type_ == "summary_failed":
            # 摘要失敗不可無聲：提示並改播原文（B14）
            message = payload.get("message", "未知錯誤")
            self.emit(T.UI_EVENT, P.ui_message("system", f"[摘要失敗] {message}，改播原文"))
            text = payload.get("text", "")
            if text:
                self.emit(T.TTS, P.tts_item(text, "medium"))

    # ── chat_ctl 處理 ─────────────────────────────────────────────────────────

    def _handle_chat_ctl(self, payload: dict) -> None:
        cmd = payload.get("cmd", "")
        if cmd == "play_last":
            if self._last_full_response:
                self.emit(T.UI_EVENT, P.ui_message("system", "播放最後一次回覆原文"))
                self.emit(T.TTS, P.tts_item(self._last_full_response, "medium"))
        else:
            log.debug("chat_ctl: 未知指令 %r，忽略", cmd)
