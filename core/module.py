"""core.module — 生產者／消費者模組基底類別。

每個模組同時擁有 outbox（生產）與 inbox（消費）：
- 純生產者：不宣告 consumes、不呼叫 start()，自行在背景執行緒呼叫 emit()。
- 消費者：宣告 consumes 並覆寫 handle()，start() 後基底迴圈逐筆取出處理。
- 同時身兼兩者：在 handle() 內呼叫 emit() 即可。

handle() 拋出例外不會中斷消費迴圈，錯誤會轉為 ui_event 訊息發布。
"""

import logging
import queue
import threading

from core.endpoint import Inbox, Outbox
from core.message import Message

log = logging.getLogger("core.module")


class TunnelModule:
    name: str = "module"
    consumes: tuple = ()

    def __init__(self):
        self.outbox = Outbox()
        self.inbox = Inbox()
        self._running = False
        self._thread: threading.Thread | None = None

    # ── 接線 ──────────────────────────────────────────────────────
    def attach(self, exchange) -> None:
        exchange.register_producer(self.name, self.outbox)
        for topic in self.consumes:
            exchange.register_consumer(topic, self.inbox)

    # ── 生產 ──────────────────────────────────────────────────────
    def emit(self, topic: str, payload) -> None:
        self.outbox.put(Message(topic=topic, payload=payload, source=self.name))

    # ── 消費（基底執行緒迴圈）──────────────────────────────────────
    def start(self) -> None:
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._run, name=self.name, daemon=True)
        self._thread.start()

    def _run(self) -> None:
        while self._running:
            try:
                msg = self.inbox.get(timeout=0.1)
            except queue.Empty:
                continue
            try:
                self.handle(msg)
            except Exception:
                log.exception("%s 處理失敗: topic=%s", self.name, msg.topic)
                self.emit("ui_event", {
                    "type": "message",
                    "role": "system",
                    "text": f"[{self.name} 錯誤] 處理 {msg.topic} 失敗",
                })

    def handle(self, message: Message) -> None:
        raise NotImplementedError

    def stop(self) -> None:
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None
