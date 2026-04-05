# Voice Client - 架構設計文件

## 1. 專案概述

一個以 Python 開發的多模態終端機 AI 客戶端，整合語音與文字輸入，透過全域快捷鍵控制，搭配本地小型語言模型 (SLM) 做預處理，最終將訊息發送至遠端/本地大型語言模型 (LLM) 並接收回覆。

核心設計理念：
- **使用者掌控權**：暫存區 (Buffer) 完全由使用者控制，SLM 僅在明確觸發時介入
- **雙軌輸入**：語音 + 文字共同操作同一個暫存區
- **語音優先級佇列**：多層級語音輸出，高優先級可打斷低優先級
- **完全 Queue 解耦**：所有模組之間僅透過 Queue 通訊，不持有彼此的參照。每個模組只知道自己的輸入/輸出 Queue，不知道對面是誰。Main Loop 作為純粹的路由器/調度器，將訊息從一個 Queue 轉發到另一個 Queue。

---

## 2. 設計原則

### 2.1 模組分離規則
1. **模組之間零直接引用**：模組 A 不可 import 模組 B，也不可持有模組 B 的實例引用
2. **所有通訊走 Queue**：模組只與自己的 input queue / output queue / cmd queue 互動
3. **控制指令也走 Queue**：start/stop/flush 等控制命令透過 `cmd_queue` 下達，不直接呼叫方法
4. **Main Loop 是路由器**：只做「從 Queue A 取出 → 轉發到 Queue B」，不含業務邏輯
5. **新增模組 = 新增 Queue + 路由規則**：擴充時不需修改現有模組

### 2.2 模組標準介面
每個模組都遵循相同的生命週期介面：

```python
class ModuleBase:
    def __init__(self, config, **queues):
        # 只接收 config 與 Queue 們，不接收其他模組實例
        pass

    def start(self):
        # 啟動背景執行緒
        pass

    def stop(self):
        # 安全停止
        pass
```

---

## 3. 系統架構圖

```
                +-----------------------+
                |   KeyboardListener    |
                +-----------+-----------+
                            |
                      key_signal_queue
                            |
+---------------------------v---------------------------+
|                                                       |
|                  Main Loop (Router)                   |
|                                                       |
|   純粹的訊息路由器：從各 output queue 取出訊息，       |
|   根據類型轉發到對應模組的 input/cmd queue。           |
|                                                       |
+--+------+------+------+------+------+------+------+--+
   |      |      |      |      |      |      |      |
   v      v      v      v      v      v      v      v
Recorder STT   CLI   SLM   HTTP   TTS  TUI  Interrupt Session
```

### 完整資料流

```
[語音輸入]                              [文字輸入]
    |                                       |
    v                                       v
 Recorder                            TerminalInput
    | audio_queue                       |           |
    v                           cli_text_queue  cli_cmd_queue
 VoiceToText (STT)                      |           |
    | stt_output_queue                  |           |
    |                                   |           |
    +------------> Main Loop <----------+-----------+
                      |
                      v
               slm_input_queue
                      |
                      v
               SLMProcessor
                      |
             slm_output_queue
                      |
                      v
                  Main Loop
                                  |
                           send_queue
                                  |
                                  v
                            HttpClient
                                  |
                           recv_queue
                                  |
                                  v
                            Main Loop
                                  |
                    +-------------+-------------+
                    |                           |
                    v                           v
             ui_event_queue              tts_input_queue
                    |                           |
                    v                           v
              TuiRenderer               AudioPriorityPlayer
```

---

## 4. 模組設計

### 4.1 config.py - 設定載入器
- **職責**：讀取 `config.ini`，回傳 `ConfigParser` 物件
- **格式**：INI（`configparser`）
- **區段**：AUDIO, CONTROL, STT, SLM, LLM, SERVER, TTS, INTERRUPT, SESSION, WORKSPACE, UI, LOGGING
- **無 Queue**：純工具函式，啟動時呼叫一次

### 4.2 keyboard_listener.py - 全域鍵盤監聽器

純粹的按鍵事件轉譯器，只負責偵測按鍵並發出結構化訊號。

| Queue | 方向 | 內容 |
|---|---|---|
| `key_signal_queue` | OUT | `SignalEvent` 枚舉值或 `(event_type, key_name)` tuple |

