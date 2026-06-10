"""core.endpoint — 模組與交換核心之間的唯一介接點。

Outbox：模組（生產者）放入，只有交換核心取出。
Inbox ：只有交換核心放入，模組（消費者）取出。
兩者都包裝 thread-safe 的 queue.Queue；「資料交換單執行緒、一次一筆」
由 Exchange 保證——佇列之間的搬移只發生在 Exchange 的執行緒。
"""

import queue


class Outbox:
    def __init__(self):
        self._q = queue.Queue()

    def put(self, message) -> None:
        """模組端：生產一筆訊息。"""
        self._q.put(message)

    def get_nowait(self):
        """交換核心專用：取出一筆，無資料時拋出 queue.Empty。"""
        return self._q.get_nowait()

    def empty(self) -> bool:
        return self._q.empty()


class Inbox:
    def __init__(self):
        self._q = queue.Queue()

    def put_nowait(self, message) -> None:
        """交換核心專用：投遞一筆訊息。"""
        self._q.put_nowait(message)

    def get(self, timeout: float | None = None):
        """模組端：阻塞取出一筆，逾時拋出 queue.Empty。"""
        return self._q.get(timeout=timeout)

    def get_nowait(self):
        return self._q.get_nowait()

    def empty(self) -> bool:
        return self._q.empty()
