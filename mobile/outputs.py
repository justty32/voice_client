"""mobile/outputs.py — WebSocket 輸出推送迴圈（全域唯一 pusher，B6）。

推送來源只有 `state.ui_event_queue`：核心模組的 ui_event／tts／tts_ctl 已由
mobile/edge.py 的 EdgeSink 轉成前端事件放入，邊緣 helper（mobile/push.py）也直接放入。
另外：app_ctl（手機無 /exit）消費後丟棄；對話清單變動時補推 sessions。
"""

import asyncio
import logging
import queue

from mobile.push import _push_sessions_refresh
from mobile.state import MobileState

log = logging.getLogger("mobile_server")


def _sessions_snapshot(state: MobileState) -> tuple:
    sm = state.session_manager
    return tuple(sm.list_sessions()), sm.current_title or ""


def _expand(state: MobileState, event: dict) -> dict:
    """sessions_refresh 於送出當下展開成完整 sessions 清單；其他事件原樣。"""
    if event["type"] == "sessions_refresh":
        snapshot = _sessions_snapshot(state)
        state.sessions_snapshot = snapshot
        return {"type": "sessions", "list": list(snapshot[0]), "current": snapshot[1]}
    return event


async def _flush_ui_events(state: MobileState, ws) -> None:
    """把暫存（先前送失敗）與 ui_event_queue 的事件依序送往 ws。

    B6：send_json 失敗時事件放回 pending_events 頭，下一輪優先重送，不再丟棄。
    """
    while True:
        if state.pending_events:
            event = state.pending_events.popleft()
        elif not state.ui_event_queue.empty():
            event = state.ui_event_queue.get_nowait()
        else:
            return
        data = _expand(state, event)  # 展開失敗沿用舊行為：由外層記 log、事件丟棄
        try:
            await ws.send_json(data)
        except Exception as exc:
            state.pending_events.appendleft(event)
            log.warning("Output pusher send failed, event kept for retry: %s", exc)
            return


def _drain_app_ctl(state: MobileState) -> None:
    """app_ctl（EXIT）在手機無意義：消費後丟棄。"""
    while True:
        try:
            payload = state.parts.app_ctl.get_nowait()
        except queue.Empty:
            return
        log.debug("mobile: 丟棄 app_ctl %r", payload)


async def _output_pusher(state: MobileState):
    """每 50ms 把 ui_event_queue 推送至 state.current_ws（唯一的最新連線）。

    整個伺服器只有一個 pusher（lifespan 建立，B6）；無人連線時不消費 queue，
    事件留到下一條連線再送。對話清單（/new、/switch、/delete、/rename、/load…）
    與上次推送的快照不同時補推 sessions（桌面沒有此事件）。
    """
    while True:
        ws = state.current_ws
        if ws is not None:
            try:
                _drain_app_ctl(state)
                await _flush_ui_events(state, ws)
                if (state.sessions_snapshot is not None
                        and _sessions_snapshot(state) != state.sessions_snapshot):
                    _push_sessions_refresh(state)
                    await _flush_ui_events(state, ws)
            except Exception as exc:
                log.error("Output pusher error: %s", exc)

        await asyncio.sleep(0.05)
