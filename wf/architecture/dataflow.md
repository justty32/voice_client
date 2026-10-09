# 資料流與 topic 協定（桌面入口）

[入口](README.md)

查證指令：`python workflows/common/code-map/codemap.py topics`（列出所有生產者與消費者）。
接線位置：`app_wiring/topology.py:61-135`。payload 形狀依實際 emit／put 呼叫點整理。

## 1. 接入方式：legacy queue 與原生模組

legacy 模組（裸 `queue.Queue`，模組本體不知道有隧道）用 Adapter 接上：

| legacy 元件 | 輸出（OutboxAdapter → topic） | 輸入（topic → InboxAdapter） |
|---|---|---|
| KeyboardListener＋LocalControl（共用 queue） | `commands` | — |
| TerminalInput | `commands`（cmd queue）、`cli_text` | — |
| Recorder | `audio`、`recorder_event` | `recorder_ctl` |
| VoiceToText | `stt_text` | `audio` |

| legacy 元件 | 輸出 | 輸入 |
|---|---|---|
| HttpClient | `inbound` | `outbound` |
| SummaryGenerator | `summary_out` | `summary_req` |
| AudioPriorityPlayer | — | `tts`、`tts_ctl` |
| TuiRenderer | — | `ui_event`（經 `_dict_to_ui_event` 轉換） |
| app.py 主執行緒 | — | `app_ctl`（`topology.py:134-135`） |

原生 `TunnelModule`（呼叫 `attach()`，`topology.py:125-129`）：

| 模組 | consumes | emits |
|---|---|---|
| WorkspaceManager | `raw_text` | （只有基底錯誤 `ui_event`） |
| SttGate | `stt_text`、`gate_ctl` | `ui_event`、`raw_text`、`commands` |
| CommandRouter | `commands`、`recorder_event` | `recorder_ctl`、`gate_ctl`、`tts_ctl`、`chat_ctl`、`outbound`、`app_ctl`、`ui_event` |
| ChatFlow | `inbound`、`summary_out`、`chat_ctl` | `tts`、`summary_req`、`ui_event` |
| CliTextBridge | `cli_text` | `ui_event`、`raw_text`、`app_ctl` |

## 2. topic 表：輸入與語音

| topic | 生產者 → 消費者 | payload |
|---|---|---|
| `commands` | 熱鍵／本機 IPC、TerminalInput、SttGate → CommandRouter | 熱鍵：裸字串 `"RECORD_TOGGLE"` 等 5 種（`keyboard_listener.py:74-82`）；終端與語音：`{"cmd","args"}` |
| `cli_text` | TerminalInput → CliTextBridge | `str`，或 `"__EXIT__"`（`terminal_input.py:5`） |
| `audio` | Recorder → VoiceToText | `io.BytesIO`（WAV，`record.py:153-163`） |
| `recorder_event` | Recorder → CommandRouter | `{"event": recording_started/recording_stopped/chunk_flushed/error, "message"?}` |
| `stt_text` | VoiceToText → SttGate | `str`（`voice_to_text.py:53-54`，空字串不送） |
| `raw_text` | SttGate、CliTextBridge → WorkspaceManager | `str`，寫進**當前**工作區 |

`chunk_flushed`（`record.py:164`）沒有任何消費邏輯，CommandRouter 只記 debug（`command_router.py:217-218`）。

## 3. topic 表：控制

| topic | 生產者 → 消費者 | payload |
|---|---|---|
| `gate_ctl` | CommandRouter → SttGate | `{"mode": "normal"/"command"}` |
| `recorder_ctl` | CommandRouter → Recorder | 裸字串 `"START"`／`"STOP"` |
| `tts_ctl` | CommandRouter → TTS | 裸字串 `"STOP_SPEECH"`（`TERMINATE` 由 `app.py:203` 直接放進 queue；`MUTE`/`UNMUTE` 沒有生產者） |
| `chat_ctl` | CommandRouter → ChatFlow | `{"cmd":"play_last"}` |
| `app_ctl` | CommandRouter（/exit）、CliTextBridge（EOF） → 主執行緒 | 裸字串 `"EXIT"` |

終端 `/exit` 會同時送出 `{"cmd":"/exit"}` 和 `EXIT_SIGNAL`（`terminal_input.py:43-45`），
所以 `app_ctl` 會收到兩次 `EXIT`；目前不會出問題。

