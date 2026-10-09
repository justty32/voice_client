# Voice Client (V-TUI Assistant)

一個語音優先、由使用者完全掌控緩衝區的終端機／手機 AI 客戶端：按鍵說話，本地 Whisper
把語音轉成文字累積在工作區，你決定什麼時候送給 LLM，回覆可經本地小模型摘要後朗讀。

> **第一次使用？** 從 [入門手冊](docs/tutorial/README.md) 開始，再依需要查
> [使用手冊](docs/user_manual.md)。

## 🌟 功能

- **本地語音辨識**：`faster-whisper`，離線、可用 GPU；錄音中每次停頓就即時切段辨識。
- **使用者掌控的工作區**：辨識與打字的文字只進「當前工作區」（`buffer`／`stt`），
  可編排、匯出入，`/send` 才送出。
- **LLM 對話**：OpenAI-compatible API（預設本機 LM Studio），或轉發到自架伺服器；多對話管理與持久化。
- **摘要與朗讀**：長回覆可先經本地 SLM（Ollama）摘要；TTS 預設 Kokoro（本機神經 TTS，中英混合），
  也可改用 `pyttsx3`。
- **熱鍵與語音指令**：X11 全域熱鍵、KDE Wayland 全域快捷鍵，或用 F7 說出指令。
- **手機 Web 模式**：手機瀏覽器錄音、看回覆、瀏覽器朗讀，與桌面共用同一套核心與指令。

## 🏗️ 系統架構（資料隧道 Data Tunnel）

所有模組掛在具名通道（topic）上當生產者／消費者，資料搬移由單執行緒交換核心（Exchange）
統一執行，一次一筆、單點可觀測。詳見 [架構文檔](docs/architecture.md)。

- **入口**：桌面 `main.py` → `app.py`；手機 `mobile_server.py`。兩者都呼叫
  `app_wiring/assembly.py` 的 `build_core()` 組出同一套核心，手機只把錄音、畫面、朗讀換成 WebSocket 邊緣。
- **協定 `protocol/`**：topic 名稱、payload 建構函式、指令集的單一來源。
- **框架 `core/`**：Message、Outbox／Inbox、Exchange、TunnelModule 與轉接器；不含業務邏輯。
- **業務模組 `modules/`**：WorkspaceManager、SttGate、CommandRouter、ChatFlow、CliTextBridge。

## 🚀 安裝與啟動

需要 Python 3.10+、FFmpeg（手機模式轉檔）、PortAudio（錄音）。Manjaro：

```bash
sudo pacman -S --needed python portaudio ffmpeg espeak-ng
```

Debian／Ubuntu：

```bash
sudo apt update
sudo apt install -y python3-dev portaudio19-dev ffmpeg espeak-ng libssl-dev
```

`espeak-ng` 只在 `[TTS] engine = pyttsx3` 時需要。接著安裝 Python 套件：

```bash
python -m venv .venv
.venv/bin/pip install -r requirements.txt
```

預設 TTS 是 Kokoro，模型檔（約 717 MB）需另外下載到 `models/kokoro/`，見
[Kokoro 安裝](docs/tts_kokoro_investigation.md)。LLM 預設連本機 LM Studio
（`http://localhost:1234/v1`），請先啟動其 Local Server。GPU、CUDA 與模型大小見
[STT 引擎](docs/user_manual/stt.md)；repo 附的 `config.ini` 預設 `large-v3`＋`cuda`，
沒有 NVIDIA GPU 時請改成 CPU 設定。

啟動：

```bash
.venv/bin/python main.py         # 桌面 TUI（也可 python app.py 或 uv run app.py）
.venv/bin/python mobile_server.py  # 手機 Web 模式
```

狀態列顯示「待機」即就緒。

## ⌨️ 基本操作