- **快捷鍵**（皆可在 config 中自訂）：
  - **F8**：錄音開關（toggle）
  - **F9**：快捷暫存區發送（觸發 SLM flush）
  - **F10**：強制結束當前正在播放的語音
- **訊號類型**：`RECORD_TOGGLE`, `QUICK_SEND`, `FORCE_STOP_TTS`

### 4.3 record.py - 錄音器

獨立的錄音工作器，透過 cmd queue 接收開始/停止指令。

| Queue | 方向 | 內容 |
|---|---|---|
| `recorder_cmd_queue` | IN | `"START"`, `"STOP"` |
| `audio_queue` | OUT | WAV `BytesIO` buffer |
| `recorder_event_queue` | OUT | `{"event": "recording_started"}`, `{"event": "recording_stopped"}`, `{"event": "chunk_flushed"}` |

- **分段邏輯**：
  1. 強制切片：錄音超過 `chunk_duration`（預設 60 秒）後偵測到停頓即切片
  2. VAD 模式：靜音超過 `silence_seconds` 秒即切片
  3. 最大時長：`max_duration > 0` 時強制切片
- **設計重點**：Recorder 不知道誰在消費 audio_queue，也不知道誰在發 cmd

### 4.4 voice_to_text.py - 語音轉文字工作器

純粹的 STT 管線，從 audio queue 取音訊，轉成文字放入 output queue。

| Queue | 方向 | 內容 |
|---|---|---|
| `audio_queue` | IN | WAV `BytesIO` buffer |
| `stt_output_queue` | OUT | `str`（轉譯文字） |

- **依賴**：`faster-whisper`
- **參數**：model_size, device, compute_type, language, beam_size, vad_filter（從 config 讀取）

### 4.5 slm_processor.py - 本地 SLM 預處理中心

獨立的文字處理器，所有控制都走 Queue。

| Queue | 方向 | 內容 |
|---|---|---|
| `slm_input_queue` | IN | `{"type": "text", "text": "...", "msg_type": "VoiceChat"}` |
| `slm_cmd_queue` | IN | `{"cmd": "flush", "msg_type": "VoiceChat"}`, `{"cmd": "summary", "text": "...", "title": "..."}` |
| `slm_output_queue` | OUT | `{"type": "payload", "payload": {...}}` (JSON payload 準備發送), `{"type": "tts", "text": "...", "priority": "medium"}` (摘要語音) |

- **兩條處理線**：
  1. **前置處理**：累積文字片段 → 靜默超時或 flush 指令觸發 → SLM 清洗 → 組裝 payload 送出
  2. **後置摘要**：接收 LLM 回覆全文 → SLM 生成摘要 → 送出 TTS 任務
- **訊息類型**：VoiceChat, VoiceCommand, TextChat
- **SLMProcessor 不知道 HttpClient 或 TTS 的存在**，它只往 `slm_output_queue` 放東西

### 4.6 http_client.py - 網路與通訊層

純粹的 HTTP 收發器 / 離線 LLM 包裝器。

| Queue | 方向 | 內容 |
|---|---|---|
| `send_queue` | IN | `dict`（JSON payload） |
| `recv_queue` | OUT | `dict`（伺服器回應或本地 LLM 回應） |

- **雙模式**：
  1. **線上** (`SERVER.enabled = true`)：HTTP POST + 重試
  2. **離線** (`SERVER.enabled = false`)：本地 LLM 直接回應
- **失敗處理**：保存 payload 至 `failed_payloads_dir`
- **回應類型**：ChatReply, ApprovalRequest, StatusUpdate, Error

### 4.7 text_to_voice.py - 音訊優先級播放器

獨立的 TTS 播放管線，所有控制走 Queue。

| Queue | 方向 | 內容 |
|---|---|---|
| `tts_input_queue` | IN | `{"text": "...", "priority": "high\|medium\|low"}` |
| `tts_cmd_queue` | IN | `"STOP_SPEECH"`, `"MUTE"`, `"UNMUTE"`, `"TERMINATE"` |

- **架構**：Dispatcher Thread + TTS Worker Process（獨立 process 避免 GIL 阻塞）
- **優先級**：
  - `HIGH`：系統警告/授權 → 打斷當前播放
  - `MEDIUM`：對話回覆/摘要
  - `LOW`：背景進度/總結
- **引擎**：Kokoro TTS API（`pygame`）或 `pyttsx3`（離線備援）

### 4.8 terminal_input.py - CLI 文字輸入介面