## 4. topic 表：聊天與呈現

| topic | 生產者 → 消費者 | payload |
|---|---|---|
| `outbound` | CommandRouter `/send` → HttpClient | `{"Content","Title","Metadata":{"ClientTime"}}`（`command_handlers/workspace.py:192-196`） |
| `inbound` | HttpClient → ChatFlow | `{"type":"ChatReply","Title","Content":{"full_response"},"model"}`、`{"type":"Error","message"}`、遠端的 `{"type":"StatusUpdate","text"}` |
| `summary_req` | ChatFlow → SummaryGenerator | `{"cmd":"summary","text","title"}` |
| `summary_out` | SummaryGenerator → ChatFlow | `{"type":"status","text"}`、`{"type":"summary","text","model"}` |
| `tts` | ChatFlow → TTS | `{"text","priority": high/medium/low}` |

| topic | 生產者 → 消費者 | payload |
|---|---|---|
| `ui_event` | 全部原生模組＋`core/module.py` 錯誤 → TuiRenderer | `{"type":"status","text"}`、`{"type":"message","role","text"}`、`{"type":"clear"}` |

`ui_event` 的 role 有：system、assistant、summary、voice、user、sending；TuiRenderer 另外支援
error、buffer_peek（`tui_renderer.py:71-74`），桌面沒有生產者。
文件 `docs/architecture/topics.md` 把 `tts` 的生產者寫成「ChatFlow、SummaryGenerator、CommandRouter」，
實際上只有 ChatFlow（codemap topics）。

## 5. 協定風格不一致（事實，不含評價）

- 控制 topic 有些用裸字串（`recorder_ctl`、`tts_ctl`、`app_ctl`），有些用 dict（`gate_ctl`、`chat_ctl`）。
- `commands` 一個 topic 同時接受裸字串與 dict，在 `command_router.py:62-74` 正規化。
- HTTP payload 用大寫鍵（`Content`/`Title`），內部訊息用小寫鍵。
- topic 名稱與 payload 都是各檔案內的字面字串，沒有集中定義（`rg -n "TOPIC_|TypedDict"` 沒有結果）。
- 斜線指令集有三份平行定義：`terminal_input.py:7`、`command_router.py:80-159`、`command_handlers/session.py:72-77`（help）。

## 6. 啟停順序（`app.py:main`）

1. `load_config`、`setup_logging`（`app.py:64-65`）
2. 建立 15 個裸 queue（71-85）
3. SessionManager＋default session（88-91）
4. 建構 9 個 legacy 元件（99-107），建構 5 個原生模組（110-118）
5. `Exchange()`＋`wire()`（121-148）
6. start 9 個 legacy（151-159）→ start 5 個原生模組（162-166）→ `exchange.start()`（167）
7. 啟動提示直接放進 `ui_event_queue`（172-185）
8. 主執行緒以 `app_ctl.get(timeout=0.5)` 等待 `EXIT`（189-199）
9. finally：`TERMINATE` → 依建構順序 stop legacy → stop 原生 → `exchange.stop()`（203-218）

停機事實：legacy 的 `stop()` 只把旗標設為 False，不 join（`record.py:50-51`、`voice_to_text.py:39-40`、
`http_client.py:57-58`、`summary_generator.py:41-42`、`terminal_input.py:24-25`、`tui_renderer.py:32-33`）；
`AudioPriorityPlayer.stop()` 不 join dispatcher（`text_to_voice.py:97-100`）。只有 `TunnelModule.stop()`
與 `Exchange.stop()` 會 `join(timeout=2)`。停機時沒有 drain，outbox 裡還沒處理的訊息會直接丟失。
`docs/architecture/runtime.md` 說「`stop()` 以 `join(timeout)` 收尾」，與 legacy 模組的實際行為不符。

## 7. Exchange 能力邊界

- 一個 topic 只能有一個消費者，重複註冊會拋例外（`core/exchange.py:30-33`）；沒有 fan-out。
- 沒有 unregister，也沒有背壓：`Inbox`／`Outbox` 都是無上限的 `queue.Queue()`（`core/endpoint.py:14,30`）。
- `Message.created_at` 只有定義（`core/message.py:13`），沒有任何讀取者。
- 沒有路由的訊息會記 warning 後丟棄（`core/exchange.py:50-53`）。
