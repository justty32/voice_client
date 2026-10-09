# 階段 7b：手機走 Data Tunnel

[總覽](README.md)｜痛點 1、6、7；P1、P7；D3、D4、D9、D10

前置：階段 1、3、4、5、6、7a 完成。

## 目標

手機入口改用 `build_core()` 的同一組 Exchange＋原生模組，只替換「邊緣裝置」：瀏覽器錄音代替 Recorder、WS 推送代替 TuiRenderer／AudioPriorityPlayer。
`text_accumulator.py`、`workspace_controller.py` 不再被產品碼引用。手機行為以桌面為準（D9），差異表見 `wf/architecture/entrypoints.md` §4。

## 設計（D3 方案 A）

| 手機邊緣 | 對應 `parts.queues[...]` | 說明 |
|---|---|---|
| WS binary frame → `_to_wav()` | put `audio_out`（Recorder 的輸出 queue） | 之前先 put `recorder_event`：`recorder_event("recording_stopped", flushed=True)`，讓狀態列走「處理中」→（階段 4c `stt_done`）→「待機」 |
| `{"type":"text"}` | put `cli_text` | CliTextBridge → ui_event(user)＋raw_text → 當前工作區（同桌面；不再同時寫 stt 工作區） |
| `{"type":"cmd"}` | put `cli_cmd`：`command(cmd, args)` | 走 CommandRouter；`/exit` 在邊緣攔下不送（手機無 exit） |
| `{"type":"signal"}` | put `key_signal`（`QUICK_SEND`／`FORCE_STOP_TTS`） | 與熱鍵同路 |
| `clipboard_data` | 邊緣直接 `wm.get(wm.current).append(line)`（階段 3 已鎖）＋推 system 訊息 | 對應桌面 `_handle_paste` 的後半 |
| `ui_event_q` | 消費：InboxAdapter **不帶 transform**，pusher 原樣 `send_json(dict)` | 前端已吃 `message/status/clear` |
| `tts_input` | 消費：pusher 轉 `{"type":"tts","text","priority"}` | |
| `tts_cmd` | 消費：`STOP_SPEECH` → `{"type":"tts_control","action":"stop"}`；`TERMINATE` 忽略 | |
| `recorder_cmd`、`app_ctl` | 消費後丟棄（log debug） | 手機不控桌面錄音 |
| `sessions_refresh` | 邊緣：cmd 屬 `SESSION_COMMANDS` 時，派發後推 `{"type":"sessions",...}` | 桌面沒有此事件 |

剪貼簿 `/copy`：`CommandRouter.__init__` 加 `clipboard=None` 參數（預設 `utils.clipboard` 模組，behavior-preserving）；
手機傳入 `BrowserClipboard`：`copy(text)` → 推 `clipboard_write` 回 `(True, "")`；`paste()` → 推 `clipboard_read` 回 `(False, "等待瀏覽器回傳")`，
邊緣改在 `clipboard_data` 到達時完成貼上（上表）。桌面 `_handle_paste` 的錯誤訊息路徑會把「等待瀏覽器回傳」顯示成 `[錯誤] …`——
邊緣在 `/paste` 時**先攔截**不送 CommandRouter，直接推 `clipboard_read`，避免該訊息。

## 動到的檔案

- `mobile/state.py`：`MobileState` 改持 `parts: CoreParts`（`build_core(config, session_manager=…)`）、`voice_to_text`（真實或注入）、`http_client`、`summary_gen`、`lifecycle`、`current_ws`；刪 `text_accumulator`、`wsc`、`acc_*` queue。
- `mobile/inputs.py`：`_route_cmd` 的 if/elif（95-186）全部刪除，改上表的轉送；`_mobile_copy/_mobile_paste` 改為上表邊緣邏輯；`_handle_audio` 改 put `recorder_event`＋`audio_out`。
- `mobile/outputs.py`：`_handle_response`（28-53）刪除（ChatFlow 接手）；`_output_pusher` 改只輪詢 `ui_event_q`、`tts_input`、`tts_cmd` 三個 queue。
- `mobile/push.py`：只保留 `_push`（直接進 `ui_event_q`）與 `sessions` 推送 helper。
- `mobile_server.py`：lifespan 用 `state.lifecycle.start_all()/stop_all()`；關閉前依 D10 把 `wm.get("buffer")` 非空時 `export(<export_dir>/_buffer_temp.json)`。
- `modules/command_router.py`、`modules/command_handlers/workspace.py:131,138`：`clipboard` 注入（上文）。
- `app_wiring/assembly.py`：若 `build_core` 需要讓手機跳過某些消費者（`recorder_cmd`、`app_ctl` 仍由 wire 註冊，手機只是不讀），不需改。
- `static/app.js`：**不改**（事件型別集合不變：`message/status/tts/tts_control/clipboard_write/clipboard_read/sessions/clear`）。
- `docs/architecture/migration.md`、`docs/architecture/topics.md`（手機邊緣一節）、`docs/user_manual/mobile.md`、CODE_MAP。

