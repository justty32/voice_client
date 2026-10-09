"""手機伺服器測試共用工具（非測試模組；檔名以底線開頭，不會被 discover 收集）。

替身元件與 `make_state()` 位於 `tests/_mobile_fakes.py`（不需 fastapi，於此 re-export）；
本檔另提供帶逾時的 WebSocket 收訊輔助。需要 fastapi（TestClient 另需 httpx）。
"""

import json
import os
import sys
import time
import warnings

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import anyio  # noqa: E402  fastapi/starlette 的依賴
from starlette.websockets import WebSocketDisconnect  # noqa: E402

with warnings.catch_warnings():
    # starlette 新版建議改用 httpx2；目前 .venv 用 httpx，僅抑制此提示
    warnings.simplefilter("ignore")
    from fastapi.testclient import TestClient  # noqa: E402,F401

from tests._mobile_fakes import (  # noqa: E402,F401  re-export
    FakeHttpClient,
    FakeSummary,
    FakeVoiceToText,
    make_config,
    make_state,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATIC_DIR = os.path.join(REPO_ROOT, "static")


def recv(ws, timeout: float = 2.0) -> dict:
    """收一則伺服器訊息（JSON）；伺服器關閉連線時拋 WebSocketDisconnect，逾時拋 TimeoutError。"""

    async def _receive():
        with anyio.fail_after(timeout):
            return await ws._send_rx.receive()

    message = ws.portal.call(_receive)
    if message["type"] == "websocket.close":
        raise WebSocketDisconnect(code=message.get("code", 1000), reason=message.get("reason", ""))
    return json.loads(message["text"])


def recv_until(ws, pred, timeout: float = 2.0) -> tuple[dict, list[dict]]:
    """輪詢直到收到符合 pred 的訊息；回傳 (該訊息, 期間收到的全部訊息含該則)。"""
    seen: list[dict] = []
    deadline = time.monotonic() + timeout
    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f"逾時未收到預期訊息；已收到：{seen}")
        msg = recv(ws, remaining)
        seen.append(msg)
        if pred(msg):
            return msg, seen


def is_type(t: str, **fields):
    """產生謂詞：訊息 type 為 t 且各欄位相等。"""

    def _pred(m: dict) -> bool:
        return m.get("type") == t and all(m.get(k) == v for k, v in fields.items())

    return _pred
