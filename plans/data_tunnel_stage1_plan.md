# 資料隧道階段①：core/ 框架本體 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 建立「生產者／消費者＋佇列」框架本體（core/ 套件），含完整單元與整合測試，不接任何業務模組。

**Architecture:** 模組透過自己的 Outbox（生產）與 Inbox（消費）介接；單執行緒的 Exchange 依路由表（topic → Inbox）搬移資料，每次 tick 最多搬一筆。TunnelModule 基底類別提供 attach／emit／消費迴圈與錯誤隔離。

**Tech Stack:** Python 3.10+ 標準庫（queue、threading、dataclasses、logging）、unittest。

**設計文件:** `plans/data_tunnel_design.md`（已定案）。
**後續:** 階段②〜⑤（語音資料流、指令流、聊天流、呈現層）待本階段完成後各自另寫計畫。

---

## 檔案結構

```
core/
  __init__.py    （空檔，套件宣告）
  message.py     Message 資料類別：topic、payload、source、created_at
  endpoint.py    Outbox / Inbox：模組與交換核心的唯一介接點
  exchange.py    Exchange：路由表＋單執行緒交換迴圈
  module.py      TunnelModule：生產者／消費者基底類別
tests/
  test_core_message.py
  test_core_endpoint.py
  test_core_exchange.py
  test_core_module.py
  test_core_integration.py
```

注意：設計文件原列有 `channel.py`（具名佇列）；實作上「通道」即 Exchange 路由表中的 topic 註冊，不需要獨立類別。Task 1 會同步修訂設計文件。

---

### Task 1: 修訂設計文件 + 建立 core 套件 + Message 資料類別

**Files:**
- Modify: `plans/data_tunnel_design.md`（「框架本體」一節）
- Create: `core/__init__.py`
- Create: `core/message.py`
- Test: `tests/test_core_message.py`

- [ ] **Step 1: 修訂設計文件中的 core/ 檔案列表**

在 `plans/data_tunnel_design.md` 中，把：

```
core/
  message.py    Message：topic、payload、source、時間戳
  channel.py    Channel：具名佇列（thread-safe），框架內部使用
  endpoint.py   Outbox / Inbox：模組與交換核心的唯一介接點
  exchange.py   Exchange：單執行緒交換迴圈＋路由表（topic → 消費者 inbox）
  module.py     TunnelModule 基底類別：宣告 produces / consumes，管理自身執行緒
```

改為：

```
core/
  message.py    Message：topic、payload、source、時間戳
  endpoint.py   Outbox / Inbox：模組與交換核心的唯一介接點
  exchange.py   Exchange：單執行緒交換迴圈＋路由表（topic → 消費者 inbox）
                ※「通道」即路由表中的 topic 註冊，不需獨立的 channel 類別
  module.py     TunnelModule 基底類別：宣告 consumes，管理自身執行緒
```

- [ ] **Step 2: 寫失敗測試**

建立 `tests/test_core_message.py`：

```python
"""core.Message 單元測試。

執行：python3 -m unittest tests.test_core_message
"""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.message import Message


class TestMessage(unittest.TestCase):
    def test_required_fields(self):
        msg = Message(topic="raw_text", payload="hello")
        self.assertEqual(msg.topic, "raw_text")
        self.assertEqual(msg.payload, "hello")
        self.assertEqual(msg.source, "")

    def test_created_at_auto(self):
        before = time.time()
        msg = Message(topic="t", payload=None)
        self.assertGreaterEqual(msg.created_at, before)
        self.assertLessEqual(msg.created_at, time.time())

    def test_source(self):
        msg = Message(topic="t", payload=1, source="stt")
        self.assertEqual(msg.source, "stt")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 3: 執行測試，確認失敗**

Run: `python3 -m unittest tests.test_core_message -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'core'`）

- [ ] **Step 4: 最小實作**

建立空的 `core/__init__.py`，再建立 `core/message.py`：

```python
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
```

- [ ] **Step 5: 執行測試，確認通過**

Run: `python3 -m unittest tests.test_core_message -v`
Expected: PASS（3 tests OK）

- [ ] **Step 6: Commit**

```bash
git add plans/data_tunnel_design.md core/__init__.py core/message.py tests/test_core_message.py
git commit -m "feat(階段①): core 套件與 Message 資料類別"
```

---

### Task 2: Outbox / Inbox 端點

**Files:**
- Create: `core/endpoint.py`
- Test: `tests/test_core_endpoint.py`

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_core_endpoint.py`：

