# 資料隧道階段②：語音資料流 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 讓語音資料流（Recorder →`audio`→ STT →`raw_text`→ 當前工作區）跑在 core/ 框架上，且不修改任何既有硬體模組。

**Architecture:** 既有模組（record.py、voice_to_text.py）以裸 `queue.Queue` 溝通——本階段新增**佇列轉接器**（`core/adapter.py`）把既有 queue 偽裝成 Outbox/Inbox 掛上 Exchange，模組本體零修改。新業務消費者 `WorkspaceManager`（`modules/`）原生繼承 TunnelModule，作為 `raw_text` 的唯一消費者，持有多個 Workspace 與「當前」指標。`main.py` 本階段不動。

**Tech Stack:** Python 標準庫、既有 `workspace.Workspace`、unittest。

**設計文件:** `plans/data_tunnel_design.md`。**前置:** 階段①已完成（core/ 框架）。

---

## 檔案結構

```
core/
  adapter.py                 OutboxAdapter / InboxAdapter（既有 queue ↔ 隧道橋接）
modules/
  __init__.py                （空檔，套件宣告）
  workspace_manager.py       WorkspaceManager：raw_text 唯一消費者
tests/
  test_core_adapter.py
  test_workspace_manager.py
  test_voice_flow_integration.py
```

接線慣例（沿階段①審查結論）：**先 attach／register，再 start**。

---

### Task 1: 佇列轉接器（OutboxAdapter / InboxAdapter）

**Files:**
- Create: `core/adapter.py`
- Test: `tests/test_core_adapter.py`

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_core_adapter.py`：

```python
"""core.adapter（OutboxAdapter / InboxAdapter）單元測試。

執行：python3 -m unittest tests.test_core_adapter
"""

import os
import queue
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.adapter import InboxAdapter, OutboxAdapter
from core.endpoint import Inbox
from core.exchange import Exchange
from core.message import Message


class TestOutboxAdapter(unittest.TestCase):
    def test_wraps_raw_item_into_message(self):
        raw = queue.Queue()
        adapter = OutboxAdapter(raw, topic="raw_text", source="legacy_stt")
        raw.put("哈囉")
        msg = adapter.get_nowait()
        self.assertIsInstance(msg, Message)
        self.assertEqual(msg.topic, "raw_text")
        self.assertEqual(msg.payload, "哈囉")
        self.assertEqual(msg.source, "legacy_stt")

    def test_get_empty_raises(self):
        adapter = OutboxAdapter(queue.Queue(), topic="t")
        with self.assertRaises(queue.Empty):
            adapter.get_nowait()

    def test_empty_reflects_raw_queue(self):
        raw = queue.Queue()
        adapter = OutboxAdapter(raw, topic="t")
        self.assertTrue(adapter.empty())
        raw.put(b"audio-bytes")
        self.assertFalse(adapter.empty())


class TestInboxAdapter(unittest.TestCase):
    def test_unwraps_payload_into_raw_queue(self):
        raw = queue.Queue()
        adapter = InboxAdapter(raw)
        adapter.put_nowait(Message(topic="audio", payload=b"wav"))
        self.assertEqual(raw.get_nowait(), b"wav")

    def test_empty_reflects_raw_queue(self):
        raw = queue.Queue()
        adapter = InboxAdapter(raw)
        self.assertTrue(adapter.empty())
        adapter.put_nowait(Message(topic="t", payload=1))
        self.assertFalse(adapter.empty())


class TestAdaptersOnExchange(unittest.TestCase):
    def test_legacy_queues_route_through_exchange(self):
        """既有模組的輸出 queue → Exchange → 既有模組的輸入 queue，全程零改寫。"""
        legacy_out = queue.Queue()   # 模擬 Recorder 的 audio_queue（輸出側）
        legacy_in = queue.Queue()    # 模擬 VoiceToText 的 audio_queue（輸入側）
        ex = Exchange()
        ex.register_producer("recorder", OutboxAdapter(legacy_out, topic="audio", source="recorder"))
        ex.register_consumer("audio", InboxAdapter(legacy_in))
        legacy_out.put(b"chunk-1")
        self.assertTrue(ex.tick())
        self.assertEqual(legacy_in.get_nowait(), b"chunk-1")

    def test_adapter_and_native_inbox_coexist(self):
        """轉接器生產者可以路由到原生 Inbox 消費者。"""
        legacy_out = queue.Queue()
        ib = Inbox()
        ex = Exchange()
        ex.register_producer("legacy", OutboxAdapter(legacy_out, topic="raw_text"))
        ex.register_consumer("raw_text", ib)
        legacy_out.put("你好")
        self.assertTrue(ex.tick())
        self.assertEqual(ib.get_nowait().payload, "你好")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 執行測試，確認失敗**

