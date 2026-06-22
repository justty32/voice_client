# Voice Client 架構文檔

更新日期：2026-06-22
適用版本：`refactor/data-tunnel` 分支（資料隧道重構**全部完成**，`app.py` 為接線入口）

## 1. 總覽

Voice Client（V-TUI Assistant）是一個語音優先的終端 AI 客戶端：
語音經本地 STT（faster-whisper）轉為文字、累積在工作區、由使用者掌控何時送往
LLM，回覆再經摘要（本地 SLM）與 TTS 朗讀。

系統已完成從「中央路由器」到「**資料隧道（Data Tunnel）**」架構的重構：
所有模組都是掛在具名通道（topic）上的**生產者／消費者**，資料交換由單執行緒
交換核心統一執行。`app.py` 是唯一的接線入口（`main.py` 為薄殼，啟動方式不變）。
設計定案見 `plans/data_tunnel_design.md`。

```
            生產者執行緒                交換核心（單執行緒）            消費者執行緒
        ┌──────────────┐           ┌──────────────────────┐        ┌──────────────┐
        │ Recorder     │─ outbox ─▶│                      │─ inbox ▶│ STT          │
        │ STT          │─ outbox ─▶│  Exchange            │─ inbox ▶│ 當前工作區    │
        │ 終端輸入      │─ outbox ─▶│  每次 tick 只搬一筆   │─ inbox ▶│ CommandRouter│
        │ 熱鍵／本機IPC │─ outbox ─▶│  依路由表 topic→inbox │─ inbox ▶│ TUI / TTS    │
        └──────────────┘           └──────────────────────┘        └──────────────┘
```

## 2. 資料隧道框架（`core/`）

框架本體不含任何業務邏輯，五個檔案各司其職：

| 檔案 | 職責 |
|---|---|
| `core/message.py` | `Message` 資料類別：`topic`、`payload`、`source`、`created_at` |
| `core/endpoint.py` | `Outbox`（模組→交換核心）／`Inbox`（交換核心→模組），模組與核心的唯一介接點 |
| `core/exchange.py` | `Exchange`：路由表（topic → 消費者 inbox）＋單執行緒交換迴圈 |
| `core/module.py` | `TunnelModule` 基底類別：`attach`／`emit`／消費迴圈／錯誤隔離 |
| `core/adapter.py` | `OutboxAdapter`／`InboxAdapter`：把既有模組的裸 queue 偽裝成 Outbox/Inbox，零改寫掛上 Exchange |

### 2.1 交換語意

- **一次一筆**：`Exchange.tick()` 每次最多搬移一筆訊息（Outbox → Inbox）。
  所有佇列之間的搬移只發生在 Exchange 的執行緒，單點可觀測、無競態。
- **工作佇列**：每個 topic 只允許註冊一個消費者（重複註冊拋 `ValueError`）；
  每筆訊息恰好被一個消費者取走。
- **round-robin**：多個生產者輪流被服務，不會餓死後註冊者。
- **無消費者即丟棄**：訊息的 topic 沒有路由時記 warning 後丟棄。
- **錯誤隔離**：壞掉的 outbox 跳過不擋路；`tick()` 例外不會中斷交換迴圈。

### 2.2 模組模型（`TunnelModule`）

- 每個模組同時擁有 `outbox`（生產）與 `inbox`（消費）。
- **純生產者**：不宣告 `consumes`、不呼叫 `start()`，自己的背景執行緒直接 `emit()`。
- **消費者**：宣告 `consumes` 並覆寫 `handle()`；`start()` 後基底迴圈逐筆處理。
- **身兼兩者**：在 `handle()` 內 `emit()` 即可（例：CommandRouter 收指令、發控制訊息）。
- `handle()` 例外不會中斷消費迴圈，錯誤自動轉為 `ui_event` 訊息發布。
- 接線慣例：**所有模組先 `attach(exchange)`，再 `start()`**（註冊非執行緒安全）。

## 3. 通道（topic）規劃

