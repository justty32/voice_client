# 資料隧道階段⑤：呈現層與 app.py 接線收尾 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 完成真實接線——所有既有模組經轉接器掛上 Exchange，新 `app.py` 成為純接線入口，舊 main.py 路由刪除（main.py 縮為薄殼轉呼叫 app.main()，使用者啟動方式不變）。

**Architecture（補齊階段④審查的接線清單）:**
1. **InboxAdapter 加 transform**：`InboxAdapter(raw_queue, transform=None)`——投遞前可把
   payload 轉換成既有模組期望的型別（給 TuiRenderer 的 dict→UiEvent 轉換用）。
2. **CliTextBridge**（新小模組）：消費 `cli_text`（terminal_input 的 text queue 經轉接器）；
   `EXIT_SIGNAL("__EXIT__")` → emit `app_ctl "EXIT"`；其他文字 → emit ui_event
   {"role":"user"} 顯示＋emit `raw_text`（port main.py:172-179）。
3. **SttGate 補 UI 顯示**：normal 模式轉發 raw_text 前先 emit ui_event
   {"role":"voice","text":text}（port main.py:168，否則使用者看不到辨識結果）。
4. **CommandRouter 消費 `recorder_event`**：`consumes=("commands","recorder_event")`，
   port main.py 段落 B——recording_started → status「錄音中」/「語音指令中」（Router 自知
   最後設定的模式）；recording_stopped → status「處理中」；error → 重設 `_is_recording`、
   emit gate_ctl normal（port main.py:155 is_command_mode=False）、ui 錯誤訊息＋status 待機。
5. **app.py**：`wire()`（可測試的純接線函式）＋`main()`（建 config/logging/legacy 模組/
   native 模組 → wire → start all → 阻塞等 app_ctl EXIT 或 KeyboardInterrupt → 統一停機，
   port main.py 的啟動訊息與 finally 停機順序，TERMINATE 給 tts_cmd_queue）。
   main.py 改為薄殼：`from app import main; main()`（舊路由全刪）。

**接線對照表（wire() 的內容）:**

| 既有 queue | 轉接 | topic |
|---|---|---|
| key_signal_queue（KeyboardListener 出） | OutboxAdapter | `commands` |
| cli_cmd_queue（TerminalInput 出） | OutboxAdapter | `commands` |
| cli_text_queue（TerminalInput 出） | OutboxAdapter | `cli_text` → CliTextBridge |
| recorder_cmd_queue（Recorder 入） | InboxAdapter | `recorder_ctl` |
| audio_queue_out（Recorder 出） | OutboxAdapter | `audio` |
| audio_queue_in（VoiceToText 入） | InboxAdapter | `audio` |
| recorder_event_queue（Recorder 出） | OutboxAdapter | `recorder_event` → CommandRouter |
| stt_output_queue（VoiceToText 出） | OutboxAdapter | `stt_text` → SttGate |
| send_queue（HttpClient 入） | InboxAdapter | `outbound` |
| recv_queue（HttpClient 出） | OutboxAdapter | `inbound` → ChatFlow |
| summary_queue（SummaryGenerator 入） | InboxAdapter | `summary_req` |
| summary_output_queue（SummaryGenerator 出） | OutboxAdapter | `summary_out` → ChatFlow |
| tts_input_queue（AudioPriorityPlayer 入） | InboxAdapter | `tts` |
| tts_cmd_queue（AudioPriorityPlayer 入） | InboxAdapter | `tts_ctl` |
| ui_event_queue（TuiRenderer 入） | InboxAdapter(transform=dict→UiEvent) | `ui_event` |
| app_ctl | 原生 Inbox（app.py 主執行緒阻塞讀取） | `app_ctl` |

注意：Recorder 與 VoiceToText 在舊版共用同一個 audio_queue 物件；新接線改為各自獨立
queue、經 Exchange 路由（單點可觀測）。

**Port 來源:** main.py 全檔（啟動順序 79-110、段落 B 143-158、段落 C/D 160-179、
finally 230-243）、tui_renderer.py（UiEvent 介面）。

**零修改維持:** record.py、voice_to_text.py、terminal_input.py、keyboard_listener.py、
http_client.py、summary_generator.py、session_manager.py、text_to_voice.py、
tui_renderer.py、mobile_server.py。
（text_accumulator.py、workspace_controller.py 自此不再被新入口使用，本階段不刪檔，
列入後續清理。）

---

### Task 1: InboxAdapter transform 參數

**Files:** Modify `core/adapter.py`、Modify `tests/test_core_adapter.py`

`InboxAdapter(raw_queue, transform=None)`：`put_nowait(message)` 時若 transform 非 None，
投遞 `transform(message.payload)`，否則照舊投遞 payload。測試：transform 套用、
None 時行為不變（既有測試不動）。

Commit: `feat(階段⑤): InboxAdapter 支援 payload 轉換（UiEvent 橋接用）`

---

### Task 2: CliTextBridge＋SttGate UI 顯示

**Files:** Create `modules/cli_text_bridge.py`、`tests/test_cli_text_bridge.py`；
Modify `modules/stt_gate.py`、`tests/test_stt_gate.py`

