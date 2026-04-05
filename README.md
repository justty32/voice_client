# Voice Client (V-TUI Assistant)

一個整合語音與文字、具備本地小模型輔助、且由使用者完全掌控緩衝區的終端機 AI 客戶端。

## 🌟 核心願景

V-TUI Assistant 旨在提供一個高效、直觀的語音優先交互環境。通過整合 STT (語音轉文字)、TTS (文字轉語音) 以及本地 SLM (小語言模型) 的摘要能力，讓用戶能夠通過最自然的語音方式與強大的遠端 LLM 進行深度交流。

## 🏗️ 系統架構

系統採用非同步事件驅動架構，確保各模組並發運行而不互相阻塞：

- **Main Router (`main.py`)**: 核心調度器，負責各模組間的消息轉發。
- **Audio Pipeline**:
    - **Recorder (`record.py`)**: 具備智能切片邏輯的錄音器，支援 VAD (靜音檢測)。
    - **VoiceToText (`voice_to_text.py`)**: 基於 `faster-whisper` 的本地 STT 引擎。
    - **AudioPriorityPlayer (`text_to_voice.py`)**: 具備優先級的 TTS 播放器，支援立即中斷與排隊。
- **Logic & Buffer**:
    - **TextAccumulator (`text_accumulator.py`)**: 消息緩衝區，允許在發送前累積多段輸入。
    - **SummaryGenerator (`summary_generator.py`)**: 調用本地 SLM (如 gemma3:1b) 生成長回答摘要。
    - **SessionManager (`session_manager.py`)**: 管理對話歷史與多會話切換。
- **Interface**:
    - **TuiRenderer (`tui_renderer.py`)**: 基於終端的交互界面。
    - **KeyboardListener (`keyboard_listener.py`)**: 全域快捷鍵監聽。

## ⌨️ 控制指南

### 全局快捷鍵
- **F7**: **語音指令模式**。錄音結束後將識別內容解析為斜線指令（如「清空」、「發送」）。
- **F8**: **錄音開關**。點擊開始錄音，再次點擊停止並識別（內容進入緩衝區）。
- **F9**: **快速發送**。立即將當前緩衝區內容發送給遠端 LLM。
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

## ⚙️ 配置說明 (`config.ini`)

項目核心行為可通過 `config.ini` 進行高度自定義：

- **[AUDIO]**: 採樣率、靜音檢測閾值、最大錄音時長等。
- **[STT]**: Whisper 模型大小、運行設備 (cpu/cuda) 等。
- **[SLM]**: 本地小模型配置，包括 `summary_threshold` (觸發摘要的字數門檻)。
- **[LLM]**: 核心對話模型配置。
    - `base_url`: API 端點。支援本地 Ollama (如 `http://localhost:11434`) 或 Google Gemini OpenAI 兼容端點。
    - `api_key`: API 密鑰。使用外部雲端模型時必填。
- **[SERVER]**: 網路通訊模式切換（重要）。
    - `enabled = false` (**直連模式**)：客戶端直接呼叫 `[LLM]` 設定的模型 API。適合個人直接連接 Gemini 或本地 Ollama。
    - `enabled = true` (**轉發模式**)：將使用者輸入打包 POST 給 `url` 設定的伺服器。適合需要隱藏 API Key、集中管理歷史記錄或進行複雜邏輯過濾的場景。
- **[TTS]**: 語音合成引擎設置、語速與音量。

## 🚀 快速開始

1. **環境準備**:
   - 安裝 Python 3.10+。
   - 確保已安裝 FFmpeg (Whisper 依賴)。
   - (推薦) 安裝 Ollama 以運行本地 SLM 進行摘要生成。

2. **安裝依賴**:
   ```bash
   pip install -r requirements.txt
   ```

3. **運行程序**:
   ```bash
   python main.py
   ```

## 🛠️ 技術棧
- **STT**: `faster-whisper`
- **TTS**: `pyttsx3` (離線) / `Kokoro` (HTTP)
- **SLM/LLM**: `Ollama API` / `OpenAI Compatible API`
- **UI**: `rich`
- **Input**: `pynput` (Global Hotkeys)