Run: `python3 -m unittest tests.test_core_adapter -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'core.adapter'`）

- [ ] **Step 3: 最小實作**

建立 `core/adapter.py`：

```python
"""core.adapter — 既有模組（裸 queue.Queue 介面）與交換核心的橋接。

讓沿用中的執行緒模組（Recorder、VoiceToText…）不需改寫即可掛上 Exchange：
  - OutboxAdapter：把模組既有的「輸出 queue」偽裝成 Outbox；
    交換核心取出時把原始項目包裝成 Message（固定 topic 與 source）。
  - InboxAdapter ：把模組既有的「輸入 queue」偽裝成 Inbox；
    交換核心投遞時解開 Message、只把 payload 放進原始 queue。

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
    def __init__(self, raw_queue: queue.Queue):
        self._q = raw_queue

    def put_nowait(self, message: Message) -> None:
        """解開 Message，把 payload 投遞進既有模組的輸入 queue。"""
        self._q.put_nowait(message.payload)

    def empty(self) -> bool:
        return self._q.empty()
```

- [ ] **Step 4: 執行測試，確認通過**

Run: `python3 -m unittest tests.test_core_adapter -v`
Expected: PASS（7 tests OK）

- [ ] **Step 5: Commit**

```bash
git add core/adapter.py tests/test_core_adapter.py
git commit -m "feat(階段②): 佇列轉接器（既有模組零改寫掛上 Exchange）"
```

---

### Task 2: WorkspaceManager（raw_text 唯一消費者）

**Files:**
- Create: `modules/__init__.py`
- Create: `modules/workspace_manager.py`
- Test: `tests/test_workspace_manager.py`

- [ ] **Step 1: 寫失敗測試**

建立 `tests/test_workspace_manager.py`：

```python
"""modules.WorkspaceManager 單元測試。

執行：python3 -m unittest tests.test_workspace_manager
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.exchange import Exchange
from core.message import Message
from modules.workspace_manager import WorkspaceManager


class TestWorkspaceManager(unittest.TestCase):
    def setUp(self):
        self.wm = WorkspaceManager()

    def test_default_workspaces_and_current(self):
        self.assertEqual(sorted(self.wm.names()), ["buffer", "stt"])
        self.assertEqual(self.wm.current, "buffer")

    def test_handle_appends_to_current_workspace(self):
        self.wm.handle(Message(topic="raw_text", payload="第一句"))
        self.assertEqual(self.wm.get("buffer").lines(), ["第一句"])
        self.assertTrue(self.wm.get("stt").is_empty())

    def test_switch_changes_consumer_target(self):
        self.assertTrue(self.wm.switch("stt"))
        self.wm.handle(Message(topic="raw_text", payload="到 stt"))
        self.assertEqual(self.wm.get("stt").lines(), ["到 stt"])
        self.assertTrue(self.wm.get("buffer").is_empty())

    def test_switch_unknown_returns_false_and_keeps_current(self):
        self.assertFalse(self.wm.switch("nothing"))
        self.assertEqual(self.wm.current, "buffer")

    def test_invalid_initial_current_raises(self):
        with self.assertRaises(ValueError):
            WorkspaceManager(current="nope")

    def test_consumes_raw_text_on_exchange(self):
        ex = Exchange()
        self.wm.attach(ex)
        self.wm.outbox.put(Message(topic="raw_text", payload="經過交換核心"))
        # wm 自己也是生產者；用自己的 outbox 餵 raw_text 回自己的 inbox
        self.assertTrue(ex.tick())
        self.assertEqual(self.wm.inbox.get_nowait().payload, "經過交換核心")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 執行測試，確認失敗**

Run: `python3 -m unittest tests.test_workspace_manager -v`
Expected: FAIL（`ModuleNotFoundError: No module named 'modules'`）

- [ ] **Step 3: 最小實作**

建立空的 `modules/__init__.py`，再建立 `modules/workspace_manager.py`：

```python
"""modules.workspace_manager — 工作區管理者。

raw_text 通道的唯一消費者：持有多個具名工作區與「當前工作區」指標，
新的辨識文字只會進入當前工作區。切換目標靠 switch()（之後由
CommandRouter 在階段③接上 /ws 指令）。
"""

