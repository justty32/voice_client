# Voice Client 架構文檔

更新日期：2026-06-10
適用版本：`refactor/data-tunnel` 分支（資料隧道重構階段①完成）

## 1. 總覽

Voice Client（V-TUI Assistant）是一個語音優先的終端 AI 客戶端：
語音經本地 STT（faster-whisper）轉為文字、累積在工作區、由使用者掌控何時送往
LLM，回覆再經摘要（本地 SLM）與 TTS 朗讀。

系統正在從「中央路由器」架構遷移至「**資料隧道（Data Tunnel）**」架構：
所有模組都是掛在具名通道（topic）上的**生產者／消費者**，資料交換由單執行緒
交換核心統一執行。設計定案見 `plans/data_tunnel_design.md`。

```
            生產者執行緒                交換核心（單執行緒）            消費者執行緒
        ┌──────────────┐           ┌──────────────────────┐        ┌──────────────┐
        │ Recorder     │─ outbox ─▶│                      │─ inbox ▶│ STT          │
        │ STT          │─ outbox ─▶│  Exchange            │─ inbox ▶│ 當前工作區    │
        │ 終端輸入      │─ outbox ─▶│  每次 tick 只搬一筆   │─ inbox ▶│ CommandRouter│
        │ 熱鍵          │─ outbox ─▶│  依路由表 topic→inbox │─ inbox ▶│ TUI / TTS    │
        └──────────────┘           └──────────────────────┘        └──────────────┘
```

## 2. 資料隧道框架（`core/`，階段①已完成）

框架本體不含任何業務邏輯，五個檔案各司其職：

| 檔案 | 職責 |
|---|---|
| `core/message.py` | `Message` 資料類別：`topic`、`payload`、`source`、`created_at` |
| `core/endpoint.py` | `Outbox`（模組→交換核心）／`Inbox`（交換核心→模組），模組與核心的唯一介接點 |
| `core/exchange.py` | `Exchange`：路由表（topic → 消費者 inbox）＋單執行緒交換迴圈 |
| `core/module.py` | `TunnelModule` 基底類別：`attach`／`emit`／消費迴圈／錯誤隔離 |

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
| `raw_text` | STT、終端文字輸入 | WorkspaceManager（塞進**當前**工作區） |
| `commands` | 終端斜線指令、語音指令辨識、熱鍵 | CommandRouter |
| `recorder_ctl` | CommandRouter | Recorder |
| `tts_ctl` | CommandRouter | AudioPriorityPlayer |
| `outbound` | CommandRouter（/send） | HttpClient |
| `inbound` | HttpClient | ChatFlow |
| `summary_req` | ChatFlow | SummaryGenerator |
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

## 5. 現行（遷移前）模組對照

舊架構中 `main.py`（487 行）是中央路由器，輪詢所有佇列並混雜業務邏輯。
遷移完成後 `main.py`／`app.py` 縮減為純接線。現有模組對照：

| 現有檔案 | 去向 |
|---|---|
| `main.py` 路由邏輯 | 拆入 CommandRouter／ChatFlow／WorkspaceManager |
| `record.py`、`voice_to_text.py` | 改為框架生產者／消費者（階段②） |
| `text_accumulator.py`、`workspace_controller.py`、`workspace.py` | 合併為 WorkspaceManager（階段②③） |
| `terminal_input.py`、`keyboard_listener.py` | 改為 `commands` 生產者（階段③） |
| `http_client.py`、`summary_generator.py`、`session_manager.py` | 聊天流（階段④） |
| `tui_renderer.py`、`text_to_voice.py` | 呈現層（階段⑤） |
| `mobile_server.py` | 本次重構非目標，日後另案對齊 |

## 6. 遷移路線圖

- ✅ **階段①**：`core/` 框架本體＋29 個測試（不接業務模組）
- ⬜ **階段②**：語音資料流——Recorder、STT、WorkspaceManager 掛上框架
- ⬜ **階段③**：指令流——終端、熱鍵、語音指令改為生產者；CommandRouter 上線
- ⬜ **階段④**：聊天流——HttpClient、ChatFlow、SummaryGenerator
- ⬜ **階段⑤**：呈現層收尾——TuiRenderer、TTS；移除舊 main.py 路由

每階段獨立可運作、有測試；計畫文件依序為 `plans/data_tunnel_stage{N}_plan.md`。

## 7. 執行緒模型與錯誤處理

- **長駐執行緒**：每個業務模組（錄音、STT、TTS、HTTP…）一條；Exchange 一條；
  全部 daemon，`stop()` 以 `join(timeout)` 收尾。
- **單點交換**：佇列間搬移僅由 Exchange 執行緒進行——資料流可在一處完整記 log。
- **錯誤策略**：模組 `handle()` 例外 → log + `ui_event` 通知使用者，迴圈續行；
  Exchange 例外 → log 後續行；無路由訊息 → warning + 丟棄。
- **關機**：`app.py` 統一停模組 → 停 Exchange。

## 8. 測試

- 框架單元測試：`tests/test_core_message.py`、`test_core_endpoint.py`、
  `test_core_exchange.py`、`test_core_module.py`
- 框架整合測試：`tests/test_core_integration.py`（生產者→Exchange→消費者全鏈）
- 執行：`python3 -m unittest discover -s tests`（unittest，非 pytest）

## 相關文件

- 設計定案：`plans/data_tunnel_design.md`
- 階段①計畫：`plans/data_tunnel_stage1_plan.md`
- 使用手冊：`docs/user_manual.md`