```python
"""core.endpoint（Outbox / Inbox）單元測試。

執行：python3 -m unittest tests.test_core_endpoint
"""

import os
import queue
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.endpoint import Inbox, Outbox


class TestOutbox(unittest.TestCase):
    def test_put_then_get(self):
        ob = Outbox()
        ob.put("a")
        self.assertEqual(ob.get_nowait(), "a")

    def test_fifo_order(self):
        ob = Outbox()
        ob.put("a")
        ob.put("b")
        self.assertEqual(ob.get_nowait(), "a")
        self.assertEqual(ob.get_nowait(), "b")

    def test_get_empty_raises(self):
        with self.assertRaises(queue.Empty):
            Outbox().get_nowait()

    def test_empty(self):
        ob = Outbox()
        self.assertTrue(ob.empty())
        ob.put("x")
        self.assertFalse(ob.empty())


class TestInbox(unittest.TestCase):
    def test_put_then_get(self):
        ib = Inbox()
        ib.put_nowait("a")
        self.assertEqual(ib.get_nowait(), "a")

    def test_get_with_timeout_raises_when_empty(self):
        with self.assertRaises(queue.Empty):
            Inbox().get(timeout=0.01)

    def test_empty(self):
        ib = Inbox()
        self.assertTrue(ib.empty())
        ib.put_nowait("x")
        self.assertFalse(ib.empty())


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 執行測試，確認失敗**

Run: `python3 -m unittest tests.test_core_endpoint -v`
Expected: FAIL（`ModuleNotFoundError` 或 `ImportError`）

- [ ] **Step 3: 最小實作**

建立 `core/endpoint.py`：

```python
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
```

- [ ] **Step 4: 執行測試，確認通過**

Run: `python3 -m unittest tests.test_core_endpoint -v`
Expected: PASS（7 tests OK）

- [ ] **Step 5: Commit**

```bash
git add core/endpoint.py tests/test_core_endpoint.py
git commit -m "feat(階段①): Outbox / Inbox 端點"
```

---

### Task 3: Exchange 註冊與 tick 路由（同步核心）

**Files:**
- Create: `core/exchange.py`
- Test: `tests/test_core_exchange.py`

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_core_exchange.py`：

```python
"""core.Exchange 單元測試。

執行：python3 -m unittest tests.test_core_exchange
"""

import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.endpoint import Inbox, Outbox
from core.exchange import Exchange
from core.message import Message


class TestExchangeRouting(unittest.TestCase):
    def setUp(self):
        self.ex = Exchange()
        self.ob = Outbox()
        self.ib = Inbox()
        self.ex.register_producer("p1", self.ob)
        self.ex.register_consumer("topic_a", self.ib)

    def test_tick_moves_exactly_one_message(self):
        self.ob.put(Message(topic="topic_a", payload=1))
        self.ob.put(Message(topic="topic_a", payload=2))
        self.assertTrue(self.ex.tick())
        self.assertEqual(self.ib.get_nowait().payload, 1)
        self.assertTrue(self.ib.empty())  # 一次只搬一筆

    def test_tick_empty_returns_false(self):
        self.assertFalse(self.ex.tick())

    def test_duplicate_consumer_raises(self):
        with self.assertRaises(ValueError):
            self.ex.register_consumer("topic_a", Inbox())

    def test_unrouted_topic_is_dropped(self):
        self.ob.put(Message(topic="nobody", payload=1))
        self.assertTrue(self.ex.tick())   # 丟棄也算做了一個動作
        self.assertFalse(self.ex.tick())  # 訊息已被取出丟棄，不殘留

    def test_round_robin_between_producers(self):
        ob2 = Outbox()
        ib2 = Inbox()
        self.ex.register_producer("p2", ob2)
        self.ex.register_consumer("topic_b", ib2)
        self.ob.put(Message(topic="topic_a", payload="A"))
        ob2.put(Message(topic="topic_b", payload="B"))
        self.assertTrue(self.ex.tick())
        self.assertTrue(self.ex.tick())
        self.assertEqual(self.ib.get_nowait().payload, "A")
        self.assertEqual(ib2.get_nowait().payload, "B")

    def test_broken_producer_does_not_block_others(self):
        bad = mock.Mock()
        bad.get_nowait.side_effect = RuntimeError("boom")
        ex = Exchange()
        ex.register_producer("bad", bad)
        ob, ib = Outbox(), Inbox()
        ex.register_producer("good", ob)
        ex.register_consumer("t", ib)
        ob.put(Message(topic="t", payload="ok"))
        self.assertTrue(ex.tick())
        self.assertEqual(ib.get_nowait().payload, "ok")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 執行測試，確認失敗**

Run: `python3 -m unittest tests.test_core_exchange -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'core.exchange'`）

- [ ] **Step 3: 最小實作**

建立 `core/exchange.py`（本 Task 先不含 start/stop 執行緒，Task 4 補上）：

```python
"""core.exchange — 單執行緒交換核心。

所有 Outbox → Inbox 的搬移只由 Exchange 的執行緒執行，
每次 tick 最多搬一筆（一次交換一個資料）。
"""