from core.message import Message
from core.module import TunnelModule
from workspace import Workspace


class WorkspaceManager(TunnelModule):
    name = "workspace_manager"
    consumes = ("raw_text",)

    DEFAULT_NAMES = ("buffer", "stt")

    def __init__(self, names: tuple = DEFAULT_NAMES, current: str = "buffer"):
        super().__init__()
        self._spaces = {n: Workspace(n) for n in names}
        if current not in self._spaces:
            raise ValueError(f"未知工作區: {current}")
        self._current = current

    # ── 查詢 ──────────────────────────────────────────────────────
    @property
    def current(self) -> str:
        return self._current

    def names(self) -> list:
        return list(self._spaces)

    def get(self, name: str) -> Workspace | None:
        return self._spaces.get(name)

    # ── 操作 ──────────────────────────────────────────────────────
    def switch(self, name: str) -> bool:
        """切換當前工作區；未知名稱回 False 且不變更。"""
        if name not in self._spaces:
            return False
        self._current = name
        return True

    # ── 消費 ──────────────────────────────────────────────────────
    def handle(self, message: Message) -> None:
        self._spaces[self._current].append(message.payload)
```

- [ ] **Step 4: 執行測試，確認通過**

Run: `python3 -m unittest tests.test_workspace_manager -v`
Expected: PASS（6 tests OK）

- [ ] **Step 5: Commit**

```bash
git add modules/__init__.py modules/workspace_manager.py tests/test_workspace_manager.py
git commit -m "feat(階段②): WorkspaceManager — raw_text 唯一消費者與當前工作區指標"
```

---

### Task 3: 語音資料流整合測試

**Files:**
- Test: `tests/test_voice_flow_integration.py`

- [ ] **Step 1: 寫整合測試**

建立 `tests/test_voice_flow_integration.py`：

```python
"""語音資料流整合測試：模擬既有模組（裸 queue＋自有執行緒）經轉接器上隧道。

驗證階段②目標：Recorder →audio→ STT →raw_text→ 當前工作區，
其中「Recorder」「STT」用與既有模組相同的介面形態（裸 queue.Queue），
完全不依賴 record.py / voice_to_text.py 的硬體與模型。

執行：python3 -m unittest tests.test_voice_flow_integration
"""

import os
import queue
import sys
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from core.adapter import InboxAdapter, OutboxAdapter
from core.exchange import Exchange
from modules.workspace_manager import WorkspaceManager


class FakeLegacyStt:
    """形態同 voice_to_text.VoiceToText：裸輸入/輸出 queue＋自有工作執行緒。"""

    def __init__(self, audio_queue: queue.Queue, text_queue: queue.Queue):
        self._audio_queue = audio_queue
        self._text_queue = text_queue
        self._running = False
        self._thread = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False
        if self._thread is not None:
            self._thread.join(timeout=2)
            self._thread = None

    def _loop(self):
        while self._running:
            try:
                chunk = self._audio_queue.get(timeout=0.05)
            except queue.Empty:
                continue
            self._text_queue.put(f"辨識[{chunk.decode()}]")


def wait_until(predicate, timeout=2.0):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.01)
    return False


