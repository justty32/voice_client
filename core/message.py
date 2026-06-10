"""core.message — 資料隧道中流動的訊息。"""

import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Message:
    topic: str
    payload: Any
    source: str = ""
    created_at: float = field(default_factory=time.time)