| Queue | 方向 | 內容 |
|---|---|---|
| `cli_text_queue` | OUT | `str`（一般文字） |
| `cli_cmd_queue` | OUT | `{"cmd": "/new", "args": ["title"]}` 等結構化指令 |

- **斜線指令**：/new, /switch, /list, /perms, /exit, /help, /clear
- **EXIT_SIGNAL**：特殊字串，通知主迴圈結束

### 4.9 tui_renderer.py - TUI 渲染層

純粹的 UI 輸出，只從 Queue 讀取事件來渲染。

| Queue | 方向 | 內容 |
|---|---|---|
| `ui_event_queue` | IN | `UiEvent(event_type, data)` |
| `approval_result_queue` | OUT | `{"request_id": "...", "result": "approved_once\|approved_always\|rejected", ...}` |

- **事件類型**：message, approval_request, progress, status, tts_playing
- **授權請求**：阻塞式 UI（允許本次 / 永久允許 / 拒絕），含逾時自動拒絕
- **狀態列**：待機 / 錄音中 / 處理中 / 傳送中 / 靜音

### 4.10 session_manager.py - 會話管理器

不使用 Queue（同步呼叫），因為它是純資料存取層，被 Main Loop 直接使用。

- **職責**：管理聊天串 (Title) 建立/切換/列表 + 操作權限記憶
- **持久化**：sessions.json + permissions.json
- **為何不用 Queue**：Session 操作是同步且極快的（記憶體讀寫 + 檔案 I/O），不需要非同步。Main Loop 需要立即拿到結果（如 `current_title`），走 Queue 反而增加不必要的複雜度。

### 4.11 utils/llm_client.py - LLM 呼叫介面
- **職責**：統一的 LLM API 呼叫，支援 Ollama 與 OpenAI 相容介面
- **介面**：`chat(system_prompt, user_message) -> str`
- **被 SLMProcessor 與 HttpClient（離線模式）使用**

### 4.12 utils/prompt_loader.py - 提示詞載入器
- **職責**：從 `prompts/` 目錄載入 `.txt` 提示詞檔案
- **提示詞**：slm_concat, slm_summary, llm_system

---

## 5. Queue 通訊總覽

```
┌─────────────────┐     key_signal_queue      ┌────────────┐
│KeyboardListener │ ────────────────────────>  │            │
└─────────────────┘                            │            │
                                               │            │
┌─────────────────┐     recorder_cmd_queue     │            │
│    Recorder     │ <────────────────────────  │            │
│                 │ ──> audio_queue ──────>     │            │
│                 │ ──> recorder_event_queue >  │            │
└─────────────────┘                            │            │
                                               │            │
┌─────────────────┐     audio_queue            │            │
│  VoiceToText    │ <────────────────────────  │            │
│                 │ ──> stt_output_queue ───>   │   Main     │
└─────────────────┘                            │   Loop     │
                                               │  (Router)  │
┌─────────────────┐     cli_text_queue         │            │
│ TerminalInput   │ ────────────────────────>  │            │
│                 │ ──> cli_cmd_queue ───────>  │            │
└─────────────────┘                            │            │
                                               │            │
┌─────────────────┐     slm_input_queue        │            │
│  SLMProcessor   │ <────────────────────────  │            │
│                 │ <── slm_cmd_queue ───────── │            │
│                 │ ──> slm_output_queue ───>   │            │
└─────────────────┘                            │            │
                                               │            │
┌─────────────────┐     send_queue             │            │
│   HttpClient    │ <────────────────────────  │            │
│                 │ ──> recv_queue ─────────>   │            │
└─────────────────┘                            │            │
                                               │            │
┌─────────────────┐     tts_input_queue        │            │
│ AudioPriority   │ <────────────────────────  │            │
│ Player          │ <── tts_cmd_queue ──────── │            │
└─────────────────┘                            │            │
                                               │            │
┌─────────────────┐     ui_event_queue         │            │
│  TuiRenderer    │ <────────────────────────  │            │
│                 │ ──> approval_result_queue > │            │
└─────────────────┘                            └────────────┘
```

### Queue 清單（共 15 個）

