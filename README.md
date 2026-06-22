# Voice Client (V-TUI Assistant)

一個整合語音與文字、具備本地小模型輔助、且由使用者完全掌控緩衝區的終端機 AI 客戶端。

## 🌟 核心願景

V-TUI Assistant 旨在提供一個高效、直觀的語音優先交互環境。通過整合 STT (語音轉文字)、TTS (文字轉語音) 以及本地 SLM (小語言模型) 的摘要能力，讓用戶能夠通過最自然的語音方式與強大的遠端 LLM 進行深度交流。

## 🏗️ 系統架構（資料隧道 Data Tunnel）

系統採用「生產者／消費者＋具名通道」的資料隧道架構：所有模組掛在 topic 上，
資料搬移由單執行緒交換核心（Exchange）統一執行，一次一筆、單點可觀測。
詳見 [`docs/architecture.md`](docs/architecture.md)。

- **入口 (`main.py` → `app.py`)**: `app.py` 是純接線層——建佇列、掛轉接器、啟動模組，不含業務邏輯。
- **框架 (`core/`)**: Message／Outbox／Inbox／Exchange／TunnelModule／轉接器。
- **Audio Pipeline**:
    - **Recorder (`record.py`)**: 具備智能切片邏輯的錄音器，支援 VAD (靜音檢測)。
    - **VoiceToText (`voice_to_text.py`)**: 基於 `faster-whisper` 的本地 STT 引擎。
    - **AudioPriorityPlayer (`text_to_voice.py`)**: 具備優先級的 TTS 播放器，支援立即中斷與排隊。
- **業務模組 (`modules/`)**:
    - **WorkspaceManager**: 多工作區與「當前工作區」指標；辨識文字唯一去向。
    - **SttGate**: 語音指令模式分流（normal → 工作區、command → 指令）。
    - **CommandRouter**: 熱鍵／斜線指令／語音指令的唯一處理者。
    - **ChatFlow**: 對話歷史、摘要決策（SLM 如 gemma3:1b）、回覆重播。
    - **SummaryGenerator (`summary_generator.py`)**: 調用本地 SLM 生成長回答摘要。
    - **SessionManager (`session_manager.py`)**: 管理對話歷史與多會話切換。
- **Interface**:
    - **TuiRenderer (`tui_renderer.py`)**: 基於終端的交互界面。
    - **KeyboardListener (`keyboard_listener.py`)**: X11 等環境的 `pynput` 全域快捷鍵監聽。
    - **LocalControl (`local_control.py`)**: Wayland/KDE 快捷鍵使用的本機 Unix socket 控制入口。

## ⌨️ 控制指南

### 全局快捷鍵
- **F7**: **語音指令模式**。錄音結束後將識別內容解析為斜線指令（如「清空」、「發送」）。
- **Alt+F8**（KDE Wayland）／**F8**（X11）: **錄音開關**。按一下開始錄音，再按一下停止並辨識。
- **Alt+F9**（KDE Wayland）／**F9**（X11）: **快速發送**。立即將目前 buffer 送給 LLM。
- **F10**: **強制停止語音**。立即中斷正在播放的 TTS。

### 斜線指令 (Slash Commands)
在終端輸入框輸入或通過語音指令觸發：
- `/new [title]`: 新建對話。
- `/switch [title]`: 切換到指定對話。
- `/list`: 列出所有對話。
- `/delete [title]`: 刪除對話。
- `/save [file]`: 保存對話到文件。
- `/clear`: 清除 UI 內容。
- `/clear buffer`: 清除緩衝區內容。
- `/show`: 查看緩衝區當前積攢的內容。
- `/stop`: 停止當前語音播放。
- `/help`: 顯示幫助信息。

## 📱 手機伺服器模式 (Mobile Server Mode)

除了桌面的 TUI 介面，V-TUI Assistant 現在支援**手機 Web 模式**。您可以透過手機瀏覽器連線到電腦運行的伺服器，直接在手機上進行語音對話。

### 核心功能
- **遠端語音錄製**：使用手機麥克風錄音，伺服器進行 Whisper 識別。
- **Web 端語音合成**：使用瀏覽器原生的 `SpeechSynthesis` API 播放 AI 回覆。
- **WebSocket 即時串流**：文字與狀態變更即時同步到手機介面。
- **SSL 自動生成**：內建自簽章憑證生成邏輯，確保行動裝置瀏覽器能夠調用麥克風（現代瀏覽器要求 HTTPS 才能使用麥克風）。

