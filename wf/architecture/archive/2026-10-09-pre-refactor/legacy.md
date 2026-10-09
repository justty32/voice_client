> 封存 2026-10-09，由 docs/architecture.md 與 workflows/common/code-map/CODE_MAP.md 取代（重構前快照，refactor_next 已落地）

# 歷史相容路徑與死碼

[入口](README.md)

查證：`python workflows/common/code-map/codemap.py json` 的 `imported_by` 欄，再用 `rg` 複查函式／指令層級的使用。

## 1. 兩個歷史相容模組的實際引用者

| 模組 | 產品程式引用 | 測試引用 |
|---|---|---|
| `text_accumulator.py`（268 行） | 只有 `mobile/state.py:13` | `tests/test_text_accumulator.py`（28 個測試）、`tests/test_clipboard_commands.py` |
| `workspace_controller.py`（244 行） | 只有 `mobile/state.py:16` | `tests/test_workspace_controller.py`（38 個測試）、`tests/test_clipboard_commands.py`（13 個測試） |

桌面主線（`app.py`、`app_wiring/`、`modules/`）完全沒有引用這兩個模組。
因此它們實際上是「**手機專用的工作區實作**」，不是沒人用的死碼；移除的前提是手機改走新路徑。

## 2. 舊模組內部的死碼（產品路徑沒有呼叫者）

| 符號 | 位置 | 證據 |
|---|---|---|
| `WorkspaceController.handle_copy`／`handle_paste` | `workspace_controller.py:116-146` | 手機 `/copy`／`/paste` 改走 `_mobile_copy`／`clipboard_read`（`mobile/inputs.py:170-173`）；`rg handle_copy` 只有測試命中 |
| `TextAccumulator` 的 `copy`／`paste` op | `text_accumulator.py:109-112,233-250` | 唯一的生產者就是上一列的兩個死方法 |
| `{"msg_type": ...}` 欄位 | `mobile/inputs.py:44,77`、`mobile/outputs.py:68` | `text_accumulator.py` 沒有讀取 `msg_type` |

## 3. 主線內的死碼／未用協定

| 符號 | 位置 | 證據 |
|---|---|---|
| `MUTE`／`UNMUTE` | `text_to_voice.py:238-243` | 沒有任何生產者（`rg '"MUTE"'`） |
| `recorder_event: chunk_flushed` | `record.py:164` | 消費端只記 debug（`command_router.py:217-218`） |
| `ui_event` role `error`／`buffer_peek` | `tui_renderer.py:71-74` | 桌面沒有生產者（role `error` 只有手機在用） |
| `Message.created_at` | `core/message.py:13` | 沒有讀取者 |
| `utils.clipboard.available()` | `utils/clipboard.py:64` | 產品程式與測試都沒有呼叫 |
| `Workspace.extend`／`replace` | `workspace.py:60,84` | 產品程式沒有呼叫（`rg "\.extend\("`、`rg "\.replace\("` 沒有 Workspace 相關命中） |

re-export 殘留，為了相容舊的匯入路徑：`app.py:23-32`（`wire`、`_dict_to_ui_event`、`_UiEventClass`、`_setup_logging`）、
`mobile_server.py:24-67`（從 `mobile.*` 匯入 41 個名稱，大多加了 `# noqa: F401`）、`text_to_voice.py:29-31`。
目前的使用者：`tests/test_app_wiring.py` 用 `app.wire`、`app._dict_to_ui_event`；`tests/test_text_to_voice.py`
從 `text_to_voice` 匯入 `tts` 函式。手機的 re-export 沒有任何測試或程式使用（mobile 沒有測試）。

## 4. `ai_assist/` 與 `server_sample/`：不屬於產品

| 目錄 | 內容 | 結論 |
|---|---|---|
| `ai_assist/` | `GEMINI.md`、`roadmap.md`、`architecture.md` 等 6 份文件，以及 `tests/01-sandbox`…`09-python-sandbox` 共 12 支實驗腳本 | 另一個專案「Hybrid-Agent-Assist」的實驗室（`ai_assist/GEMINI.md:1-4`）。沒有被任何產品模組匯入；codemap 明確排除（`codemap.py:25`） |
| `server_sample/server.py` | FastAPI 範例伺服器：`/chat` 轉發給 Ollama，回傳 `ChatReply` 格式（`server_sample/server.py:22-60`） | 是 `SERVER.enabled=true` 模式的**測試對端**，不是客戶端的一部分；沒有被匯入、沒有測試 |

兩者都受 git 追蹤（`git ls-files ai_assist server_sample`），最後相關提交是 `eb97d38 sdf`、`f11d2b7 feat: add sample FastAPI server`。
`ai_assist/tests/02-session/session_manager.py` 與根層 `session_manager.py` 同名但沒有關聯。
目前只有 `reports/extension-ideas.md:19,235` 把 `ai_assist/roadmap.md` 當成歷史願景引用。

## 5. 其他根層非程式資料夾

`prompts/`（`utils/prompt_loader.py:3` 用模組相對路徑讀取）、`static/`（手機前端，`mobile_server.py:98-104`）、
`models/kokoro/` 與 `output/`（被 `.gitignore:223-229` 忽略）。
`config.ini` 用 cwd 相對路徑讀取（`config.py:5`），`prompts/`、Kokoro 模型用 `__file__` 相對路徑
（`text_to_voice.py:58-60`）：兩種路徑基準並存。
