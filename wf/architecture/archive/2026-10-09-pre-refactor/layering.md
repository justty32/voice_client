> 封存 2026-10-09，由 docs/architecture.md 與 workflows/common/code-map/CODE_MAP.md 取代（重構前快照，refactor_next 已落地）

# 分層與依賴

[入口](README.md)

依賴資料來源：`python workflows/common/code-map/codemap.py json`（AST 靜態掃描，含函式內延遲匯入；
`ai_assist/`、`server_sample/`、`wf/`、`workflows/` 被排除，見 `codemap.py:25`）。
另以 `rg -n "^\s+(from|import) "` 補查函式內匯入，結果全是第三方套件，沒有遺漏的專案內依賴。

## 1. 現有套件與根層

套件（有 `__init__.py`）：`core/`（5 檔）、`modules/`（5 檔＋`command_handlers/` 3 檔）、
`utils/`（4 檔）、`tts/`（3 檔）、`app_wiring/`（2 檔）、`mobile/`（7 檔）。

根層仍有 **17 個 `.py`**，用途混在一起：

| 類別 | 根層檔案 |
|---|---|
| 入口 | `main.py`、`app.py`、`mobile_server.py` |
| 語音 I/O | `record.py`、`voice_to_text.py`、`text_to_voice.py`（另一半在 `tts/`） |
| 終端介面 | `terminal_input.py`、`keyboard_listener.py`、`local_control.py`、`tui_renderer.py` |
| LLM I/O | `http_client.py`、`summary_generator.py` |
| 領域資料 | `workspace.py`、`session_manager.py` |
| 舊路徑 | `text_accumulator.py`、`workspace_controller.py` |
| 設定 | `config.py`（8 行） |

觀察：

- `text_to_voice.py` 留在根層，拆出的 `tts/` 在套件內，同一個元件被拆在兩層
  （`text_to_voice.py:29-31` re-export `tts.*`）。
- `mobile_server.py` 與 `mobile/` 同樣是一層入口加一個套件；`app.py` 與 `app_wiring/` 也一樣。
- 業務模組 `modules/workspace_manager.py:10` 與 `modules/command_handlers/workspace.py:7`
  依賴根層的 `workspace.py`，所以「領域資料結構」放在根層，業務放在 `modules/`，方向是 modules→根層。

## 2. 依賴方向（彙整）

| 來源 | 依賴到 |
|---|---|
| `core/*` | 只用標準庫與 `core` 內部（`core/adapter.py:15`、`core/exchange.py:12`、`core/module.py:15-16`） |
| `modules/*` | `core.message`、`core.module`；另外 `workspace`、`terminal_input`、`utils.clipboard` |
| `app_wiring/*` | `core.adapter`、`core.exchange`、`tui_renderer`（`app_wiring/ui_events.py:8`） |
| `app.py` | 20 個模組（幾乎全部根層 I/O＋所有 `modules`） |
| `mobile/state.py` | `config`、`http_client`、`session_manager`、`summary_generator`、`text_accumulator`、`voice_to_text`、`workspace_controller`、`utils.logging_setup` |

| 來源 | 依賴到 |
|---|---|
| `http_client.py`、`summary_generator.py` | `utils.llm_client`、`utils.prompt_loader` |
| `session_manager.py` | `workspace`（`session_manager.py:6`，用在 `_apply_history_op` 152-162） |
| `text_accumulator.py`、`workspace_controller.py` | `workspace`、`utils.clipboard` |
| `text_to_voice.py` | `tts.*` |
| 其他根層 I/O | 不依賴專案內模組 |

**循環依賴：無**。對 codemap json 的 import 圖做 DFS，非測試模組之間沒有環。

## 3. 規則檢查

### 「core 不依賴業務模組」：import 層面成立，語意上有一處耦合

- import 層面乾淨：`core/` 五檔只 import 標準庫與彼此。
- 語意耦合：`core/module.py:59-63` 的 `TunnelModule._run` 在 `handle()` 例外時，
  寫死 emit 業務 topic `"ui_event"`，payload 用業務形狀
  `{"type":"message","role":"system","text":...}`。框架知道 UI 協定。

### 「app.py 只接線」：`wire()` 符合，`main()` 有業務／呈現決策

`wire()` 已搬到 `app_wiring/topology.py:13-137`，是純接線。`app.py:main()`（37-219）還做了這些事：

| 位置 | 內容 | 性質 |
|---|---|---|
| `app.py:88-91` | 沒有當前對話就切到或建立 `default` | 業務初始化（`mobile/state.py:32-35` 有一模一樣的副本） |
| `app.py:93-96` | 從 `WORKSPACE.export_file` 推出匯出目錄 | 設定解讀（`mobile/state.py:42` 副本） |
| `app.py:115-116` | 讀 `SLM.summary_threshold`／`enabled` 傳給 ChatFlow | 設定解讀（`mobile/state.py:45-46` 副本；`summary_generator.py:24` 又讀一次 `enabled`） |
| `app.py:172-185` | 依熱鍵可用性組出啟動提示文字 | 呈現文字，而且繞過隧道直接放進 `ui_event_queue` |
| `app.py:203` | `tts_cmd_queue.put("TERMINATE")` | 繞過隧道的控制訊息 |

`app.py:99-118`（建構）、`151-167`（start）、`204-218`（stop）是三份手寫清單，順序靠人工對齊。

### 其他跨層耦合

- `modules/cli_text_bridge.py:16` 從根層 I/O 模組 `terminal_input` 匯入 `EXIT_SIGNAL`
  （業務模組依賴輸入裝置模組的常數）。
- `modules/command_handlers/workspace.py:6,131,138` 在業務 handler 內直接呼叫 `utils.clipboard`
  （同步系統 I/O，所以 mobile 無法共用這段，見 [entrypoints.md](entrypoints.md)）。
- `http_client.py:25-28,109-119`：網路 I/O 層持有 `SessionManager`，自己讀歷史組上下文。
- `app_wiring/ui_events.py:3-17` 依賴 `tui_renderer.UiEvent`；接線層知道呈現層型別。
  註解說的 `_FallbackUiEvent`（第 6 行）跟實際類名 `_UiEventClass`（第 14 行）對不上。

## 4. 共享可變物件（不走隧道的同步呼叫）

隧道只負責佇列搬移，下列物件仍被多條執行緒直接呼叫，而且沒有鎖
（`rg -n "Lock" session_manager.py workspace.py core/` 沒有結果）：

| 物件 | 呼叫者（執行緒） |
|---|---|
| `SessionManager` | CommandRouter（session／send handler）、ChatFlow（`chat_flow.py:69`）、HttpClient（`http_client.py:109`） |
| `Workspace`（WM 內） | WorkspaceManager 執行緒 append（`workspace_manager.py:50-51`）、CommandRouter 執行緒 clear／concat／move（`command_handlers/workspace.py`） |
| `WorkspaceManager._current` | CommandRouter 呼叫 `switch()`（`workspace_manager.py:38-47`，註解以 GIL 自辯） |
| mobile `_wsc.stt` | asyncio pusher（`mobile/outputs.py:67`）與 `to_thread`／事件迴圈中的指令處理（`mobile/inputs.py:81`） |