import logging
import queue
import time

from core.endpoint import Inbox, Outbox

log = logging.getLogger("core.exchange")


class Exchange:
    def __init__(self, idle_sleep: float = 0.01):
        self._outboxes: list[tuple[str, Outbox]] = []
        self._routes: dict[str, Inbox] = {}
        self._idle_sleep = idle_sleep
        self._rr = 0  # round-robin 起點，避免固定順序餓死後面的生產者

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
```

- [ ] **Step 4: 執行測試，確認通過**

Run: `python3 -m unittest tests.test_core_exchange -v`
Expected: PASS（6 tests OK）

- [ ] **Step 5: Commit**

```bash
git add core/exchange.py tests/test_core_exchange.py
git commit -m "feat(階段①): Exchange 路由表與一次一筆 tick 交換"
```

---

### Task 4: Exchange 執行緒生命週期

**Files:**
- Modify: `core/exchange.py`
- Test: `tests/test_core_exchange.py`（追加測試類別）

- [ ] **Step 1: 寫失敗測試**

在 `tests/test_core_exchange.py` 檔案末尾（`if __name__ == "__main__":` 之前）追加：

```python
class TestExchangeLifecycle(unittest.TestCase):
    def test_start_stop_moves_messages(self):
        ex = Exchange(idle_sleep=0.001)
        ob, ib = Outbox(), Inbox()
        ex.register_producer("p", ob)
        ex.register_consumer("t", ib)
        ex.start()
        try:
            ob.put(Message(topic="t", payload="hi"))
            msg = ib.get(timeout=1)
            self.assertEqual(msg.payload, "hi")
        finally:
            ex.stop()

    def test_stop_joins_thread(self):
        ex = Exchange(idle_sleep=0.001)
        ex.start()
        ex.stop()
        self.assertIsNone(ex._thread)

    def test_loop_survives_broken_producer(self):
        ex = Exchange(idle_sleep=0.001)
        bad = mock.Mock()
        bad.get_nowait.side_effect = RuntimeError("boom")
        ex.register_producer("bad", bad)
        ob, ib = Outbox(), Inbox()
        ex.register_producer("good", ob)
        ex.register_consumer("t", ib)
        ex.start()
        try:
            ob.put(Message(topic="t", payload="ok"))
            self.assertEqual(ib.get(timeout=1).payload, "ok")
        finally:
            ex.stop()
```

- [ ] **Step 2: 執行測試，確認失敗**

Run: `python3 -m unittest tests.test_core_exchange -v`
Expected: 新增 3 個測試 FAIL（`AttributeError: 'Exchange' object has no attribute 'start'`），原 6 個 PASS

- [ ] **Step 3: 實作生命週期**

修改 `core/exchange.py`：import 區塊補上 `import threading`，`__init__` 末尾補上兩行：

```python
        self._running = False
        self._thread: threading.Thread | None = None
