# Mobile Web 版本規劃

## 目標

將桌面 TUI Voice Client 擴展為可在手機瀏覽器使用的 Web 版本。  
手機與執行後端的電腦在同一區域網路，透過瀏覽器即可操作，不需安裝 App。

---

## 1. 現有架構分析

### 1.1 元件清單與職責

| 元件 | 檔案 | 職責 | Queue 通訊 |
|------|------|------|-----------|
| **KeyboardListener** | `keyboard_listener.py` | pynput 全域熱鍵 (F6~F10) → 信號 | `→ key_signal_queue` |
| **TerminalInput** | `terminal_input.py` | stdin 讀取，區分文字/斜線指令 | `→ cli_text_queue, cli_cmd_queue` |
| **TuiRenderer** | `tui_renderer.py` | Rich 終端渲染 (Panel, Text) | `← ui_event_queue` |
| **Recorder** | `record.py` | PyAudio 麥克風錄音，VAD 靜音切片 | `← recorder_cmd_queue → audio_queue, recorder_event_queue` |
| **VoiceToText** | `voice_to_text.py` | faster-whisper STT | `← audio_queue → stt_output_queue` |
| **TextAccumulator** | `text_accumulator.py` | 文字暫存、合併、匯出入 | `← acc_input_queue, acc_cmd_queue → acc_output_queue` |
| **SummaryGenerator** | `summary_generator.py` | SLM 摘要 (gemma3:1b via Ollama) | `← summary_queue → summary_output_queue` |
| **HttpClient** | `http_client.py` | 本地 LLM / 遠端 Server 雙模式 | `← send_queue → recv_queue` |
| **AudioPriorityPlayer** | `text_to_voice.py` | pyttsx3 TTS，優先級 heapq | `← tts_input_queue, tts_cmd_queue` |
| **SessionManager** | `session_manager.py` | 對話持久化 (JSON 檔案) | 同步呼叫，無 Queue |
| **Main Loop** | `main.py` | 純路由器，輪詢所有 Queue 並轉發 | 所有 Queue |

### 1.2 Queue 架構圖（桌面版）

```
KeyboardListener ──→ key_signal_queue ──→┐
TerminalInput ────→ cli_text_queue ─────→│
                  ──→ cli_cmd_queue ─────→│
                                          │
                    Main Loop (Router) ←──┘
                          │
        ┌─────────────────┼─────────────────┐
        ↓                 ↓                 ↓
  recorder_cmd_queue  acc_input_queue  tts_input_queue
        │             acc_cmd_queue    tts_cmd_queue
        ↓                 ↓                 ↓
    Recorder       TextAccumulator   AudioPriorityPlayer
        │                 │
        ↓                 ↓
   audio_queue      acc_output_queue ──→ send_queue ──→ HttpClient
        ↓                                                   │
   VoiceToText                                         recv_queue
        │                                                   │
   stt_output_queue ──→ Main Loop ←── recv_queue ←──────────┘
                            │
                    ui_event_queue ──→ TuiRenderer
                    summary_queue ──→ SummaryGenerator → summary_output_queue
```

### 1.3 手機相容性分析

| 元件 | 手機可用？ | 原因 | 替代方案 |
|------|-----------|------|---------|
| KeyboardListener | ❌ | pynput 需 OS 級鍵盤 hook | 前端觸控按鈕 → WebSocket |
| TerminalInput | ❌ | 無 stdin | 前端文字輸入框 → WebSocket |
| TuiRenderer | ❌ | 需終端機 (Rich) | 前端 HTML/CSS 渲染 |
| Recorder | ❌ | PyAudio 無法存取手機麥克風 | 前端 MediaRecorder → WebSocket 傳音訊 |
| AudioPriorityPlayer | ❌ | pyttsx3 無法在手機播放 | 前端 Web Speech API SpeechSynthesis |
| VoiceToText | ✅ | 後端執行 Whisper，不受前端影響 | 保留 |
| TextAccumulator | ✅ | 純 Python 邏輯 | 保留 |
| SummaryGenerator | ✅ | 純 Python 邏輯 | 保留 |
| HttpClient | ✅ | 純 Python 邏輯 | 保留 |
| SessionManager | ✅ | 純 Python 邏輯 | 保留 |

