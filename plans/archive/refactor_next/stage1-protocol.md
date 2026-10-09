> 封存 2026-10-09，已全部落地（見 workflows/feature-dev/landed/README.md）
# 階段 1：協定單一事實來源（`protocol/`＋契約測試）

[總覽](README.md)｜痛點 4、P3（1、2、5）

## 目標

topic 名稱、payload 鍵與控制字串集中到一個**零依賴**套件；用三方機械比對（`wire()` 實際路由、codemap 掃描、`docs/architecture/topics.md`）
鎖住協定，之後任何漂移都讓測試變紅。全程 behavior-preserving：所有字串值不變，只是來源變成常數。

為什麼放 `protocol/` 而不是 `core/`：`core/` 不得知道業務 topic（CLAUDE.md 鐵律）；放 `modules/` 則根層 I/O 模組（`terminal_input.py` 等）
反向依賴 `modules`，且 `modules/command_handlers/__init__.py` 會在匯入時拉進整組 mixin。`protocol/` 只 import 標準庫，任何層都能匯入。

## 動到的檔案

新增：

- `protocol/__init__.py`（空）
- `protocol/topics.py`：17 個 topic 常數＋`ALL: frozenset`。名稱對應 `docs/architecture/topics.md` 現表：
  `AUDIO, STT_TEXT, RAW_TEXT, COMMANDS, CLI_TEXT, RECORDER_EVENT, GATE_CTL, APP_CTL, RECORDER_CTL, TTS_CTL, CHAT_CTL, OUTBOUND, INBOUND, SUMMARY_REQ, SUMMARY_OUT, TTS, UI_EVENT`。
- `protocol/payloads.py`：建構函式與控制字串常數，值一律沿用現碼：
  - `ui_status(text)`、`ui_message(role, text)`、`ui_clear()`（形狀見 `app_wiring/ui_events.py:23-27`）
  - `command(cmd, args=())` → `{"cmd","args"}`；`recorder_event(event, **extra)` → `{"event",...}`
  - `gate_mode(mode)` → `{"mode"}`；`chat_cmd(cmd)` → `{"cmd"}`；`tts_item(text, priority)`；`summary_request(text, title)`；
    `outbound_chat(content, title, client_time)` → 大寫鍵 `Content/Title/Metadata.ClientTime`（`modules/command_handlers/workspace.py:192-196`）
  - 常數：`RECORDER_START="START"`、`RECORDER_STOP="STOP"`、`TTS_STOP_SPEECH`、`TTS_TERMINATE`、`APP_EXIT="EXIT"`、`UI_ROLES`
- `tests/test_protocol_contract.py`、`tests/test_protocol_literals.py`

修改（機械替換字面字串為常數）：

- `modules/*.py`、`modules/command_handlers/*.py`（所有 `emit("...")`、`consumes = (...)`、`message.topic == "..."`）
- `app_wiring/topology.py`（`register_producer(... topic=...)`、`register_consumer("...")`）
- `app.py`（`payload == "EXIT"`、`tts_cmd_queue.put("TERMINATE")`）
- `core/exchange.py`：新增公開查詢 `routes() -> tuple[str, ...]`（回傳已註冊 topic；給契約測試用，不再碰 `_routes`）＋1 個單元測試。
  `core/module.py:59-63` 的 `"ui_event"` 字面**本階段不動**（core 不匯入 protocol；階段 4a 改成可覆寫的 hook）。
- `docs/architecture/topics.md`：改寫成可機械比對的表（見步驟 4）。
- `workflows/common/code-map/CODE_MAP.md`：「框架與接線」加 `protocol/`。

## 步驟

1. 建 `protocol/`，先寫常數與建構函式；`python -c "import protocol.topics, protocol.payloads"` 成功。
2. 寫 `tests/test_protocol_contract.py`（先紅後綠）：
   - `test_wire_routes_equal_protocol_all`：照 `tests/test_app_wiring.py:setUp` 方式建 Exchange＋`wire()`（可抽成 `tests/_wiring_helpers.py:build_wired(tmp)` 供兩檔共用），
     斷言 `set(exchange.routes()) == protocol.topics.ALL`。
   - `test_codemap_topics_equal_protocol_all`：`sys.path` 加入 `workflows/common/code-map`，`codemap.scan()["topics"].keys() == ALL`（`tests/test_codemap.py` 已示範匯入方式）。
   - `test_docs_table_matches_codemap`：解析 `docs/architecture/topics.md` 的三張表，(a) 反引號 topic 集合 == `ALL`；(b) 生產者欄以測試內的別名表
     （`ChatFlow→modules.chat_flow.ChatFlow`、`Recorder→app_wiring.topology:recorder`、`STT→…:voice_to_text`、`HttpClient→…:http_client`、
     `SummaryGenerator→…:summary_generator`、`熱鍵→…:keyboard_listener`、`終端指令→…:terminal_input_cmd`、`終端文字→…:terminal_input_text`、
     `SttGate`、`CommandRouter`、`CliTextBridge`、`WorkspaceCommandMixin`…）轉成 codemap 識別字後，集合必須相等（`ui_event` 可忽略 `core.module.TunnelModule`）。
     **驗收**：把文件 `tts` 生產者改回「ChatFlow、SummaryGenerator、CommandRouter」時此測試必須變紅。
3. 寫 `tests/test_protocol_literals.py`：用 `ast` 掃 `modules/`、`app_wiring/`、`app.py`，凡 `emit(`、`register_consumer(`、`register_producer(`（含 `topic=` 關鍵字）第一個引數是 `ast.Constant` 字串即失敗。
   此時應列出所有待替換點 → 逐一改成常數直到綠。
4. 改寫 `docs/architecture/topics.md` §3 三張表為「`topic` | 生產者（別名） | 消費者 | payload 形狀（指向 `protocol/payloads.py` 函式名）」；
   「關鍵設計」段保留。控制 topic 的裸字串（`recorder_ctl`、`tts_ctl`、`app_ctl`）如實標示「裸字串」。
5. 既有測試可留字面字串（它們是外部觀察者），不強制改。
6. 更新 CODE_MAP；跑驗證。

## behavior-preserving

是。所有 topic 與 payload 的值不變；`Exchange.routes()` 是純新增查詢。

## 驗證命令

```bash
.venv/bin/python -m pytest -q                                   # 全綠；≥ 358 + 新增（契約 3、字面掃描 1、routes 1 ＝ 至少 5）
.venv/bin/python -m pytest -q tests/test_protocol_contract.py tests/test_protocol_literals.py
python workflows/common/code-map/codemap.py topics               # 17 個 topic，與 protocol/topics.py 一致
python -m compileall -q -x '/(\.venv|\.git)/' .
bash wf/tools/wf-lint.sh .
```

## 需同步的文件

- CODE_MAP：新增 `protocol/topics.py`、`protocol/payloads.py`、`tests/test_protocol_*.py`。
- `docs/architecture/framework.md` §2 表：`core/exchange.py` 加「`routes()` 查詢」。
- `docs/architecture/testing.md`：新增「協定契約測試」一行。

## Done when

- `protocol/topics.py`、`protocol/payloads.py`、`tests/test_protocol_contract.py`、`tests/test_protocol_literals.py` 存在。
- `rg -n 'emit\("' modules app_wiring app.py` 無命中。
- pytest 全綠且測試數 ≥ 363。
- 故意把 `docs/architecture/topics.md` 的 `tts` 生產者加上 `SummaryGenerator` → `test_docs_table_matches_codemap` 失敗；改回後通過。

建議 commit 訊息：`refactor(protocol): topic／payload 常數集中到 protocol/，加契約測試`