```

並在類別末尾（`tick` 之後）追加：

```python
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
```

- [ ] **Step 4: 執行測試，確認通過**

Run: `python3 -m unittest tests.test_core_exchange -v`
Expected: PASS（9 tests OK）

- [ ] **Step 5: Commit**

```bash
git add core/exchange.py tests/test_core_exchange.py
git commit -m "feat(階段①): Exchange 單執行緒交換迴圈（start/stop、例外不中斷）"
```

---

### Task 5: TunnelModule 基底類別

**Files:**
- Create: `core/module.py`
- Test: `tests/test_core_module.py`

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_core_module.py`：

```python
"""core.TunnelModule 單元測試。

執行：python3 -m unittest tests.test_core_module
"""

import os
import queue
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.exchange import Exchange
from core.message import Message
from core.module import TunnelModule


class EchoConsumer(TunnelModule):
    name = "echo"
    consumes = ("ping",)

    def __init__(self):
        super().__init__()
        self.received = []

    def handle(self, message):
        self.received.append(message.payload)
        self.emit("pong", message.payload)


class BoomConsumer(TunnelModule):
    name = "boom"
    consumes = ("ping",)

    def handle(self, message):
        raise RuntimeError("炸了")


def wait_outbox(testcase, module, timeout=1.0):
    """輪詢模組 outbox 直到取得一筆訊息，逾時則 fail。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            return module.outbox.get_nowait()
        except queue.Empty:
            time.sleep(0.005)
    testcase.fail("outbox 逾時無資料")


class TestTunnelModule(unittest.TestCase):
    def test_emit_wraps_message(self):
        m = EchoConsumer()
        m.emit("ping", {"a": 1})
        msg = m.outbox.get_nowait()
        self.assertIsInstance(msg, Message)
        self.assertEqual(msg.topic, "ping")
        self.assertEqual(msg.payload, {"a": 1})
        self.assertEqual(msg.source, "echo")

    def test_attach_registers_producer_and_consumer(self):
        ex = Exchange()
        m = EchoConsumer()
        m.attach(ex)
        # emit 進自己的 outbox，經 tick 路由回自己的 inbox（echo 訂閱 ping）
        m.emit("ping", "x")
        self.assertTrue(ex.tick())
        self.assertEqual(m.inbox.get_nowait().payload, "x")

    def test_consume_loop_calls_handle(self):
        m = EchoConsumer()
        m.start()
        try:
            m.inbox.put_nowait(Message(topic="ping", payload="hello"))
            msg = wait_outbox(self, m)
            self.assertEqual(msg.topic, "pong")
            self.assertEqual(msg.payload, "hello")
            self.assertEqual(m.received, ["hello"])
        finally:
            m.stop()

    def test_handle_exception_emits_ui_event(self):
        m = BoomConsumer()
        m.start()
        try:
            m.inbox.put_nowait(Message(topic="ping", payload="x"))
            msg = wait_outbox(self, m)
            self.assertEqual(msg.topic, "ui_event")
            self.assertEqual(msg.payload["type"], "message")
            self.assertIn("boom", msg.payload["text"])
        finally:
            m.stop()

    def test_handle_exception_does_not_kill_loop(self):
        m = BoomConsumer()
        m.start()
        try:
            m.inbox.put_nowait(Message(topic="ping", payload="第一筆"))
            wait_outbox(self, m)  # 第一筆的錯誤 ui_event
            m.inbox.put_nowait(Message(topic="ping", payload="第二筆"))
            msg = wait_outbox(self, m)  # 迴圈仍在運作，產出第二筆的錯誤
            self.assertEqual(msg.topic, "ui_event")
        finally:
            m.stop()

    def test_stop_joins_thread(self):
        m = EchoConsumer()
        m.start()
        m.stop()
        self.assertIsNone(m._thread)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 執行測試，確認失敗**

Run: `python3 -m unittest tests.test_core_module -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'core.module'`）

- [ ] **Step 3: 最小實作**

建立 `core/module.py`：

```python
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
```

- [ ] **Step 4: 執行測試，確認通過**

Run: `python3 -m unittest tests.test_core_module -v`
Expected: PASS（6 tests OK）

- [ ] **Step 5: Commit**

```bash
git add core/module.py tests/test_core_module.py
git commit -m "feat(階段①): TunnelModule 基底類別（attach/emit/消費迴圈/錯誤隔離)"
```

---

### Task 6: 端到端整合測試

**Files:**
- Test: `tests/test_core_integration.py`

- [ ] **Step 1: 寫整合測試**

建立 `tests/test_core_integration.py`：

```python
"""core 框架端到端整合測試：假生產者 → Exchange → 假消費者。

執行：python3 -m unittest tests.test_core_integration
"""