| topic | 生產者 | 消費者 |
|---|---|---|
| `audio` | Recorder | STT |
| `stt_text` | STT | SttGate（依模式分流） |
| `raw_text` | SttGate（normal 模式）、終端文字輸入 | WorkspaceManager（塞進**當前**工作區） |
| `commands` | 終端斜線指令、SttGate（command 模式）、熱鍵 | CommandRouter |
| `cli_text` | 終端文字輸入 | CliTextBridge（EXIT 攔截＋顯示＋轉 raw_text） |
| `recorder_event` | Recorder 事件 | CommandRouter（狀態列／錯誤復原） |
| `gate_ctl` | CommandRouter | SttGate（模式切換） |
| `app_ctl` | CommandRouter（/exit）、CliTextBridge（EOF） | app.py 主執行緒 |
| `recorder_ctl` | CommandRouter | Recorder |
| `tts_ctl` | CommandRouter | AudioPriorityPlayer |
| `outbound` | CommandRouter（/send） | HttpClient |
| `inbound` | HttpClient | ChatFlow |
| `summary_req` | ChatFlow | SummaryGenerator |
| `summary_out` | SummaryGenerator | ChatFlow（呈現摘要） |
| `chat_ctl` | CommandRouter（play_last） | ChatFlow |
| `tts` | ChatFlow、SummaryGenerator、CommandRouter | AudioPriorityPlayer |
| `ui_event` | 所有模組 | TuiRenderer |

關鍵設計：

- **`raw_text` 的唯一消費者是「當前工作區」**。多個工作區並存，但只有被
  `/ws` 選中的那一個會收到新辨識文字；不自動寫入其他工作區、不自動轉發。
- **熱鍵與斜線指令一律是生產者**：按鍵只產生一筆指令資料進 `commands`，
  由 CommandRouter 統一消費後再發控制訊息，輸入端不直接操控任何模組。

## 4. 工作流

1. **語音資料流**：Recorder →`audio`→ STT →`raw_text`→ 當前工作區。
2. **指令流**：熱鍵／終端／語音指令 →`commands`→ CommandRouter →
   （`recorder_ctl`、`tts_ctl`、`ui_event`、`outbound`…）。
3. **聊天流**：/send 將 buffer 組成 payload →`outbound`→ HttpClient →`inbound`→
   ChatFlow（寫入歷史；依摘要門檻直接 `tts` 或發 `summary_req`）。
4. **呈現**：`ui_event`→ TuiRenderer；`tts`→ AudioPriorityPlayer。

## 5. 新舊模組對照

舊架構中 `main.py`（487 行）是中央路由器，輪詢所有佇列並混雜業務邏輯。
現在 `main.py` 是 14 行薄殼，`app.py`（純接線）負責建佇列、掛轉接器、啟動模組。
模組對照：

| 現有檔案 | 去向 |
|---|---|
| `main.py` 路由邏輯 | 已拆入 CommandRouter／ChatFlow／WorkspaceManager／SttGate／CliTextBridge |
| `record.py`、`voice_to_text.py` | 經 `core/adapter.py` 轉接器掛上框架（階段②，模組本體零修改） |
| `text_accumulator.py`、`workspace_controller.py` | 已被 WorkspaceManager＋CommandRouter 取代；僅 `mobile_server.py` 仍使用（待清理） |
| `workspace.py` | 沿用（WorkspaceManager 的底層資料結構） |
| `terminal_input.py`、`keyboard_listener.py` | 經轉接器作為 `commands`／`cli_text` 生產者（模組零修改） |
| `local_control.py` | Wayland 桌面快捷鍵的 Unix datagram socket 接收器；將白名單命令送入既有 `key_signal_queue` |
| `main.py` 的 `is_command_mode` | SttGate（`modules/stt_gate.py`，階段③） |
| `http_client.py`、`summary_generator.py` | 經轉接器掛上框架（階段④完成邏輯、階段⑤接線；模組零修改） |
| `session_manager.py` | 由 CommandRouter／ChatFlow 同步呼叫（保持同步物件，零修改） |
| `main.py` 的 `_route_response`、摘要呈現、last_full_response | ChatFlow（`modules/chat_flow.py`，階段④） |
| `tui_renderer.py`、`text_to_voice.py` | 經轉接器掛上框架（ui_event 經 dict→UiEvent 轉換；模組零修改） |
| `main.py` 段落 B/C/D（錄音事件、CLI 文字、EXIT） | CommandRouter（recorder_event）、CliTextBridge（cli_text） |
| `mobile_server.py` | 本次重構非目標，日後另案對齊 |

