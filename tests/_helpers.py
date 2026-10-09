"""測試共用工具（非測試模組；檔名以底線開頭，不會被 discover 收集）。

用法：from tests._helpers import make_sm, drain, wait_until, drain_queue
"""

import configparser
import os
import queue
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from session_manager import SessionManager


def make_sm(tmp: str) -> SessionManager:
    """建立指向 tmp 目錄的 SessionManager，並預建 default session。"""
    cfg = configparser.ConfigParser()
    cfg["WORKSPACE"] = {
        "sessions_file": os.path.join(tmp, "output", ".sessions.json"),
        "deleted_sessions_dir": os.path.join(tmp, "output", "deleted"),
    }
    sm = SessionManager(cfg)
    sm.new_session("default")
    return sm


def drain(module) -> list:
    """取出模組 outbox 中所有訊息，回傳 list[Message]。"""
    msgs = []
    while True:
        try:
            msgs.append(module.outbox.get_nowait())
        except queue.Empty:
            break
    return msgs


def wait_until(predicate, timeout=3.0):
    """輪詢直到謂詞成立或逾時；回傳 True/False。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


def drain_queue(q: queue.Queue) -> list:
    """取出佇列中所有現有項目，回傳 list。"""
    items = []
    while True:
        try:
            items.append(q.get_nowait())
        except queue.Empty:
            break
    return items
