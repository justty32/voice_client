# 測試覆蓋地圖

[入口](README.md)

基準（2026-10-09，工作樹）：`.venv/bin/python -m pytest -q` → **358 passed, 9 subtests passed**。
`CLAUDE.md` 寫的 `339 passed, 5 subtests passed` 已經過時。
查證：`python workflows/common/code-map/codemap.py json` 的 `imported_by`（只看 `tests.*`），
加上 `rg -l <模組名> tests`；測試數量用 `rg -c 'def test' tests/<檔>` 統計。

## 1. 有直接測試的模組

| 模組 | 測試檔（測試數） |
|---|---|
| `core/*` | `test_core_message`(3)、`_endpoint`(7)、`_exchange`(9)、`_module`(6)、`_adapter`(9)、`_integration`(2) |
| `app_wiring/*`（經 `app`） | `test_app_wiring`(6)：只測 `wire()` 路由與 `_dict_to_ui_event`，**不測 `main()`** |
| `modules/command_router`＋handlers | `test_command_router_*` 8 檔（121） |
| `modules/chat_flow` | `test_chat_flow_reply`(9)、`_summary`(5)、整合 3 檔(4) |

| 模組 | 測試檔（測試數） |
|---|---|
| `modules/stt_gate`、`workspace_manager`、`cli_text_bridge` | `test_stt_gate`(12)、`test_workspace_manager`(6)、`test_cli_text_bridge`(7) |
| `workspace.py`、`session_manager.py` | `test_workspace`(25)、`test_session_manager`(14) |
| `local_control.py` | `test_local_control`(4) |
| `codemap.py` | `test_codemap`(5) |

## 2. 只有淺層測試

| 模組 | 現況 |
|---|---|
| `record.py` | `test_record`(1)：只測 PyAudio 初始化失敗時回報 error；切片／VAD／STOP 邏輯沒有測試；numpy、pyaudio 用 stub（`tests/test_record.py:16-17`） |
| `voice_to_text.py` | `test_voice_to_text`(7)：只測設定解析與 CPU 不預載；`_loop`、模型載入失敗路徑沒有測試 |
| `text_to_voice.py`＋`tts/*` | `test_text_to_voice`(10)：語言分段、引擎選擇、kokoro 任務編號／取消；dispatcher 迴圈、`_drain_input` 優先級、worker 死亡都沒有測試 |

## 3. 沒有任何直接測試

| 模組 | 備註 |
|---|---|
| `http_client.py` | 整合測試用形狀相同的假物件取代（`tests/test_chat_flow_integration_http.py:27`）；`_call_local`、retry、`_save_failed` 都沒有測試 |
| `summary_generator.py` | 同樣用假物件（`test_chat_flow_integration_summary.py:25`） |
| `terminal_input.py` | 只有被匯入 `EXIT_SIGNAL`（`test_cli_text_bridge.py:15`）；斜線指令解析沒有測試 |
| `keyboard_listener.py`、`tui_renderer.py` | 沒有（`tui_renderer` 只在 `test_app_wiring` 中被間接匯入） |

| 模組 | 備註 |
|---|---|
| `utils/llm_client.py`、`prompt_loader.py`、`logging_setup.py` | 沒有；`clipboard` 只被 mock（`test_command_router_workspace_edit.py:221-260`） |
| `config.py` | 沒有 |
| `app.py:main()` | 沒有（啟停順序、三份清單一致性都沒有測試） |
| `mobile_server.py`、`mobile/*`（7 檔） | **完全沒有**；`.venv` 缺 `fastapi`／`uvicorn`，連匯入都做不到（`ModuleNotFoundError: uvicorn`），而且 `mobile/state.py` 匯入時就會建立 VoiceToText 等元件 |

## 4. 測在舊路徑上的部分

`test_text_accumulator`(28)＋`test_workspace_controller`(38)＋`test_clipboard_commands`(13)＝**79 個測試**
（約佔 358 個的 22%），保護的是只有手機在用的舊工作區實作。
`test_clipboard_commands` 同時匯入 `session_manager`、`text_accumulator`、`workspace_controller`。

## 5. 缺少的測試類型

- 沒有協定契約測試：`docs/architecture/topics.md` 的表與 `wire()` 實際註冊的路由沒有機械比對
  （已知漂移：`tts` 生產者，見 [dataflow.md](dataflow.md)）。
- 沒有並發測試：Workspace／SessionManager 的跨執行緒競態沒有壓力測試。
- 沒有手機與桌面的行為對齊測試（兩邊各自的訊息文字已經不同，見 [entrypoints.md](entrypoints.md)）。
- 整合測試用假物件代替 legacy I/O 模組，所以真實模組的 queue 協定（例如 HttpClient 回傳的 dict 形狀）
  只靠假物件「形態相同」的註解維持。
