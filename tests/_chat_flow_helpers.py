"""ChatFlow 單元測試共用訊息建構工具（非測試模組）。

用法：from tests._chat_flow_helpers import inbound, summary_out, chat_ctl
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.message import Message


def inbound(type_: str, **kwargs) -> Message:
    payload = {"type": type_}
    payload.update(kwargs)
    return Message(topic="inbound", payload=payload)


def summary_out(type_: str, text: str) -> Message:
    return Message(topic="summary_out", payload={"type": type_, "text": text})


def chat_ctl(cmd: str) -> Message:
    return Message(topic="chat_ctl", payload={"cmd": cmd})