| # | Queue 名稱 | 生產者 | 消費者 | 資料型別 |
|---|---|---|---|---|
| 1 | `key_signal_queue` | KeyboardListener | Main Loop | SignalEvent / tuple |
| 2 | `recorder_cmd_queue` | Main Loop | Recorder | str: "START" / "STOP" |
| 3 | `audio_queue` | Recorder | VoiceToText | BytesIO (WAV) |
| 4 | `recorder_event_queue` | Recorder | Main Loop | dict: {event: ...} |
| 5 | `stt_output_queue` | VoiceToText | Main Loop | str |
| 6 | `cli_text_queue` | TerminalInput | Main Loop | str |
| 7 | `cli_cmd_queue` | TerminalInput | Main Loop | dict: {cmd, args} |
| 8 | `slm_input_queue` | Main Loop | SLMProcessor | dict: {type, text, msg_type} |
| 9 | `slm_cmd_queue` | Main Loop | SLMProcessor | dict: {cmd, ...} |
| 10 | `slm_output_queue` | SLMProcessor | Main Loop | dict: {type: "payload"/"tts", ...} |
| 11 | `send_queue` | Main Loop | HttpClient | dict (JSON payload) |
| 12 | `recv_queue` | HttpClient | Main Loop | dict (回應) |
| 13 | `tts_input_queue` | Main Loop | AudioPriorityPlayer | dict: {text, priority} |
| 14 | `tts_cmd_queue` | Main Loop | AudioPriorityPlayer | str: 控制指令 |
| 15 | `ui_event_queue` | Main Loop | TuiRenderer | UiEvent |
| 16 | `approval_result_queue` | TuiRenderer | Main Loop | dict: 授權結果 |

---

## 6. JSON 通訊協定

### 客戶端 → 伺服器
```json
{
  "Title": "聊天串名稱",
  "Content": "處理後的文字內容",
  "Metadata": {
    "ClientTime": "2026-04-05T12:00:00+00:00",
  }
}
```

### 伺服器 → 客戶端
```json
{
  "Title": "聊天串名稱",
  "Content": {
    "full_response": "完整回覆文字",
    "status_update": "短摘要",
  },
}
```

---

## 7. 主迴圈路由邏輯

Main Loop 是純粹的路由器，不含業務邏輯。它的工作就是輪詢所有 output queue 並轉發。

```python
while True:
    # ── A. 鍵盤訊號 → 轉發控制指令 ──
    #   RECORD_TOGGLE  → recorder_cmd_queue.put("START"/"STOP")（追蹤錄音狀態）
    #   QUICK_SEND     → slm_cmd_queue.put({"cmd": "flush"})
    #   FORCE_STOP_TTS → tts_cmd_queue.put("STOP_SPEECH") + ui_event_queue 狀態更新

    # ── B. 錄音器事件 ──
    #   recorder_event_queue → ui_event_queue（更新狀態列）

    # ── C. STT 輸出 → SLM ──
    #   stt_output_queue → slm_input_queue（type="text", msg_type="VoiceChat"）

    # ── D. CLI 文字 → SLM ──
    #   cli_text_queue → slm_input_queue（type="text", msg_type="TextChat"）

    # ── E. CLI 指令 → Session 操作 ──
    #   cli_cmd_queue → session_manager 方法呼叫 → ui_event_queue

    # ── F. SLM 輸出 → 路由到 HTTP 或 TTS ──
    #   slm_output_queue:
    #     type="payload" → send_queue
    #     type="tts"     → tts_input_queue

    # ── G. HTTP 回應 → 路由到 TUI + TTS + SLM ──
    #   recv_queue:
    #     ChatReply → ui_event_queue + slm_cmd_queue(summary) + tts_input_queue
    #     ApprovalRequest → 權限檢查 → ui_event_queue 或自動回應
    #     StatusUpdate → tts_input_queue
    #     Error → ui_event_queue + tts_input_queue

    # ── H. 授權結果 → HTTP 回傳 ──
    #   approval_result_queue → send_queue

    # ── I. 自動備份 ──

    sleep(0.05)
```

---

## 8. 目錄結構

