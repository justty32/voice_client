"""CommandRouter 單元測試共用工具（非測試模組）。

用法：from tests._router_helpers import make_router, cmd, voice, ui_texts
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.message import Message
from modules.command_router import CommandRouter
from modules.workspace_manager import WorkspaceManager
from tests._helpers import drain, make_sm


def make_router(tmp: str, sm=None) -> tuple:
    """回傳 (router, wm, sm)；export_dir 指向 tmp。"""
    wm = WorkspaceManager()
    if sm is None:
        sm = make_sm(tmp)
    router = CommandRouter(workspace_manager=wm, session_manager=sm, export_dir=tmp)
    return router, wm, sm


def cmd(router, cmd_str: str, args: list = None):
    """送出一個 /cmd 指令並回傳所有輸出訊息。"""
    payload = {"cmd": cmd_str, "args": args if args is not None else []}
    router.handle(Message(topic="commands", payload=payload))
    return drain(router)


def voice(router, text: str) -> list:
    """送出一個 voice 語音指令並回傳所有輸出訊息。"""
    payload = {"cmd": "voice", "args": [text]}
    router.handle(Message(topic="commands", payload=payload))
    return drain(router)


def ui_texts(msgs) -> list:
    """從訊息列表中擷取所有 ui_event message 的 text 欄位。"""
    return [
        m.payload["text"]
        for m in msgs
        if m.topic == "ui_event"
        and m.payload.get("type") == "message"
        and "text" in m.payload
    ]