## 6. 遷移路線圖（全部完成）

- ✅ **階段①**：`core/` 框架本體＋單元測試（不接業務模組）
- ✅ **階段②**：語音資料流——轉接器橋接 Recorder/STT、WorkspaceManager 上線
- ✅ **階段③**：指令流——SttGate 分流、CommandRouter 上線（全指令集 port 完成）
- ✅ **階段④**：聊天流——ChatFlow 上線、chat 工作區指令接入、重播鏈完成
- ✅ **階段⑤**：呈現層收尾——CliTextBridge、recorder_event、`app.py` 接線入口、
  main.py 縮為薄殼（舊路由刪除）

計畫文件依序為 `plans/data_tunnel_stage{N}_plan.md`。
後續清理另案：mobile_server.py 對齊新框架時一併移除 text_accumulator.py、
workspace_controller.py。

## 7. 執行緒模型與錯誤處理

- **長駐執行緒**：每個業務模組（錄音、STT、TTS、HTTP…）一條；Exchange 一條；
  全部 daemon，`stop()` 以 `join(timeout)` 收尾。
- **本機控制**：`LocalControl` 綁定 `$XDG_RUNTIME_DIR/voice-client-control.sock`
  （權限 `0600`），只接受固定命令白名單。KDE 快捷鍵啟動短命 helper，透過
  Unix datagram 將 `RECORD_TOGGLE` 送入與 `KeyboardListener` 共用的命令 queue。
  0.5 秒相同命令去抖用來吸收桌面啟動動作可能產生的重複觸發。
- **單點交換**：佇列間搬移僅由 Exchange 執行緒進行——資料流可在一處完整記 log。
- **錯誤策略**：模組 `handle()` 例外 → log + `ui_event` 通知使用者，迴圈續行；
  Exchange 例外 → log 後續行；無路由訊息 → warning + 丟棄。
- **關機**：`app.py` 統一停模組 → 停 Exchange。

## 8. 測試

- 框架單元測試：`tests/test_core_message.py`、`test_core_endpoint.py`、
  `test_core_exchange.py`、`test_core_module.py`、`test_core_adapter.py`
- 業務模組測試：`tests/test_workspace_manager.py`、`test_stt_gate.py`、
  `test_command_router_hotkeys.py`、`test_command_router_workspace.py`、
  `test_command_router_session.py`、`test_command_router_voice.py`、
  `test_chat_flow.py`、`test_cli_text_bridge.py`
- 接線測試：`tests/test_app_wiring.py`（app.wire() 的端到端路由驗證）
- 本機控制測試：`tests/test_local_control.py`（白名單、轉發、未知命令、重複命令去抖）
- 框架整合測試：`tests/test_core_integration.py`（生產者→Exchange→消費者全鏈）、
  `test_voice_flow_integration.py`（語音資料流：audio→STT→當前工作區）、
  `test_command_flow_integration.py`（指令流：熱鍵／語音指令／終端全鏈）、
  `test_chat_flow_integration.py`（聊天流：HTTP 往返／摘要／重播全鏈）
- 執行：`python3 -m unittest discover -s tests`（unittest，非 pytest）

## 相關文件

- 設計定案：`plans/data_tunnel_design.md`
- 階段①計畫：`plans/data_tunnel_stage1_plan.md`
- 使用手冊：`docs/user_manual.md`
- KDE Wayland 快捷鍵：`docs/kde_wayland_shortcuts.md`