| 鍵 | 功能 |
|---|---|
| **Alt+F8**（KDE Wayland）／**F8**（X11） | 錄音開關；文字進當前工作區 |
| **F7** | 語音指令模式：說「發送」就等於 `/send` |
| **Alt+F9**（KDE Wayland）／**F9**（X11） | 快速發送（等同 `/send`） |
| **F10** | 停止朗讀 |
| **F6** | 重播最後一次回覆原文 |

不加斜線直接打字按 Enter，會把文字加入當前工作區。常用斜線指令：`/send` 送出 buffer、
`/show` 看當前工作區、`/clear` 清空當前工作區、`/ws [名稱]` 切換工作區、
`/new`／`/switch`／`/list` 管理對話、`/help` 列出全部、`/exit` 離開。
完整指令表與語音指令關鍵字見 [指令](docs/user_manual/commands.md)。

熱鍵支援依環境而定：X11 上 `pynput` 全域熱鍵可用；KDE Plasma Wayland 由 KDE 全域快捷鍵呼叫
`local_control.py`（設定見 [KDE Wayland 快捷鍵](docs/kde_wayland_shortcuts.md)）；
其他 Wayland、SSH／headless 環境改用斜線指令，打字流程不受影響。

## 📱 手機模式

`python mobile_server.py` 啟動後，log 會印出 `https://<本機 IP>:8080`；手機與電腦在同一區域網路下開啟即可。
預設啟用 HTTPS 並自動產生自簽憑證（手機瀏覽器要 HTTPS 才允許麥克風），第一次連線需接受憑證警告。
同時只服務最新的一條連線。細節見 [手機模式](docs/user_manual/mobile.md)。

## ⚙️ 設定（`config.ini`）

主要區段：`[AUDIO]` 錄音與切段、`[CONTROL]` 熱鍵、`[STT]` Whisper、`[SLM]` 摘要小模型、
`[LLM]` 主對話模型、`[SERVER]` 直連／轉發模式、`[TTS]` 語音合成、`[WORKSPACE]` 檔案位置、
`[LOGGING]`、`[MOBILE]`。每個鍵的意義與預設值見
[設定檔速查](docs/user_manual/config.md)。日誌在 `output/system.log`。

## 🗂️ 專案結構

| 路徑 | 內容 |
|---|---|
| `main.py`、`app.py` | 桌面入口與接線 |
| `app_wiring/` | `wire()`、`build_core()`／`Lifecycle`、共用設定解讀 |
| `protocol/`、`core/`、`modules/` | 協定、隧道框架、業務模組 |
| `speech/`、`ui/`、`llm/`、`domain/` | 錄音／STT／TTS、終端與熱鍵、LLM I/O、工作區與對話 |
| `mobile_server.py`、`mobile/`、`static/` | 手機後端、WS 邊緣、前端 |
| `tests/`、`docs/` | 測試、文件 |

完整地圖見 [INDEX](INDEX.md) 與 [CODE_MAP](workflows/common/code-map/CODE_MAP.md)。

## 📚 文件導航

- 新手第一站：[入門手冊](docs/tutorial/README.md)
- 使用：[使用手冊](docs/user_manual.md)（安裝、STT、操作、指令、設定、疑難排解、手機）
- 開發：[架構文檔](docs/architecture.md)、[INDEX](INDEX.md)、[開發環境](workflows/dev-env.md)
- 調查：[KDE Wayland 快捷鍵](docs/kde_wayland_shortcuts.md)、
  [TTS／Kokoro](docs/tts_kokoro_investigation.md)、[SenseVoice](docs/sensevoice_investigation.md)

## 🛠️ 技術棧

STT `faster-whisper`；TTS `kokoro-onnx`／`pyttsx3`（桌面）、Web Speech API（手機）；
後端 `FastAPI`＋`Uvicorn`；手機音訊轉檔 `pydub`＋FFmpeg；LLM／SLM 為 LM Studio、Ollama 或任何
OpenAI-compatible API；UI 為 `rich`（桌面）與原生 JS／CSS（手機）；輸入為 `pynput`（X11）與
KDE Global Shortcuts＋Unix socket（Wayland）。