---

## 2. 技術選型

### Web App 方案（FastAPI + WebSocket + 瀏覽器前端）

| 層級 | 技術 | 說明 |
|------|------|------|
| 後端框架 | FastAPI + uvicorn | 專案已有依賴，WebSocket 原生支援 |
| 即時通訊 | WebSocket `/ws` | 全雙工：推送狀態/訊息，接收音訊/文字/指令 |
| 前端錄音 | MediaRecorder API | 瀏覽器原生，免費，錄成 WebM/Opus → 傳至後端 |
| 前端 TTS | Web Speech API SpeechSynthesis | 瀏覽器原生，免費，使用 OS 內建引擎 |
| 前端 UI | 純 HTML/CSS/JS | 無框架依賴，手機觸控友善 |
| 音訊轉換 | pydub (ffmpeg) | WebM/Opus → WAV，供 faster-whisper 使用 |
| 靜態檔案 | FastAPI StaticFiles | 後端直接 serve 前端頁面 |

### 費用

| 技術 | 費用 |
|------|------|
| MediaRecorder API | 免費（瀏覽器原生） |
| Web Speech API SpeechSynthesis (TTS) | 免費（手機本地引擎） |
| faster-whisper (STT) | 免費（自己電腦跑） |
| Ollama LLM / SLM | 免費（自己電腦跑） |

---

## 3. 新架構設計

### 3.1 整體架構圖（Mobile Web 版）

```
┌──────────────────────────────────────┐
│          手機瀏覽器 (HTML/JS)          │
│                                      │
│  [觸控按鈕] → 開始/停止錄音            │
│  [MediaRecorder] → 錄製音訊 blob       │
│  [文字輸入框] → 打字輸入               │
│  [SpeechSynthesis] → 播放 TTS         │
│  [訊息列表] → 顯示對話                 │
│                                      │
│        ↕ WebSocket (JSON + binary)    │
└──────────────────────────────────────┘
                    │
                    │ Wi-Fi / LAN
                    │
┌──────────────────────────────────────┐
│     FastAPI Server (mobile_server.py) │
│                                      │
│  WebSocket /ws                       │
│    ├─ 接收 binary (音訊) → audio_queue │
│    ├─ 接收 JSON text → acc_input_queue │
│    ├─ 接收 JSON cmd  → 路由至對應操作   │
│    └─ 推送 JSON 至前端（訊息/狀態/TTS） │
│                                      │
│  保留元件（完全不動）：                  │
│    VoiceToText, TextAccumulator,      │
│    SummaryGenerator, HttpClient,      │
│    SessionManager                     │
└──────────────────────────────────────┘
```

### 3.2 WebSocket 訊息協議

#### 前端 → 後端

```jsonc
// 1. 文字輸入
{"type": "text", "content": "你好"}

// 2. 斜線指令
{"type": "cmd", "cmd": "/new", "args": ["my_session"]}

// 3. 控制信號（對應桌面版 KeyboardListener 的功能）
{"type": "signal", "signal": "QUICK_SEND"}
{"type": "signal", "signal": "FORCE_STOP_TTS"}

// 4. 音訊資料（binary frame，非 JSON）
//    前端 MediaRecorder 停止錄音後，直接傳送 audio blob
```

#### 後端 → 前端