```
voice_client/
├── main.py                  # 主程式入口 + 主迴圈 (Router)
├── config.py                # 設定載入
├── config.ini               # 設定檔
├── keyboard_listener.py     # 全域鍵盤監聽
├── record.py                # 錄音器
├── voice_to_text.py         # 語音轉文字 (STT)
├── slm_processor.py         # 本地 SLM 前置/後置處理
├── http_client.py           # 網路通訊 / 離線 LLM
├── text_to_voice.py         # TTS 優先級播放器
├── terminal_input.py        # CLI 文字輸入
├── tui_renderer.py          # TUI 渲染 (rich)
├── session_manager.py       # 會話管理（同步呼叫）
├── utils/
│   ├── __init__.py
│   ├── llm_client.py        # LLM 呼叫介面 (Ollama/OpenAI)
│   └── prompt_loader.py     # 提示詞載入
├── prompts/
│   ├── slm_concat.txt       # 語音文字清洗 prompt
│   ├── slm_summary.txt      # 回覆摘要 prompt
│   └── llm_system.txt       # LLM 系統 prompt
├── output/                  # 工作空間
│   ├── .sessions.json
│   ├── .permissions.json
│   ├── system.log
│   └── failed/
└── plans/
```

---

## 9. 執行緒/行程模型

| 元件 | 類型 | 備註 |
|---|---|---|
| Main Loop | 主執行緒 | 純路由，sleep(0.05) 輪詢 |
| KeyboardListener | 背景執行緒 (pynput) | 全域鍵盤回呼 |
| Recorder._record_worker | Daemon Thread | 持續讀取麥克風 + 監聽 cmd queue |
| VoiceToText | Daemon Thread | 持續 STT |
| SLMProcessor._pre_loop | Daemon Thread | 前置清洗 + 監聽 cmd queue |
| SLMProcessor._post_loop | Daemon Thread | 後置摘要 |
| HttpClient._loop | Daemon Thread | 網路請求 / 本地 LLM |
| TerminalInput | Daemon Thread | 讀取 stdin |
| TuiRenderer._event_loop | Daemon Thread | UI 渲染 |
| AudioPriorityPlayer._dispatcher | Daemon Thread | TTS 調度 + 監聽 cmd queue |
| TTS Worker | **子 Process** | 獨立 process 做語音合成播放 |

---

## 10. 擴充範例

### 範例 A：新增「翻譯模組」

不需修改任何現有模組，只需：

1. 建立 `translator.py`，接收 `translate_input_queue`，輸出到 `translate_output_queue`
2. 在 `main.py` 建立兩個新 Queue
3. 在路由邏輯中加入：SLM output 中 type="translate" → translate_input_queue
4. translate_output_queue → send_queue 或 ui_event_queue

### 範例 B：新增「第二個 TTS 引擎」

1. 建立新的 TTS 模組，接收 `tts2_input_queue` + `tts2_cmd_queue`
2. 在路由邏輯中根據條件分流到 tts_input_queue 或 tts2_input_queue

### 範例 C：新增「語音喚醒」

1. 建立 `wake_word.py`，持續監聽麥克風，偵測到喚醒詞時輸出事件
2. wake_event_queue → Main Loop → recorder_cmd_queue.put("START")

---

## 11. 技術依賴

| 套件 | 用途 | 必要性 |
|---|---|---|
| `pynput` | 全域鍵盤監聽 | 必要 |
| `pyaudio` | 麥克風錄音 | 必要 |
| `numpy` | 音量計算 (RMS) | 必要 |
| `faster-whisper` | 語音轉文字 (STT) | 必要 |
| `rich` | TUI 渲染 | 必要 |
| `pyttsx3` | TTS 音訊播放 | 必要 |

---

## 12. 開發階段規劃

### Phase 1 - 基礎骨架
- [ ] config.py
- [ ] keyboard_listener.py（移除 F7/QuickCapture）
- [ ] terminal_input.py
- [ ] tui_renderer.py
- [ ] main.py（主迴圈骨架 + Queue 建立）

### Phase 2 - 語音核心
- [ ] record.py（改用 cmd_queue 控制）
- [ ] voice_to_text.py
- [ ] 路由：key_signal → recorder_cmd → audio → stt → stt_output

### Phase 3 - SLM 整合
- [ ] utils/llm_client.py
- [ ] utils/prompt_loader.py
- [ ] slm_processor.py（改用 cmd_queue + output_queue）
- [ ] prompts/*.txt

### Phase 4 - 網路與 LLM
- [ ] http_client.py
- [ ] session_manager.py
- [ ] 路由：slm_output → send_queue → recv_queue → 分發

### Phase 5 - TTS
- [ ] text_to_voice.py（改用 input_queue + cmd_queue）
- [ ] 路由：TTS 分發

### Phase 6 - 完善
- [ ] 授權請求系統
- [ ] 自動備份
- [ ] 日誌系統
- [ ] 錯誤處理與資源清理
