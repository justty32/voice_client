"""mobile/push.py — 邊緣直接推送 WS 事件到 state.ui_event_queue 的 helper。

核心模組的 ui_event／tts 由 Exchange 經 mobile/edge.py 的 EdgeSink 進入同一條 queue；
這裡只給手機邊緣自己產生的事件（連線初始狀態、剪貼簿、sessions 等）使用。
"""

from mobile.state import MobileState
from protocol import payloads as P


def _push(state: MobileState, event: dict):
    state.ui_event_queue.put(event)

def _push_msg(state: MobileState, role: str, text: str):
    _push(state, P.ui_message(role, text))

def _push_status(state: MobileState, text: str):
    _push(state, P.ui_status(text))

def _push_system(state: MobileState, text: str):
    _push_msg(state, "system", text)

def _push_sessions_refresh(state: MobileState):
    """sessions_refresh 於送出當下由 pusher 展開成完整 sessions 清單（mobile/outputs.py:_expand）。"""
    _push(state, {"type": "sessions_refresh"})
