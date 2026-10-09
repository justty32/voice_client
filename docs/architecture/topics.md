# 架構文檔：通道與工作流

[架構文檔入口](../architecture.md)

## 3. 通道（topic）規劃

topic 名稱常數在 [`protocol/topics.py`](../../protocol/topics.py)，payload 建構函式與控制字串在
[`protocol/payloads.py`](../../protocol/payloads.py)（下表 payload 欄的 `P.` 即指此檔）。
「生產者」欄必須與 `python workflows/common/code-map/codemap.py topics` 一致：
`tests/test_protocol_contract.py` 以別名表機械比對，括號內為註記、比對時略去；
`TunnelModule` 基底的錯誤回報（`ui_event`）不列。

### 語音與輸入

| topic | 生產者 | 消費者 | payload |
|---|---|---|---|
| `audio` | Recorder | STT | numpy 音訊陣列 |
| `stt_text` | STT | SttGate（依模式分流） | 辨識文字 `str` |
| `raw_text` | SttGate（normal 模式）、CliTextBridge（終端文字） | WorkspaceManager（塞進**當前**工作區） | 文字 `str` |
| `commands` | 終端指令、SttGate（command 模式）、熱鍵 | CommandRouter | `P.command()`；熱鍵為裸字串（`RECORD_TOGGLE`…）；cmd 集合見 `protocol/commands.py` |
| `cli_text` | 終端文字 | CliTextBridge（EXIT 攔截＋顯示＋轉 raw_text） | 文字 `str`（`__EXIT__` 為 EOF） |
| `recorder_event` | Recorder（事件） | CommandRouter（狀態列／錯誤復原） | `P.recorder_event()`；`recording_stopped` 帶 `flushed: bool`（False＝無音訊送 STT，狀態列回待機） |
| `stt_event` | STT（處理結果） | CommandRouter（錯誤訊息＋狀態列回待機） | `P.stt_event()`：`stt_error`（帶 `message`）／`stt_empty`／`stt_done` |

### 控制

| topic | 生產者 | 消費者 | payload |
|---|---|---|---|
| `gate_ctl` | CommandRouter | SttGate（模式切換） | `P.gate_mode()` |
| `app_ctl` | CommandRouter（/exit）、CliTextBridge（EOF） | app.py 主執行緒 | 裸字串 `P.APP_EXIT` |
| `recorder_ctl` | CommandRouter | Recorder | 裸字串 `P.RECORDER_START`／`P.RECORDER_STOP` |
| `tts_ctl` | CommandRouter | AudioPriorityPlayer | 裸字串 `P.TTS_STOP_SPEECH`（停機時 app.py 直接放 `P.TTS_TERMINATE`） |
| `chat_ctl` | CommandRouter（play_last） | ChatFlow | `P.chat_cmd()` |

### 聊天與呈現

| topic | 生產者 | 消費者 | payload |
|---|---|---|---|
| `outbound` | WorkspaceCommandMixin（CommandRouter /send） | HttpClient | `P.outbound_chat()` |
| `inbound` | HttpClient | ChatFlow | 伺服器回應 dict（`type`＝ChatReply／StatusUpdate／Error） |
| `summary_req` | ChatFlow | SummaryGenerator | `P.summary_request()` |
| `summary_out` | SummaryGenerator | ChatFlow（呈現摘要；失敗改播原文） | `{"type":"status"／"summary","text"}`；失敗為 `{"type":"summary_failed","message","text"}`（`text`＝原文） |
| `tts` | ChatFlow | AudioPriorityPlayer | `P.tts_item()` |
| `ui_event` | ChatFlow、CliTextBridge、CommandRouter、WorkspaceCommandMixin、SttGate | TuiRenderer | `P.ui_status()`／`P.ui_message()`／`P.ui_clear()` |

`ui_event` 的 message role 現有 `system／assistant／summary／voice／user／sending`；`error`、`buffer_peek` 只有 TuiRenderer 支援、桌面無生產者。

關鍵設計：

- **`raw_text` 的唯一消費者是「當前工作區」**。多個工作區並存，但只有被
  `/ws` 選中的那一個會收到新辨識文字；不自動寫入其他工作區、不自動轉發。
- **熱鍵與斜線指令一律是生產者**：按鍵只產生一筆指令資料進 `commands`，
  由 CommandRouter 統一消費後再發控制訊息，輸入端不直接操控任何模組。

## 4. 工作流

1. **語音資料流**：Recorder →`audio`→ STT →`raw_text`→ 當前工作區；
   STT 每段的結局（錯誤／空／完成）另經 `stt_event` 回報 CommandRouter，狀態列據此回「待機」。
2. **指令流**：熱鍵／終端／語音指令 →`commands`→ CommandRouter →
   （`recorder_ctl`、`tts_ctl`、`ui_event`、`outbound`…）。
3. **聊天流**：/send 將 buffer 組成 payload →`outbound`→ HttpClient →`inbound`→
   ChatFlow（寫入歷史；依摘要門檻直接 `tts` 或發 `summary_req`）。
4. **呈現**：`ui_event`→ TuiRenderer；`tts`→ AudioPriorityPlayer。

### 手機邊緣（不新增 topic）

手機入口（`mobile/state.py`）用同一組 topic，只替換 legacy queue 的兩端：
前端輸入放進 `cli_text`、`cli_cmd`、`key_signal`、`audio_out`、`recorder_event`（瀏覽器錄音停止＝`recording_stopped`、`flushed=True`）；
`ui_event`（不經 dict→UiEvent 轉換）、`tts`、`tts_ctl` 由 `mobile/edge.py` 的 `EdgeSink` 依投遞順序轉成 WS 事件，
`recorder_ctl`、`app_ctl` 消費後丟棄。WS 專屬事件（`clipboard_*`、`sessions`）由邊緣直接推送，不進 Exchange。