## 行為變更清單（D9，全部【改行為】，各補測試）

1. 工作區集合變 `buffer/stt`，`chat` 唯讀（`/ws chat` 回唯讀訊息；`/del /move /to_top` 不再作用於 chat）。
2. STT 文字只進當前工作區。
3. `/switch`（無參數、無 default）自動建立 default。
4. `/list` 尾行文字「當前使用session：」。
5. Error 回覆 role 為 `system`（前端 `error` 樣式不再觸發；`static/style.css` 保留無妨）。
6. `/import` 無參數回錯誤（不再讀 `_buffer_temp.json`）；D10 保留停機匯出。
7. `/help` 為桌面文字；多了語音指令解析（`voice` 需 SttGate command 模式，手機無 F7，實際不會觸發）。
8. 7a 的 8 案事件序列維持，文案依上列調整。

## 測試

- `tests/test_mobile_server.py`：更新文案斷言；新增上列 1–6 各一案；新增「`/paste` 不產生 `[錯誤]` 訊息」。
- `tests/test_mobile_wiring.py`：`build_mobile_state(tmp)` 後 `parts.exchange.routes() == protocol.topics.ALL`；`state` 不含 `text_accumulator` 屬性。
- `tests/test_command_router_workspace_edit.py`：`clipboard` 注入 fake 的 `/copy` 案（取代目前 `mock.patch("utils.clipboard…")` 的其中一案）。
- `rg -n "text_accumulator|workspace_controller" --type py -g '!tests/*'` → 只剩兩個模組本身。

## D4：舊模組處置（預設先不刪）

- 預設：`text_accumulator.py`、`workspace_controller.py` 檔頭加 `"""DEPRECATED：自 2026-xx 起無產品碼引用；待使用者裁示後刪除。"""`；
  CODE_MAP「歷史相容」節改寫；三個測試檔保留（仍綠）。
- 使用者同意後的獨立 commit：`git rm text_accumulator.py workspace_controller.py tests/test_text_accumulator.py tests/test_workspace_controller.py tests/test_clipboard_commands.py`，
  基準減 79；`docs/architecture/migration.md` §5 刪該列；CODE_MAP 刪該節。

## 步驟

1. `CommandRouter` 剪貼簿注入＋測試（桌面行為不變）。
2. `mobile/state.py` 改 `build_core`；pusher 三 queue；輸入轉送；7a 測試逐案轉綠（文案依 D9 改斷言）。
3. 邊緣 `sessions`、`/paste` 攔截、`recorder_event`、D10 匯出。
4. 刪手機內舊 if/elif 與 `_handle_response`；`rg` 確認舊模組零引用。
5. D4 預設處理；文件同步；WAIT_USER 記真機項。

## 驗證命令

```bash
.venv/bin/python -m pytest -q                                   # 全綠；≥ 上階段 + 至少 10
.venv/bin/python -m pytest -q tests/test_mobile_server.py tests/test_mobile_wiring.py -v
rg -n "text_accumulator|workspace_controller" --type py -g '!tests/*' -g '!text_accumulator.py' -g '!workspace_controller.py'   # 無命中
python workflows/common/code-map/codemap.py deps mobile.state    # imports 含 app_wiring.assembly，不含 text_accumulator
```

## Done when

- 上述 `rg` 無命中；`tests/test_mobile_wiring.py` 存在；pytest 全綠且測試數 ≥ 438（D4 刪除前）。
- `python workflows/common/code-map/codemap.py topics` 的生產者／消費者不因手機而新增 topic（手機只用既有 17＋`stt_event`）。
- CODE_MAP「手機」節與 `docs/architecture/migration.md` 已無「待對齊」字樣。

建議 commit：`feat(mobile): 手機入口改走 Data Tunnel，共用 build_core 與 CommandRouter`；D4 另 commit `chore: 移除 text_accumulator／workspace_controller`
