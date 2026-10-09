# 兩條入口的分歧：桌面 vs 手機

[入口](README.md)

## 1. 結構對照

| 面向 | 桌面（`main.py`→`app.py`） | 手機（`mobile_server.py`＋`mobile/`） |
|---|---|---|
| 路由 | Exchange＋topic（`app_wiring/topology.py`） | 沒有 Exchange；`_output_pusher` 每 50ms 輪詢 5 組 queue（`mobile/outputs.py:58-116`） |
| 元件建立 | `main()` 執行時才建立 | **匯入 `mobile.state` 就建立**：載 config、設日誌、建 VoiceToText 等（`mobile/state.py:18-46`） |
| buffer 工作區 | `WorkspaceManager` 的 `Workspace("buffer")` | `TextAccumulator` 執行緒＋cmd/output queue |
| 工作區指令 | `CommandRouter`＋`WorkspaceCommandMixin` | `WorkspaceController` → `WSResult` 意圖 → `_apply_ws_result`（`mobile/push.py:21-29`） |
| 對話指令 | `SessionCommandMixin` | `mobile/inputs.py:95-146` 內嵌 if/elif |
| 回覆處理 | `ChatFlow` | `mobile/outputs.py:28-53` `_handle_response` |
| 輸出 | TuiRenderer＋AudioPriorityPlayer | 推 WebSocket JSON；TTS 由前端 SpeechSynthesis 播放 |

手機用到的共享元件：`config`、`SessionManager`、`VoiceToText`、`SummaryGenerator`、`HttpClient`、
`utils.logging_setup`（`mobile/state.py:9-16`）。手機**不使用** `core/`、`modules/`、`app_wiring/`
（`codemap.py deps` 的 imported_by 沒有任何 mobile 模組）。

## 2. 手機仍依賴的舊元件

- `text_accumulator.TextAccumulator`：`mobile/state.py:13,38`；lifespan 負責啟停（`mobile_server.py:84,90`）。
- `workspace_controller.WorkspaceController`：`mobile/state.py:16,43`；`mobile/inputs.py:150-168` 的工作區指令全走它。
- 舊式 buffer 協定：`{"type":"text","text","msg_type"}` 輸入（`mobile/inputs.py:44,77`、`mobile/outputs.py:68`），
  `payload/buffer_peek/buffer_text` 輸出（`text_accumulator.py:114-115,144,261-268`）。`msg_type` 欄位沒有任何讀取者。

## 3. 重複的業務邏輯（兩份實作）

| 邏輯 | 桌面位置 | 手機位置 |
|---|---|---|
| 回覆→歷史→摘要門檻→TTS | `modules/chat_flow.py:63-85` | `mobile/outputs.py:28-42` |
| 摘要呈現「回覆摘要：」 | `chat_flow.py:100-107` | `mobile/outputs.py:90-97` |
| /send payload 組裝（Title/ClientTime/add_message） | `command_handlers/workspace.py:178-205` | `mobile/outputs.py:73-82`＋`text_accumulator.py:252-268` |
| /new /switch /list /delete /save /load /rename /history | `command_handlers/session.py:7-68` | `mobile/inputs.py:96-146` |

| 邏輯 | 桌面位置 | 手機位置 |
|---|---|---|
| 工作區 CRUD 訊息文字 | `command_handlers/workspace.py:20-176` | `workspace_controller.py:61-244`＋`text_accumulator.py:138-250` |
| /help 指令清單 | `command_handlers/session.py:72-77` | `mobile/inputs.py:180-183` |
| default session 初始化 | `app.py:88-91` | `mobile/state.py:32-35` |
| export_dir、SLM 設定解讀 | `app.py:93-96,115-116` | `mobile/state.py:42,45-46` |

## 4. 行為已經不一致的地方（可查證）

> 2026-10-09 refactor_next 階段 7b 後，手機已改走 `build_core()`，下表除「停機時保存 buffer」（D10 保留）、`/exit`（手機邊緣攔截）與語音指令模式（手機無 F7 觸發）外均已對齊桌面；表格保留作為調查當時的事實紀錄。

| 項目 | 桌面 | 手機 |
|---|---|---|
| 工作區集合 | `buffer`、`stt`；`chat` 只能看（`workspace_manager.py:17`、`command_handlers/workspace.py:34-39`） | `stt`、`buffer`、`chat`，都可切換（`workspace_controller.py:35`） |
| chat 的 /del /move /to_top | 不支援 | 支援，直接改歷史（`workspace_controller.py:160,177,192`） |
| STT 文字去向 | 只進**當前**工作區（`workspace_manager.py:50-51`） | **同時**進 stt 工作區與 buffer（`mobile/outputs.py:67-68`） |
| 語音指令模式 | SttGate＋VoiceCommandMixin | 沒有 |
| `/switch` 不帶參數且沒有 default | 自動建立（`session.py:18-20`） | 只回報找不到（`mobile/inputs.py:102-107`） |

| 項目 | 桌面 | 手機 |
|---|---|---|
| `/list` 尾行 | 「當前使用session：」（`session.py:29`） | 「當前 session：」（`mobile/inputs.py:113`） |
| Error 回覆 | role `system`，不復位狀態（`chat_flow.py:93-96`） | role `error`，並推送「待機」（`mobile/outputs.py:49-53`） |
| `/import` 不帶參數 | 回報錯誤（`command_handlers/workspace.py:162-164`） | buffer 讀 `_buffer_temp.json`（`text_accumulator.py:118-122`） |
| 停機時保存 buffer | 不保存 | 匯出 `_buffer_temp.json`（`text_accumulator.py:58-66`） |
| `/exit` | 有 | 沒有 |

## 5. 手機專屬協定（桌面 ui_event 沒有）

WebSocket 推送型別：`tts`、`tts_control`、`clipboard_write`、`clipboard_read`、`sessions_refresh`
（伺服器展開成 `sessions`，`mobile/outputs.py:106-109`），前端在 `static/app.js:47-69` 處理。
前端送來的型別：`text`、`cmd`、`signal`、`clipboard_data`，音訊用 binary frame（`mobile/inputs.py:33-51`、`mobile_server.py:122-126`）。
剪貼簿在手機是「瀏覽器往返」（`mobile/inputs.py:54-84`），在桌面是本機 `utils.clipboard` 同步呼叫。

## 6. 手機的併發與可測性事實

- 每條 WebSocket 連線各開一個 `_output_pusher`（`mobile_server.py:118`），所有連線消費同一組模組層級 queue。
- 音訊轉檔在 `asyncio.to_thread` 執行（`mobile_server.py:124`），文字指令在事件迴圈執行，兩邊都會碰 `_wsc.stt` 和 `SessionManager`。
- `.venv` 沒有 `fastapi`／`uvicorn`：`.venv/bin/python -c "import mobile_server"` → `ModuleNotFoundError: uvicorn`。
  `requirements.txt` 有列這兩個套件，但開發環境沒裝；而且匯入 `mobile.state` 就會建立所有元件，無法注入替身。