### 啟動方式
1. **執行伺服器**：
   ```bash
   python mobile_server.py
   ```
2. **手機連線**：
   伺服器啟動時會顯示本機 IP（例如 `https://192.168.1.100:8080`），請確保手機與電腦在同一區域網路下。
   *注意：由於使用自簽章憑證，手機瀏覽器第一次進入時會顯示安全警告，請點擊「進階」並「繼續前往」。*

### 配置說明 (`config.ini`)
- **[MOBILE]**:
    - `host`: 伺服器綁定位址 (預設 `0.0.0.0`)。
    - `port`: 伺服器埠號 (預設 `8080`)。
    - `ssl`: 是否啟用 HTTPS (預設 `true`)。**強烈建議開啟**，否則手機瀏覽器通常會因安全性限制而禁用麥克風。

## ⚙️ 配置說明 (`config.ini`)

項目核心行為可通過 `config.ini` 進行高度自定義：

- **[AUDIO]**: 採樣率、靜音檢測閾值、最大錄音時長等。
- **[STT]**: Whisper 模型大小、運行設備 (cpu/cuda) 等。
- **[SLM]**: 本地小模型配置，包括 `summary_threshold` (觸發摘要的字數門檻)。
- **[LLM]**: 核心對話模型配置。
    - `base_url`: OpenAI-compatible API 端點。預設連到本機 LM Studio
      `http://localhost:1234/v1`。
    - `api_key`: API 密鑰。使用外部雲端模型時必填。
- **[SERVER]**: 網路通訊模式切換（重要）。
    - `enabled = false` (**直連模式**)：客戶端直接呼叫 `[LLM]` 設定的模型 API。適合 LM Studio、Ollama 或 Gemini。
    - `enabled = true` (**轉發模式**)：將使用者輸入打包 POST 給 `url` 設定的伺服器。適合需要隱藏 API Key、集中管理歷史記錄或進行複雜邏輯過濾的場景。
- **[MOBILE]**: 手機網頁伺服器設定（Host, Port, SSL 等）。
- **[TTS]**: 語音合成引擎設置、語速與音量。

## 🚀 快速開始

1. **環境準備**:
   - 安裝 Python 3.10+。
   - 確保已安裝 **FFmpeg** (Whisper 與手機音訊轉換依賴)。
   - 啟動 LM Studio Local Server，或準備其他 OpenAI-compatible API。

2. **安裝依賴**:
   ```bash
   pip install -r requirements.txt
   ```

3. **運行程序**:
   - **桌面 TUI 模式**: `python main.py`、`python app.py` 或 `uv run app.py`
   - **手機 Web 模式**: `python mobile_server.py`

### Linux 安裝

在 Debian/Ubuntu 系統上，除了 Python 套件還需要下列系統套件：

```bash
sudo apt update
sudo apt install -y python3-dev portaudio19-dev ffmpeg espeak-ng libssl-dev
```

- `portaudio19-dev`：`pyaudio` 編譯依賴。
- `ffmpeg`：手機模式音訊解碼需要；若只跑 TUI 模式且不用 `mobile_server.py` 可略。
- `espeak-ng`：使用 `pyttsx3` 後端時需要；預設 Kokoro 不依賴系統 TTS。

**熱鍵支援：**

- **X11 桌面**：F6–F10 全域熱鍵正常運作。
- **KDE Plasma + Wayland**：`pynput` 仍不可用，但可由 KDE 捕捉快捷鍵，再呼叫
  `local_control.py`。目前本機已註冊 **Alt+F8** 錄音與 **Alt+F9** 發送；詳見
  [`docs/kde_wayland_shortcuts.md`](docs/kde_wayland_shortcuts.md)。
- **其他 Wayland、SSH / headless**：沒有桌面快捷鍵提供者時，改用斜線指令。
  TUI 的文字流程不受影響。

## 🛠️ 技術棧
- **STT**: `faster-whisper`
- **TTS**: `Kokoro ONNX` / `pyttsx3` (桌面離線) / `Web Speech API` (手機)
- **Web Framework**: `FastAPI` & `Uvicorn`
- **Audio Processing**: `pydub` (手機錄音轉檔)
- **SLM/LLM**: LM Studio / Ollama / OpenAI-compatible API
- **UI**: `rich` (桌面) / `Vanilla JS & CSS` (手機)
- **Input**: `pynput`（X11 全域熱鍵）／KDE Global Shortcuts + Unix socket（Wayland）