```jsonc
// 1. 訊息（對應桌面版 UiEvent("message", ...)）
{"type": "message", "role": "assistant", "text": "AI 的回覆..."}
{"type": "message", "role": "voice", "text": "語音辨識結果..."}
{"type": "message", "role": "user", "text": "使用者輸入..."}
{"type": "message", "role": "system", "text": "系統訊息..."}
{"type": "message", "role": "sending", "text": "[傳送內容] ..."}
{"type": "message", "role": "summary", "text": "回覆摘要：..."}

// 2. 狀態更新（對應桌面版 UiEvent("status", ...)）
{"type": "status", "text": "待機"}
{"type": "status", "text": "處理中"}

// 3. TTS 指令（讓前端播放語音）
{"type": "tts", "text": "要播放的文字", "priority": "medium"}

// 4. TTS 控制（停止前端播放）
{"type": "tts_control", "action": "stop"}

// 5. 清除畫面
{"type": "clear"}

// 6. Session 列表回應
{"type": "sessions", "list": ["default (當前)", "session_2"], "current": "default"}
```

### 3.3 與桌面版 Queue 架構的對應

桌面版 Main Loop 路由七大區塊（A~G），Mobile 版在 `mobile_server.py` 中以 WebSocket handler 取代：

| 桌面版區塊 | 桌面版來源 | Mobile 版替代 |
|-----------|-----------|--------------|
| A. Keyboard signals | `key_signal_queue` | WebSocket `{"type":"signal"}` |
| B. Recorder events | `recorder_event_queue` | 不需要（前端自行管理錄音狀態 UI） |
| C. STT output | `stt_output_queue` | 保留，結果透過 ws 推送 |
| D. CLI text | `cli_text_queue` | WebSocket `{"type":"text"}` |
| E. CLI commands | `cli_cmd_queue` | WebSocket `{"type":"cmd"}` |
| F. Accumulator output | `acc_output_queue` | 保留，結果透過 ws 推送 |
| F1. Summary output | `summary_output_queue` | 保留，結果透過 ws 推送 |
| G. HTTP response | `recv_queue` | 保留，結果透過 ws 推送 |

---

## 4. 前端介面設計

### 4.1 手機觸控 UI Layout

```
┌─────────────────────────────────────┐
│ 🎙 Voice Client     [default ▾]     │ ← 固定 header，Session 下拉選單
├─────────────────────────────────────┤
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ [🤖 AI]                         │ │
│ │ 你好，有什麼需要幫忙的？          │ │
│ └─────────────────────────────────┘ │
│                                     │
│ ┌─────────────────────────────────┐ │
│ │ [👤 You]                        │ │
│ │ 請幫我查一下天氣                  │ │
│ └─────────────────────────────────┘ │
│                                     │ ← 可滾動訊息區
│ ┌─────────────────────────────────┐ │
│ │ [💡 摘要]                        │ │
│ │ 回覆摘要：AI 介紹了今天天氣狀況    │ │
│ └─────────────────────────────────┘ │
│                                     │
│ ● 待機                              │ ← 狀態列
├─────────────────────────────────────┤
│ ┌──────────────────────────┐  [▶]  │ ← 文字輸入框 + 送出鍵
│ │ 輸入文字...               │       │
│ └──────────────────────────┘       │
│                                     │
│    [🎙 錄音]    [⏹ 停止TTS]         │ ← 操作按鈕列
│    [📋 指令]    [⋯ 更多]            │
└─────────────────────────────────────┘
```

### 4.2 「更多」選單（滑出面板）

```
┌─────────────────────────────────────┐
│ 指令面板                       [✕]  │
├─────────────────────────────────────┤
│ 暫存區操作                          │
│   [顯示暫存區]  [壓縮]  [置頂]       │
│   [匯出]  [匯入]  [清除暫存]         │
│                                     │
│ 對話管理                            │
│   [新建對話]  [對話列表]  [歷史紀錄]  │
│   [儲存]  [載入]  [重新命名]  [刪除]  │
│                                     │
│ 其他                               │
│   [清除畫面]                        │
└─────────────────────────────────────┘
```

### 4.3 錄音按鈕行為

- **按住錄音**：按下 → 開始錄音（MediaRecorder.start()）；放開 → 停止錄音並傳送
- **狀態指示**：錄音中按鈕變紅並顯示脈動動畫
- 錄音完成後，音訊 blob 直接透過 WebSocket binary frame 傳送至後端

