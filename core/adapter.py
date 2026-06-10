"""core.adapter — 既有模組（裸 queue.Queue 介面）與交換核心的橋接。

讓沿用中的執行緒模組（Recorder、VoiceToText…）不需改寫即可掛上 Exchange：
  - OutboxAdapter：把模組既有的「輸出 queue」偽裝成 Outbox；
    交換核心取出時把原始項目包裝成 Message（固定 topic 與 source）。
  - InboxAdapter ：把模組既有的「輸入 queue」偽裝成 Inbox；
    交換核心投遞時解開 Message、把 payload（或 transform(payload)）放進原始 queue。
    transform 選用參數供階段⑤接線用，例如 TuiRenderer 需要的 dict→UiEvent 轉換。

Exchange 只依賴 get_nowait()/put_nowait()/empty() 鴨子型別，故可直接註冊。
"""

import queue

from core.message import Message


class OutboxAdapter:
    def __init__(self, raw_queue: queue.Queue, topic: str, source: str = ""):
        self._q = raw_queue
        self._topic = topic
        self._source = source

    def get_nowait(self) -> Message:
        """取出一筆原始項目並包裝為 Message；無資料時拋出 queue.Empty。"""
        item = self._q.get_nowait()
        return Message(topic=self._topic, payload=item, source=self._source)

    def empty(self) -> bool:
        return self._q.empty()


class InboxAdapter:
    def __init__(self, raw_queue: queue.Queue, transform=None):
        """
        Args:
            raw_queue: 既有模組的輸入 queue。
            transform: 可選的 payload 轉換函式（callable，接受 payload 回傳新值）。
                       例如 TuiRenderer 接線時傳入 dict→UiEvent 的工廠函式；
                       None（預設）表示直接投遞原始 payload，維持舊行為不變。
        """
        self._q = raw_queue
        self._transform = transform

    def put_nowait(self, message: Message) -> None:
        """解開 Message，把 payload（或 transform(payload)）投遞進既有模組的輸入 queue。"""
        if self._transform is not None:
            self._q.put_nowait(self._transform(message.payload))
        else:
            self._q.put_nowait(message.payload)

    def empty(self) -> bool:
        return self._q.empty()
