# 架構文檔：新舊模組對照與遷移

[架構文檔入口](../architecture.md)

## 5. 新舊模組對照

舊架構中 `main.py`（487 行）是中央路由器，輪詢所有佇列並混雜業務邏輯。
現在 `main.py` 是 14 行薄殼，`app.py`（純接線）呼叫 `app_wiring/assembly.py` 的 `build_core()`
取得佇列、原生模組與已接線的 Exchange，再建 legacy 元件並以 `Lifecycle` 統一啟停；
設定解讀（default 對話、匯出目錄、SLM 參數）在 `app_wiring/settings.py`。
手機入口 `mobile/state.py` 同樣呼叫 `build_core()`，只把 TuiRenderer／AudioPriorityPlayer／Recorder 換成 WS 邊緣（`mobile/edge.py`）。
模組對照：

### `main.py` 路由邏輯的去向

| 現有檔案 | 去向 |
|---|---|
| `main.py` 路由邏輯 | 已拆入 CommandRouter／ChatFlow／WorkspaceManager／SttGate／CliTextBridge |
| `main.py` 的 `is_command_mode` | SttGate（`modules/stt_gate.py`，階段③） |
| `main.py` 的 `_route_response`、摘要呈現、last_full_response | ChatFlow（`modules/chat_flow.py`，階段④） |
| `main.py` 段落 B/C/D（錄音事件、CLI 文字、EXIT） | CommandRouter（recorder_event）、CliTextBridge（cli_text） |

### 既有模組的接入方式

| 現有檔案 | 去向 |
|---|---|
| `record.py`、`voice_to_text.py` | 經 `core/adapter.py` 轉接器掛上框架（階段②，模組本體零修改） |
| `workspace.py` | 沿用（WorkspaceManager 的底層資料結構） |
| `terminal_input.py`、`keyboard_listener.py` | 經轉接器作為 `commands`／`cli_text` 生產者（模組零修改） |
| `local_control.py` | Wayland 桌面快捷鍵的 Unix datagram socket 接收器；將白名單命令送入既有 `key_signal_queue` |
| `http_client.py`、`summary_generator.py` | 經轉接器掛上框架（階段④完成邏輯、階段⑤接線；模組零修改） |
| `session_manager.py` | 由 CommandRouter／ChatFlow 同步呼叫（保持同步物件，零修改） |
| `tui_renderer.py`、`text_to_voice.py` | 經轉接器掛上框架（ui_event 經 dict→UiEvent 轉換；模組零修改） |

### 手機入口與待刪除

| 現有檔案 | 去向 |
|---|---|
| `mobile_server.py` | 走 Data Tunnel：`build_core()`＋WS 邊緣轉接（refactor_next 階段 7b）；行為以桌面為準 |
| `text_accumulator.py`、`workspace_controller.py` | DEPRECATED，產品碼零引用；待使用者裁示（D4）後連同其測試刪除 |

## 6. 遷移路線圖（全部完成）

- ✅ **階段①**：`core/` 框架本體＋單元測試（不接業務模組）
- ✅ **階段②**：語音資料流——轉接器橋接 Recorder/STT、WorkspaceManager 上線
- ✅ **階段③**：指令流——SttGate 分流、CommandRouter 上線（全指令集 port 完成）
- ✅ **階段④**：聊天流——ChatFlow 上線、chat 工作區指令接入、重播鏈完成
- ✅ **階段⑤**：呈現層收尾——CliTextBridge、recorder_event、`app.py` 接線入口、
  main.py 縮為薄殼（舊路由刪除）
- ✅ **refactor_next 7b**：手機入口改走 `build_core()`；text_accumulator.py、
  workspace_controller.py 不再被產品碼引用（刪除待 D4）。