### 4.4 TTS 播放行為

- 後端推送 `{"type": "tts", "text": "...", "priority": "..."}` 時，前端呼叫 `SpeechSynthesis.speak()`
- high priority：立即取消當前播放，清除佇列
- medium/low：依序排隊播放
- 「停止 TTS」按鈕：呼叫 `SpeechSynthesis.cancel()` 並通知後端

---

## 5. 後端實作細節

### 5.1 `mobile_server.py` 結構

```python
# mobile_server.py — Mobile Web 版後端入口

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
import asyncio, queue, io
from config import load_config
from voice_to_text import VoiceToText
from text_accumulator import TextAccumulator
from summary_generator import SummaryGenerator
from http_client import HttpClient
from session_manager import SessionManager

app = FastAPI()
app.mount("/static", StaticFiles(directory="static"), name="static")

# --- 元件初始化（啟動時建立） ---

# --- WebSocket endpoint ---
@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()
    # 1. 啟動 output queue → ws 推送的 asyncio task
    # 2. 接收迴圈：
    #    - binary frame → 音訊 blob → audio_queue
    #    - text frame → JSON 解析 → 路由至對應 queue
    # 3. 斷線時清理
```

### 5.2 關鍵實作：Queue → WebSocket 推送

桌面版用 `ui_event_queue` 驅動 `TuiRenderer`。Mobile 版改為 asyncio task 輪詢 Queue 並 `ws.send_json()`：

```python
async def _output_pusher(ws: WebSocket, queues: dict):
    """輪詢各 output queue，將事件推送至 WebSocket。"""
    while True:
        # 檢查 ui_event_queue → 轉為 ws message
        # 檢查 stt_output_queue → 推送語音辨識結果
        # 檢查 acc_output_queue → 處理 payload 送出
        # 檢查 summary_output_queue → 推送摘要
        # 檢查 recv_queue → 推送 AI 回覆 + TTS 指令
        await asyncio.sleep(0.05)
```

### 5.3 音訊格式轉換

手機 MediaRecorder 預設輸出 `audio/webm;codecs=opus`，faster-whisper 需要 WAV 或可解碼格式。

```python
from pydub import AudioSegment
import io

def webm_to_wav(webm_bytes: bytes) -> io.BytesIO:
    """WebM/Opus → 16kHz mono WAV（供 faster-whisper 使用）。"""
    audio = AudioSegment.from_file(io.BytesIO(webm_bytes), format="webm")
    audio = audio.set_frame_rate(16000).set_channels(1).set_sample_width(2)
    wav_buf = io.BytesIO()
    audio.export(wav_buf, format="wav")
    wav_buf.seek(0)
    return wav_buf
```

> 需要系統安裝 ffmpeg。pydub 只是 ffmpeg 的 Python wrapper。

### 5.4 Session Manager 共享

`SessionManager` 是同步物件，桌面版在 Main Loop 中直接呼叫。Mobile 版同樣在 WebSocket handler 中直接呼叫，不需改動 `session_manager.py`。

若未來需支援多個同時連線的客戶端，需加鎖或改用 async-safe 存取。初版（單一使用者）不需處理。

---

## 6. 檔案結構

### 6.1 新增檔案

```
voice_client/
├── mobile_server.py            ← FastAPI WebSocket server（Mobile 版入口）
├── static/
│   ├── index.html              ← 手機前端頁面（單一 HTML 包含結構）
│   ├── app.js                  ← 前端邏輯（WebSocket、錄音、TTS、UI 操作）
│   └── style.css               ← 手機觸控 RWD 樣式
└── plans/
    └── mobile.md               ← 本文件
```

### 6.2 不動的檔案

以下檔案完全不修改，直接被 `mobile_server.py` import 使用：

