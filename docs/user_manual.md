# Voice Client 使用者說明手冊

更新日期：2026-06-10

Voice Client（V-TUI Assistant）是一個語音優先的終端 AI 客戶端：
按下熱鍵說話 → 本地 Whisper 轉成文字 → 累積在工作區 → 你決定何時送給 LLM →
回覆自動摘要並朗讀。另提供手機瀏覽器模式。

---

## 1. 安裝

### 1.1 系統需求

- Python 3.10+
- FFmpeg（Whisper 與手機模式音訊轉檔）
- （建議）Ollama：本地跑 LLM 與摘要用小模型

### 1.2 Linux（Debian/Ubuntu）

```bash
sudo apt update
sudo apt install -y python3-dev portaudio19-dev ffmpeg espeak-ng libssl-dev
pip install -r requirements.txt
```

- `portaudio19-dev`：`pyaudio` 編譯依賴
- `espeak-ng`：Linux TTS 後端（Windows 用 SAPI5、macOS 用 NSSpeechSynthesizer，自動偵測）

### 1.3 Manjaro / Arch

```bash
sudo pacman -S --needed python portaudio ffmpeg espeak-ng
pip install -r requirements.txt
```

---

## 2. 啟動

| 模式 | 指令 | 說明 |
|---|---|---|
| 桌面 TUI | `python main.py` | 終端介面＋全域熱鍵 |
| 手機 Web | `python mobile_server.py` | 手機瀏覽器連線（見第 7 節） |

啟動後狀態列顯示「待機」即就緒。

---

## 3. 全域熱鍵

| 鍵 | 功能 |
|---|---|
| **F8** | 錄音開關：按一下開始錄音，再按一下停止並辨識，文字進入 buffer 工作區 |
| **F7** | 語音指令模式：錄音內容會被解析成指令（如說「發送」「清除」「列表」） |
| **F9** | 快速發送：立即把 buffer 內容送給 LLM |
| **F10** | 強制停止語音：中斷正在朗讀的 TTS |
| **F6** | 重播：朗讀最後一次 LLM 回覆的原文 |

鍵位可在 `config.ini` 的 `[CONTROL]` 區自訂。

> **注意（Linux）**：全域熱鍵僅支援 X11。Wayland 或 SSH/headless 環境下熱鍵
> 自動停用（啟動時會提示），請改用斜線指令（`/send`、`/stop`…）；
> 打字對話流程不受影響。

---

## 4. 工作區（Workspace）

系統有三個工作區，所有內容操作都作用在「**當前工作區**」上：

| 工作區 | 內容 | 特性 |
|---|---|---|
| `buffer` | 待發送的訊息暫存 | 預設當前工作區；只有它能 `/send` |
| `stt` | 語音辨識原文紀錄 | 可編輯、匯出 |
| `chat` | 對話歷史 | 唯讀為主（清空、檢視） |

- `/ws`：列出所有工作區與筆數（並標示當前）
- `/ws buffer`／`/ws stt`／`/ws chat`：切換當前工作區

> 重構完成後（資料隧道架構），新辨識出的語音文字只會進入「當前」工作區。

---

## 5. 斜線指令

### 5.1 內容操作（作用於當前工作區）

| 指令 | 功能 |
|---|---|
| `/show` | 檢視當前工作區內容（含編號） |
| `/clear` | 清空當前工作區；`/clear ui` 清畫面、`/clear buffer|stt|chat` 指定清空 |
| `/del <編號>` | 刪除指定一筆 |
| `/move <來源> <目標>` | 移動一筆到指定位置 |
| `/to_top [編號]` | 將該筆（預設最後一筆）移到最前 |
| `/concat` | 把多筆壓縮連接成一筆 |
| `/copy` | 複製當前工作區內容到系統剪貼簿 |
| `/paste` | 從剪貼簿貼上（每非空行一筆；chat 不支援） |
| `/export [檔名]` | 匯出當前工作區為 JSON |
| `/import [檔名]` | 從 JSON 匯入 |
| `/send` | 把 buffer 內容發送給 LLM（僅 buffer 有效） |

### 5.2 對話（Session）管理

