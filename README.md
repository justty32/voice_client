# Voice Client

Gemini 說了
這份架構設計文檔（Architecture Design Document, ADD）將作為你開發這個專案的藍圖。它整合了你提到的「絕對掌控權」、「緩衝區協作」以及「語音優先級」等核心概念。

📝 專案名稱：V-TUI Assistant (暫定)
核心願景：一個整合語音與文字、具備本地小模型輔助、且由使用者完全掌控緩衝區的終端機 AI 客戶端。
🏛️ 1. 系統架構概覽 (System Architecture)
系統採用非同步事件驅動架構 (Asynchronous Event-Driven)，確保語音錄製、文字輸入與語音播放能同時並行而不互相阻塞。

模組拆解：
Input Manager (輸入管理器)：處理全域快捷鍵 (F4-F8)、TUI 文字輸入、語音錄製與 STT。

Buffer Room (緩衝空間)：核心數據中控，存放未發送的內容，支援手動編輯與檔案導出入。

Processing Engine (處理引擎)：

Local SLM (2B)：執行總結、糾錯、預覽等可選任務。

Cloud/Remote LLM：執行核心對話邏輯。

Output Manager (輸出管理器)：

TUI Renderer：顯示對話與狀態。

Priority Voice Queue：管理不同等級的語音輸出播放。

🛠️ 2. 核心功能細節設計
A. 暫存緩衝區邏輯 (Buffer Logic)
緩衝區是發送前的最後一道防線。

數據來源：STT(Voice) + TUI(Text) + File Import。

協作模式：

語音錄入後自動附加換行。

TUI 輸入後按下回車（Enter）自動附加。

SLM 介入 (可選)：

/clean (F6)：小模型對 Buffer 進行語法修正。

/summary：小模型對 Buffer 進行發送前摘要。

B. 語音流水線與分段 (Voice Pipeline)
VAD (Voice Activity Detection)：

檢測停頓時間 t (預設 1.5s)。

若 t>threshold 或 錄音時長 >60s，觸發切片送至 faster-whisper。

STT 引擎：本地端推理，結果非同步寫入 Buffer。

C. 語音優先級隊列 (Audio Priority Queue)
系統維護兩個對列：High-Priority (P0, P1) 與 Low-Priority (P2)。

等級	內容範例	播放行為
P0 (Critical)	系統警告、錄音開始/結束音	立即打斷當前播放，播放後恢復。
P1 (Summary)	SLM 生成的摘要（發送前/接收後）	排在 P2 之前，若 P2 正在播放，可選擇壓低 P2 音量 (Ducking)。
P2 (Content)	LLM 完整回覆文本	正常排隊播放。
💾 3. 數據持久化與 Session 管理
存檔結構 (Directory Structure)
Plaintext
/vault
  /sessions
    /session_001
      - chat_history.json   (實際對話紀錄)
      - buffer_state.json   (未發送的暫存內容)
      - actions.log         (SLM 修改、系統操作紀錄)
  - config.yaml             (快捷鍵、API Key、模型參數)
  - global_buffer.tmp       (程式異常結束時的緊急備份)
⌨️ 4. 控制指令系統
快捷鍵映射 (Hotkeys)
F8：內容錄音 (按住或開關式)。

F7：語音指令錄音 (例如說出「發送」、「清空」)。

F4：直接發送當前 Buffer。

F6：觸發 SLM 整理 Buffer。

斜線指令 (Slash Commands)
/new：開新對話。

/switch [ID]：切換 Session。

/export：將 Buffer 轉存為 .txt 進行外部編輯。

/import：從檔案讀回 Buffer。

🧪 5. 技術棧選型 (Tech Stack)
語言：Python 3.10+

異步框架：asyncio

TUI 框架：prompt_toolkit (比 curses 更強大，支援非同步輸入)。

監聽器：pynput (全域按鍵攔截)。

語音處理：

STT：faster-whisper (本地端)。

VAD：silero-vad。

TTS：edge-tts (自然) 或 pyttsx3 (離線)。

播放控制：pygame.mixer (支援多軌道與暫停)。

模型介面：Ollama API (處理本地 2B 模型) + OpenAI/Anthropic SDK (雲端)。

📈 6. 開發路線圖 (Roadmap)
Phase 1 (MVP)：建立 TUI 基礎架構、Buffer 管理器與快捷鍵監聽。

Phase 2 (Audio Core)：實作錄音切片、STT 整合與基礎語音隊列。

Phase 3 (SLM Integration)：對接 Ollama，實作發送前/接收後的摘要與整理功能。

Phase 4 (Advanced Logic)：實作跨 Session 語音播放、檔案匯入匯出與語音優先級。