```
voice_to_text.py                ← STT（後端 Whisper）
text_accumulator.py             ← 暫存區
summary_generator.py            ← SLM 摘要
http_client.py                  ← LLM 呼叫
session_manager.py              ← 對話管理
config.py                       ← config loader
utils/llm_client.py             ← LLM API 呼叫
utils/prompt_loader.py          ← prompt 載入
prompts/llm_system.txt          ← LLM 提示詞
prompts/slm_summary.txt         ← SLM 提示詞
config.ini                      ← 設定檔（新增 [MOBILE] section）
```

### 6.3 不使用的檔案（Mobile 版不 import）

```
keyboard_listener.py            ← pynput，手機無法使用
terminal_input.py               ← stdin，手機無終端
tui_renderer.py                 ← Rich TUI，手機無終端
record.py                       ← PyAudio，手機無法使用
text_to_voice.py                ← pyttsx3，手機無法使用
main.py                         ← 桌面版入口（保留供桌面使用）
```

---

## 7. 設定檔變更

在 `config.ini` 新增 `[MOBILE]` section：

```ini
[MOBILE]
host = 0.0.0.0
port = 8080
# 允許任何 IP 連線（區域網路內使用）
```

啟動方式：
```bash
python mobile_server.py
# 手機瀏覽器開啟 http://<電腦IP>:8080
```

---

## 8. 依賴套件

### 8.1 新增

```
pydub              # WebM → WAV 音訊格式轉換
```

> `fastapi` 和 `uvicorn` 已在 `requirements.txt` 中。  
> 系統需安裝 ffmpeg（pydub 依賴）。

### 8.2 Mobile 版不需要但桌面版需要的套件

```
pyaudio            # 桌面版錄音
pyttsx3            # 桌面版 TTS
pynput             # 桌面版全域熱鍵
rich               # 桌面版 TUI
```

---

## 9. 實作步驟

### Phase 1：後端 `mobile_server.py`

1. **FastAPI app 骨架**
   - 建立 `mobile_server.py`
   - 讀取 `config.ini`，初始化所有後端元件
   - 掛載 `static/` 靜態檔案目錄
   - 根路由 `/` 重導至 `/static/index.html`

2. **WebSocket endpoint `/ws`**
   - `on_connect`：初始化各 Queue，啟動後端元件（VoiceToText, TextAccumulator, SummaryGenerator, HttpClient）
   - `on_message (text)`：JSON 解析，根據 `type` 路由至：
     - `"text"` → `acc_input_queue.put()`
     - `"cmd"` → 對應 session/acc/tts 操作（移植 `main.py:_route_cli_cmd` 邏輯）
     - `"signal"` → 對應操作（QUICK_SEND, FORCE_STOP_TTS 等）
   - `on_message (binary)`：音訊 blob → `webm_to_wav()` → `audio_queue.put()`
   - `on_disconnect`：停止後端元件，清理資源

3. **Output 推送 task**
   - asyncio task 輪詢 `stt_output_queue`、`acc_output_queue`、`summary_output_queue`、`recv_queue`
   - 將結果轉為 WebSocket JSON 推送至前端
   - TTS 文字不在後端播放，改為 `{"type":"tts"}` 推送至前端

### Phase 2：前端 `static/`

4. **`index.html` — 頁面結構**
   - Header（標題 + Session 下拉選單）
   - 訊息列表區（可滾動，自動捲至底部）
   - 狀態列
   - 輸入區（文字框 + 送出按鈕）
   - 操作按鈕列（錄音、停止 TTS、指令面板）
   - 指令面板（滑出式）

5. **`style.css` — 手機觸控樣式**
   - `<meta name="viewport">` 確保手機正確縮放
   - 按鈕最小觸控區域 44x44px
   - 訊息泡泡樣式（依 role 區分顏色）
   - 錄音中脈動動畫
   - 深色/淺色主題（依系統偏好）
   - 固定 header + 固定底部輸入區，中間訊息區滾動