- CliTextBridge(TunnelModule)：`consumes=("cli_text",)`。EXIT_SIGNAL（從
  terminal_input import）→ emit app_ctl "EXIT"；空白文字忽略；其他 →
  emit ui_event {"type":"message","role":"user","text":text} ＋ emit raw_text。
  順序：先 ui 後 raw_text（port main.py:177-179）。
- SttGate：normal 模式在 emit raw_text **之前**先 emit ui_event
  {"type":"message","role":"voice","text":text}（port main.py:168）。
  command 模式不變（[語音指令] 顯示已在 CommandRouter）。更新既有測試斷言。

測試 ≥6：bridge 三行為＋順序；gate 顯示＋順序＋command 模式不顯示 voice 訊息。

Commit: `feat(階段⑤): CliTextBridge 與 SttGate 的 UI 顯示（終端/語音輸入呈現相容）`

---

### Task 3: CommandRouter 消費 recorder_event

**Files:** Modify `modules/command_router.py`、`tests/test_command_router_hotkeys.py`

- `consumes = ("commands", "recorder_event")`；handle() 依 message.topic 分派
  （commands 走既有路徑；recorder_event 走新 `_handle_recorder_event`）。
- 內部記錄 `_last_mode`（record_toggle 設 "normal"、record_command_toggle 開始時設 "command"、
  F8 停止時設 "normal"——與 gate_ctl 發送一致）。
- `_handle_recorder_event(payload)`（port main.py:143-158）：
  - {"event":"recording_started"} → `_is_recording=True`、status「語音指令中」若
    `_last_mode=="command"` 否則「錄音中」
  - {"event":"recording_stopped"} → `_is_recording=False`、status「處理中」
  - {"event":"error","message":...} → `_is_recording=False`、emit gate_ctl {"mode":"normal"}、
    `_last_mode="normal"`、ui「[錄音錯誤] {message}」、status「待機」

測試 ≥5：三種事件、error 重設狀態與 gate、started 的模式相依狀態文字。

Commit: `feat(階段⑤): CommandRouter 消費 recorder_event（錄音狀態列與錯誤復原）`

---

### Task 4: app.py 接線入口＋main.py 薄殼

**Files:** Create `app.py`、`tests/test_app_wiring.py`；Rewrite `main.py`（薄殼）

- `app.py`：
  - `wire(exchange, *, native_modules, legacy_queues)` 形式的純接線函式
    （簽名由實作者依測試便利設計；核心要求：上表所有 register 呼叫集中於此、
    無業務邏輯、可用裸 queue 測試）。
  - `main()`：load_config、_setup_logging（port main.py:29-41）、建立所有裸 queue 與
    既有模組（建構參數同舊 main.py）、建立 native 模組（WorkspaceManager、SttGate、
    CommandRouter(wm, sm, export_dir)、ChatFlow(sm, threshold, slm_enabled)、CliTextBridge）、
    wire、start 全部（先 attach/register 後 start）、發出啟動 ui 訊息（port main.py:101-110
    含熱鍵停用提示）、主執行緒阻塞於 app_ctl Inbox（get timeout 迴圈）直到 "EXIT" 或
    KeyboardInterrupt、finally 停機（port main.py:232-243：TERMINATE → 各模組 stop →
    exchange stop）。
  - session 初始化 port main.py:69-77（default session）。
- `main.py` 重寫為：docstring＋`from app import main`＋`if __name__ == "__main__": main()`。
- `tests/test_app_wiring.py`：用裸 queue ＋ native 模組呼叫 wire()，驗證代表性路由：
  key_signal "RECORD_TOGGLE" → recorder_cmd_queue 收 "START"；cli_text "哈囉" →
  ui_event_queue 收 UiEvent 且 raw_text 進 buffer；stt_output "文字" → buffer；
  recv_queue ChatReply → tts_input_queue；app_ctl EXIT 可被讀到。
  （不啟動真硬體模組——wire 只碰 queue。）

Commit: `feat(階段⑤): app.py 純接線入口；main.py 縮為薄殼（舊路由移除）`

---

### Task 5: 文件同步與收尾

**Files:** Modify `plans/data_tunnel_design.md`、`docs/architecture.md`、`docs/user_manual.md`、`README.md`

- 設計文件：通道表補 `cli_text`、`recorder_event`；遷移階段全部打勾；
  「業務邏輯落點」補 CliTextBridge。
- 架構文檔：版本標頭「重構完成」；對照表全部標完成；路線圖全勾；
  注明 text_accumulator.py／workspace_controller.py 已不被新入口使用（待清理）。
- 使用手冊：第 4 節工作區的「重構完成後」註記改為現行行為；
  其他使用方式不變（啟動指令相同）。
- README：系統架構一節改寫為資料隧道架構（簡述＋指向 docs/architecture.md）。

Commit: `docs(階段⑤): 重構完成——全文件同步`

---

## 完成定義（Definition of Done）

- [ ] `python main.py` 入口存在且為薄殼；app.py 為唯一接線點；舊路由刪除
- [ ] 既有硬體／IO 模組全部零修改
- [ ] `python3 -m unittest discover -s tests` 全綠（跑兩次）
- [ ] 文件全面同步（含 README、使用手冊）

完成後：使用 superpowers:finishing-a-development-branch 決定合併方式；
後續清理（text_accumulator、workspace_controller 移除與 mobile_server 對齊）另案。