| 指令 | 功能 |
|---|---|
| `/new [名稱]` | 新建對話 |
| `/switch [名稱]` | 切換對話（預設 default） |
| `/list` | 列出所有對話 |
| `/rename <舊> <新>` | 重新命名 |
| `/delete <名稱>` | 刪除對話 |
| `/history` | 顯示當前對話歷史 |
| `/save [檔名]` | 儲存對話到檔案 |
| `/load <檔名>` | 從檔案載入對話 |

### 5.3 其他

| 指令 | 功能 |
|---|---|
| `/stop` | 停止 TTS 朗讀 |
| `/help` | 指令一覽 |
| `/exit` | 離開程式 |

不加斜線直接輸入文字＋Enter＝把這段文字加入 buffer（等同打字輸入）。

---

## 6. 語音指令模式（F7）

按 F7 錄音、再按 F7 結束後，辨識文字會被解析成指令而不是進入 buffer。
支援的關鍵字（中英皆可）：

- 「發送／傳送／send」→ `/send`
- 「清除／clear」→ `/clear`（含「清除暫存」「清除畫面」變體）
- 「顯示／show」→ `/show`
- 「停止／stop」→ `/stop`
- 「新建／開啟對話／new」「切換／switch」「列表／list」「刪除／delete」
- 「保存／儲存／save」「歷史／紀錄／history」
- 「工作區／workspace」→ `/ws`
- 「複製／copy」「貼上／paste」「壓縮／連接／concat」「置頂／to top」
- 「匯出／export」「匯入／import」「幫助／說明／help」

---

## 7. 手機模式

1. 啟動：`python mobile_server.py`
2. 終端會顯示連線網址（例 `https://192.168.x.x:8080`），手機與電腦須在同一區網
3. 自簽憑證會出現安全警告：點「進階」→「繼續前往」
4. 手機上即可錄音（伺服器端 Whisper 辨識）、看回覆、用瀏覽器原生語音朗讀

`config.ini` 的 `[MOBILE]` 可設定 host／port／ssl。
**SSL 建議保持開啟**——現代手機瀏覽器要求 HTTPS 才允許使用麥克風。

---

## 8. 設定檔（config.ini）速查

| 區段 | 重點設定 |
|---|---|
| `[AUDIO]` | `silence_seconds`（靜音自動切片）、`silence_threshold`、`max_duration` |
| `[CONTROL]` | 五個熱鍵鍵位 |
| `[STT]` | `model_size`（tiny/base/small…）、`device`（cpu/cuda）、`language`（auto＝自動偵測） |
| `[SLM]` | 摘要小模型；`summary_threshold`：回覆超過幾個字才摘要；`enabled=false` 停用摘要 |
| `[LLM]` | 對話主模型：`base_url` 支援 Ollama 或任何 OpenAI 相容端點、`api_key` |
| `[SERVER]` | `enabled=true` 時改為轉發模式：輸入打包 POST 給 `url` 指定的伺服器 |
| `[TTS]` | `engine`（pyttsx3／kokoro）、語速、音量 |
| `[SESSION]` | 自動存檔開關與間隔 |
| `[MOBILE]` | 手機伺服器 host／port／SSL |

---

## 9. 疑難排解

| 症狀 | 處理 |
|---|---|
| 啟動提示「全域熱鍵已停用」 | Wayland/SSH 環境限制，改用斜線指令；或登入 X11 工作階段 |
| 錄音沒反應／報錯 | 確認麥克風權限與 `pyaudio` 安裝（需 portaudio）；看 `output/system.log` |
| 辨識很慢 | `[STT]` 改小模型（`model_size = tiny`）或用 `device = cuda` |
| 沒有聲音 | Linux 需安裝 `espeak-ng`；或 `/stop` 後重試；檢查 `[TTS]` engine |
| 手機連不上 | 同一區網？防火牆開 8080？網址用 `https://` |
| 手機無法錄音 | 必須 HTTPS（`ssl = true`），且要先接受自簽憑證警告 |
| LLM 沒回應 | 檢查 `[LLM] base_url`／`api_key`；本地 Ollama 確認 `ollama serve` 在跑 |

日誌檔：`output/system.log`（等級由 `[LOGGING] level` 控制）。