6. **`app.js` — 前端邏輯**

   **6a. WebSocket 連線管理**
   - 連線、自動重連（指數退避）、心跳
   - 接收 JSON → 依 `type` 分派處理

   **6b. 訊息渲染**
   - `type: "message"` → 建立訊息泡泡 DOM，依 `role` 套用樣式
   - `type: "status"` → 更新狀態列
   - `type: "clear"` → 清空訊息區

   **6c. MediaRecorder 錄音**
   - 請求麥克風權限 `navigator.mediaDevices.getUserMedia({audio: true})`
   - 錄音按鈕 touchstart → `MediaRecorder.start()`
   - 錄音按鈕 touchend → `MediaRecorder.stop()` → `ondataavailable` 拿到 blob → `ws.send(blob)`
   - 錄音中 UI 狀態切換（按鈕變紅、動畫）

   **6d. Web Speech API TTS**
   - 維護播放佇列（模仿 `AudioPriorityPlayer` 的 heapq 邏輯）
   - `type: "tts"` → 建立 `SpeechSynthesisUtterance`，依 priority 排隊或打斷
   - `type: "tts_control", action: "stop"` → `speechSynthesis.cancel()`
   - 「停止 TTS」按鈕 → `speechSynthesis.cancel()` + 通知後端

   **6e. 文字輸入**
   - Enter 鍵或送出按鈕 → `ws.send(JSON.stringify({type: "text", content: ...}))`
   - 送出後清空輸入框、focus 回輸入框

   **6f. 指令面板**
   - 每個按鈕對應一個 `{"type": "cmd", "cmd": "/xxx"}` → ws.send()
   - 需要參數的指令（/new, /switch, /rename...）→ 彈出簡易 prompt() 或 modal

   **6g. Session 下拉選單**
   - 連線時向後端請求 session 列表
   - 選擇後送出 `{"type": "cmd", "cmd": "/switch", "args": ["title"]}`

### Phase 3：整合與收尾

7. **音訊格式轉換驗證**
   - 測試 Android Chrome、iOS Safari 的 MediaRecorder 輸出格式
   - 確認 pydub + ffmpeg 正確轉換
   - 確認 faster-whisper 正確辨識轉換後的音訊

8. **config.ini 新增 `[MOBILE]` section**

9. **requirements.txt 更新**
   - 新增 `pydub`

10. **README 更新**
    - Mobile 版啟動方式
    - 手機連線方式
    - ffmpeg 安裝說明

---

## 10. 待確認 / 風險

| 項目 | 說明 | 影響 | 備案 |
|------|------|------|------|
| **MediaRecorder 輸出格式** | Android Chrome → `audio/webm;codecs=opus`，iOS Safari → 可能是 `audio/mp4;codecs=aac` | 需要判斷格式並分別轉換 | pydub 兩者皆可處理 |
| **SpeechSynthesis 中文支援** | iOS 有良好中文語音，Android 視裝置而異 | 部分 Android 裝置中文 TTS 品質差 | 可列印文字，TTS 作為輔助 |
| **ffmpeg 安裝** | pydub 依賴系統 ffmpeg | 使用者需自行安裝 | 提供安裝說明 |
| **HTTPS** | iOS Safari 13+ 要求 HTTPS 才能使用麥克風 | 區域網路 HTTP 可能被擋 | 使用 mkcert 產生自簽憑證 |
| **單一連線** | 初版不處理多客戶端同時連線 | SessionManager 非 thread-safe | 後續可加鎖 |
| **大音訊傳輸** | 長時間錄音的 blob 可能很大 | WebSocket 傳輸延遲 | 前端每 5 秒自動切片送出 |

---

## 11. 未來擴充方向（不在本次範圍）

- 多客戶端支援（WebSocket 廣播、Session 隔離）
- PWA 離線快取（Service Worker）
- HTTPS + 自簽憑證自動化
- 推播通知（Push API）
- 語音指令模式（前端長按指令按鈕，錄音後送至後端解析）
