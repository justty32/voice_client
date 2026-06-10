"""core.exchange — 單執行緒交換核心。

所有 Outbox → Inbox 的搬移只由 Exchange 的執行緒執行，
每次 tick 最多搬一筆（一次交換一個資料）。
"""

import logging
import queue
import threading
import time

from core.endpoint import Inbox, Outbox

log = logging.getLogger("core.exchange")


class Exchange:
    def __init__(self, idle_sleep: float = 0.01):
        self._outboxes: list[tuple[str, Outbox]] = []
        self._routes: dict[str, Inbox] = {}
        self._idle_sleep = idle_sleep
        self._rr = 0  # round-robin 起點，避免固定順序餓死後面的生產者
        self._running = False
        self._thread: threading.Thread | None = None

    # ── 註冊 ──────────────────────────────────────────────────────
    def register_producer(self, name: str, outbox: Outbox) -> None:
        self._outboxes.append((name, outbox))

    def register_consumer(self, topic: str, inbox: Inbox) -> None:
        if topic in self._routes:
            raise ValueError(f"topic 已有消費者: {topic}")
        self._routes[topic] = inbox

    # ── 交換 ──────────────────────────────────────────────────────
    def tick(self) -> bool:
        """執行一次交換：最多搬一筆。回傳是否有搬移（或丟棄）。"""
        n = len(self._outboxes)
        for i in range(n):
            idx = (self._rr + i) % n
            name, outbox = self._outboxes[idx]
            try:
                msg = outbox.get_nowait()
            except queue.Empty:
                continue
            except Exception:
                log.exception("讀取 %s 的 outbox 失敗，跳過", name)
                continue
            self._rr = (idx + 1) % n
            inbox = self._routes.get(msg.topic)
            if inbox is None:
                log.warning("topic=%s 無消費者（來源 %s），丟棄", msg.topic, name)
                return True
            inbox.put_nowait(msg)
            log.debug("%s --[%s]--> consumer", name, msg.topic)
            return True
        return False

    # ── 生命週期 ───────────────────────────────────────────────────
    def start(self) -> None:
        self._running = True
        self._thread = threading.Thread(target=self._run, name="exchange", daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while self._running:
            try:
                moved = self.tick()
            except Exception:
                log.exception("exchange tick 失敗")
                moved = False
            if not moved:
                time.sleep(self._idle_sleep)

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