class TestVoiceFlow(unittest.TestCase):
    def setUp(self):
        # 既有模組形態的裸 queue
        self.recorder_audio_out = queue.Queue()  # 模擬 Recorder 的輸出
        self.stt_audio_in = queue.Queue()        # FakeLegacyStt 的輸入
        self.stt_text_out = queue.Queue()        # FakeLegacyStt 的輸出

        self.stt = FakeLegacyStt(self.stt_audio_in, self.stt_text_out)
        self.wm = WorkspaceManager()

        self.ex = Exchange(idle_sleep=0.001)
        self.ex.register_producer(
            "recorder", OutboxAdapter(self.recorder_audio_out, topic="audio", source="recorder"))
        self.ex.register_consumer("audio", InboxAdapter(self.stt_audio_in))
        self.ex.register_producer(
            "stt", OutboxAdapter(self.stt_text_out, topic="raw_text", source="stt"))
        self.wm.attach(self.ex)

        self.ex.start()
        self.stt.start()
        self.wm.start()

    def tearDown(self):
        self.wm.stop()
        self.stt.stop()
        self.ex.stop()

    def test_audio_reaches_current_workspace_as_text(self):
        self.recorder_audio_out.put(b"hello")
        self.assertTrue(wait_until(lambda: self.wm.get("buffer").count() == 1))
        self.assertEqual(self.wm.get("buffer").lines(), ["辨識[hello]"])
        self.assertTrue(self.wm.get("stt").is_empty())

    def test_switch_redirects_following_texts(self):
        self.recorder_audio_out.put(b"one")
        self.assertTrue(wait_until(lambda: self.wm.get("buffer").count() == 1))
        self.wm.switch("stt")
        self.recorder_audio_out.put(b"two")
        self.assertTrue(wait_until(lambda: self.wm.get("stt").count() == 1))
        self.assertEqual(self.wm.get("buffer").lines(), ["辨識[one]"])
        self.assertEqual(self.wm.get("stt").lines(), ["辨識[two]"])

    def test_order_preserved_under_burst(self):
        for i in range(10):
            self.recorder_audio_out.put(f"c{i}".encode())
        self.assertTrue(wait_until(lambda: self.wm.get("buffer").count() == 10))
        self.assertEqual(
            self.wm.get("buffer").lines(),
            [f"辨識[c{i}]" for i in range(10)],
        )


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: 執行整合測試，確認通過**

Run: `python3 -m unittest tests.test_voice_flow_integration -v`
Expected: PASS（3 tests OK）

- [ ] **Step 3: 跑全部測試**

Run: `python3 -m unittest discover -s tests`
Expected: 全部 PASS（149 既有 + 16 新增 = 165 左右，以實際為準；0 failures）

- [ ] **Step 4: Commit**

```bash
git add tests/test_voice_flow_integration.py
git commit -m "test(階段②): 語音資料流整合測試（轉接器＋WorkspaceManager）"
```

---

### Task 4: 文件同步

**Files:**
- Modify: `plans/data_tunnel_design.md`（框架本體 core/ 列表）
- Modify: `docs/architecture.md`（框架表格與遷移路線圖）

- [ ] **Step 1: 設計文件補上 adapter.py**

在 `plans/data_tunnel_design.md` 的 core/ 列表中，`endpoint.py` 那行之後加入：

```
  adapter.py    OutboxAdapter / InboxAdapter：既有裸 queue 模組的零改寫橋接
```

- [ ] **Step 2: 架構文檔更新**

在 `docs/architecture.md`：

a) 第 2 節表格 `core/module.py` 之後加一列：

```
| `core/adapter.py` | `OutboxAdapter`／`InboxAdapter`：把既有模組的裸 queue 偽裝成 Outbox/Inbox，零改寫掛上 Exchange |
```

b) 第 5 節表格中 `record.py`、`voice_to_text.py` 那列的「去向」改為：
`經 core/adapter.py 轉接器掛上框架（階段②，模組本體零修改）`

c) 第 6 節遷移路線圖，階段②那行改為：
`- ✅ **階段②**：語音資料流——轉接器橋接 Recorder/STT、WorkspaceManager 上線`

d) 第 8 節測試清單補 `test_core_adapter.py`、`test_workspace_manager.py`、
`test_voice_flow_integration.py`。

- [ ] **Step 3: Commit**

```bash
git add plans/data_tunnel_design.md docs/architecture.md
git commit -m "docs(階段②): 設計文件與架構文檔同步轉接器設計"
```

---

## 完成定義（Definition of Done）

- [ ] `core/adapter.py`、`modules/workspace_manager.py` 就位，既有模組零修改
- [ ] `python3 -m unittest discover -s tests` 全綠
- [ ] `main.py` 與所有既有模組在本階段未被修改
- [ ] 設計文件／架構文檔與實作一致

完成後進入階段③（指令流），另寫 `plans/data_tunnel_stage3_plan.md`。