import os
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.exchange import Exchange
from core.module import TunnelModule


class FakeStt(TunnelModule):
    """純生產者：模擬 STT 不斷產出 raw_text。"""
    name = "fake_stt"


class FakeWorkspace(TunnelModule):
    """消費者：模擬當前工作區收集 raw_text。"""
    name = "fake_workspace"
    consumes = ("raw_text",)

    def __init__(self):
        super().__init__()
        self.texts = []

    def handle(self, message):
        self.texts.append(message.payload)


class RelayRouter(TunnelModule):
    """同時是消費者＋生產者：收到 command 後轉發控制訊息。"""
    name = "fake_router"
    consumes = ("commands",)

    def handle(self, message):
        if message.payload == "record_toggle":
            self.emit("recorder_ctl", "START")


class CtlCollector(TunnelModule):
    name = "fake_recorder"
    consumes = ("recorder_ctl",)

    def __init__(self):
        super().__init__()
        self.ctls = []

    def handle(self, message):
        self.ctls.append(message.payload)


def wait_until(predicate, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class TestEndToEnd(unittest.TestCase):
    def test_producer_to_consumer_preserves_order(self):
        ex = Exchange(idle_sleep=0.001)
        stt = FakeStt()
        ws = FakeWorkspace()
        stt.attach(ex)
        ws.attach(ex)
        ex.start()
        ws.start()
        try:
            for i in range(5):
                stt.emit("raw_text", f"句子{i}")
            self.assertTrue(wait_until(lambda: len(ws.texts) == 5))
            self.assertEqual(ws.texts, [f"句子{i}" for i in range(5)])
        finally:
            ws.stop()
            ex.stop()

    def test_consumer_can_also_produce(self):
        ex = Exchange(idle_sleep=0.001)
        keys = FakeStt()  # 借用純生產者模擬熱鍵
        router = RelayRouter()
        rec = CtlCollector()
        keys.attach(ex)
        router.attach(ex)
        rec.attach(ex)
        ex.start()
        router.start()
        rec.start()
        try:
            keys.emit("commands", "record_toggle")
            self.assertTrue(wait_until(lambda: rec.ctls == ["START"]))
        finally:
            rec.stop()
            router.stop()
            ex.stop()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 執行整合測試，確認通過**

Run: `python3 -m unittest tests.test_core_integration -v`
Expected: PASS（2 tests OK）——框架程式碼在前面任務已完成，本任務只驗證整合行為。

- [ ] **Step 3: 跑全部測試（含既有測試，確認沒弄壞任何東西）**

Run: `python3 -m unittest discover -s tests -v`
Expected: 全部 PASS（既有 7 個測試檔 + 新增 5 個測試檔）

- [ ] **Step 4: Commit**

```bash
git add tests/test_core_integration.py
git commit -m "test(階段①): core 框架端到端整合測試"
```

---

## 完成定義（Definition of Done）

- [ ] `core/` 五個檔案（`__init__.py`、`message.py`、`endpoint.py`、`exchange.py`、`module.py`）全部就位
- [ ] `python3 -m unittest discover -s tests` 全綠
- [ ] 既有功能不受影響（本階段不動任何既有模組與 `main.py`）
- [ ] 設計文件 `plans/data_tunnel_design.md` 與實作一致（channel.py 已修訂）

完成後進入階段②（語音資料流遷移），另寫 `plans/data_tunnel_stage2_plan.md`。
