# Voice Client 使用手冊

更新日期：2026-06-22

這是一個語音優先的終端 AI 客戶端。按熱鍵說話，Whisper 把語音轉成文字累積在工作區，你決定什麼時候送給 LLM，回覆會自動摘要並朗讀。

---

## 1. 安裝（Manjaro）

### 1.1 系統套件

```bash
sudo pacman -S --needed python portaudio ffmpeg espeak-ng
```

- `portaudio`：pyaudio 錄音依賴
- `ffmpeg`：手機模式音訊轉檔（只跑桌面 TUI 可略）
- `espeak-ng`：Linux 上的 TTS 朗讀後端

### 1.2 Python 套件

```bash
pip install -r requirements.txt
```

如果你要用 CUDA 加速 Whisper，先裝 GPU 版 PyTorch 再裝 faster-whisper：

```bash
# 先確認 CUDA 版本
nvidia-smi

# 按你的 CUDA 版本裝 PyTorch（範例：CUDA 12.1）
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# 再裝 faster-whisper
pip install faster-whisper
```

### 1.3 熱鍵支援

- **X11**：F6–F10 全域熱鍵正常。
- **KDE Plasma + Wayland**：`pynput` 無法抓全域鍵，但可以使用 KDE Global
  Shortcuts 呼叫 `local_control.py`。目前本機已設定 Alt+F8／Alt+F9；完整設定與故障排除見
  [KDE Wayland 全域快捷鍵](kde_wayland_shortcuts.md)。
- **其他 Wayland、SSH / headless**：沒有 KDE 快捷鍵時使用斜線指令，TUI 打字流程不受影響。

---

## 2. STT 引擎安裝與調整

STT 引擎是 [faster-whisper](https://github.com/SYSTRAN/faster-whisper)，本地跑、離線、不送雲端。

### 2.1 模型第一次啟動自動下載

設定好 `model_size` 後，第一次執行 `python main.py` 時 Whisper 會自動下載模型到 `~/.cache/huggingface/hub/`。下載完後就是離線使用。

### 2.2 模型大小選擇

在 `config.ini` 的 `[STT]` 區設定：

```ini
[STT]
model_size = base
```

| 模型 | 大小 | 速度 | 準確度 | 適合場景 |
|---|---|---|---|---|
| `tiny` | 75 MB | 最快 | 最低 | 低資源機器、快速測試 |
| `base` | 145 MB | 快 | 尚可 | **預設值，日常用夠了** |
| `small` | 483 MB | 中 | 好 | 想更準但不換 GPU |
| `medium` | 1.5 GB | 慢 | 很好 | CPU 跑會明顯延遲 |
| `large-v2` | 3 GB | 很慢 | 最好 | 需要 GPU |
| `large-v3` | 3 GB | 很慢 | 最好（新版） | 需要 GPU |
| `large-v3-turbo` | 1.6 GB | 快（GPU） | 很好（略低於 v3） | **GPU 推薦，速度／準度最佳平衡** |

一般建議：CPU 跑用 `base`（或 `small` 可接受），有 GPU 用 `large-v3-turbo`（快又準、VRAM 省）；要極致準度才用 `large-v3`。

> 想要中文辨識再上一層樓？有個比 Whisper 對中文更準的替代引擎（SenseVoice）調查
> 記在 [docs/sensevoice_investigation.md](sensevoice_investigation.md)，尚未實作。

### 2.3 CPU vs GPU

```ini
device = cpu       # 預設，不需要 GPU
device = cuda      # 需要 NVIDIA GPU + CUDA 環境
```

GPU 跑時速度可快 5–10 倍。如果 `nvidia-smi` 有輸出、CTranslate2 能看到 GPU，就可以設 `cuda`。

> **CUDA 13 系統注意**：faster-whisper 的後端 CTranslate2 4.x 是針對 CUDA 12 編譯的，
> 需要 `libcublas.so.12`。若系統是 CUDA 13（只提供 `libcublas.so.13`），GPU 轉譯會報
> `Library libcublas.so.12 is not found`。解法是裝 pip 版 cuBLAS（不污染系統 CUDA）：
> ```bash
> pip install nvidia-cublas-cu12      # 或 uv pip install --python .venv/bin/python nvidia-cublas-cu12
> ```
> 裝好後 `voice_to_text.py` 啟動時會自動預載它，無需設 `LD_LIBRARY_PATH`。

### 2.4 compute_type（精度／速度權衡）

```ini
compute_type = int8      # 預設，最快，佔記憶體最少，準確度略降
compute_type = float16   # GPU 推薦，速度快且準確度好（需要 GPU）
compute_type = float32   # 最準，但最慢最耗記憶體
```

- CPU：用 `int8` 或 `float32`（`float16` 在純 CPU 上可能報錯）。
- GPU：`float16` 是最佳選擇，速度與準確度平衡好。

### 2.5 語言設定

```ini
language = auto    # 自動偵測（預設）
language = zh      # 強制中文
language = en      # 強制英文
```

`auto` 會從說話的前幾秒猜語言，大部分時候夠用。如果你只說中文，設 `zh` 速度略快（少一步偵測）；混說中英就留 `auto`。

### 2.6 其他調整

```ini
beam_size = 5      # 搜尋寬度，越大越準但越慢；CPU 上可改 1 換速度
vad_filter = true  # 靜音偵測過濾，減少背景雜音被辨識成文字
```

`beam_size = 1` 是貪婪解碼，速度最快，準確度比 5 差一點，低資源時可試。

### 2.7 initial_prompt（繁體與常用詞引導）

```ini
initial_prompt = 以下是繁體中文的句子。
```

Whisper 對中文預設會輸出**簡體**。`initial_prompt` 會被當成「上文」餵給模型，
用一句繁體中文當提示就能引導它輸出繁體；也可以塞入你常講但容易被辨錯的專有名詞
（例如人名、技術術語），提高這些詞的辨識率。留空則不使用。

### 2.8 常見 STT 問題

| 症狀 | 處理 |
|---|---|
| 辨識很慢 | 換小模型（`tiny`/`base`）或設 `beam_size = 1` |
| CPU 溫度高 | 正常，Whisper 很吃 CPU，設 `tiny` 減少負擔 |
| `float16` 報錯 | CPU 不支援，改 `int8` 或 `float32` |
| CUDA out of memory | 換小模型，或 `compute_type = int8` |
| 辨識文字亂跳雜訊 | 確認 `vad_filter = true`，調高 `silence_threshold` |
| 說中文被辨識成日文 | 設 `language = zh` 強制中文 |
| 中文輸出成簡體 | 設 `initial_prompt = 以下是繁體中文的句子。` |
| 認錯字太多 | 換更大模型（GPU 用 `large-v3-turbo` 或 `large-v3`），並固定 `language` |
| `libcublas.so.12 is not found` | CUDA 13 系統缺 CUDA 12 cuBLAS，`pip install nvidia-cublas-cu12`（見 2.3） |
| 第一次啟動很慢 | 正在下載模型，等它跑完，之後就快了 |

---

## 3. 啟動

```bash
# 桌面 TUI 模式（一般使用）
python main.py

# 使用現有 .venv 啟動
uv run app.py

# 手機 Web 模式
python mobile_server.py
```

啟動後狀態列顯示「待機」就代表就緒了。在 KDE Wayland 上看到
「Wayland 本機控制已啟用」代表程式端的快捷鍵控制 socket 已建立。

---

## 4. 熱鍵

| 鍵 | 功能 |
|---|---|
| **Alt+F8**（KDE）／**F8**（X11） | 錄音開關：按一下開始、再按一下停止並辨識，文字進**當前工作區** |
| **F7** | 語音指令模式：說的話被解析成指令（說「發送」就等於 `/send`） |
| **Alt+F9**（KDE）／**F9**（X11） | 快速發送：把 buffer 內容馬上送給 LLM |
| **F10** | 強制停止 TTS：中斷正在朗讀的回覆 |
| **F6** | 重播：用 TTS 朗讀最後一次 LLM 回覆的原文 |

鍵位可以在 `config.ini` 的 `[CONTROL]` 區自訂，例如：

```ini
[CONTROL]
key_record_toggle = f8
key_command_toggle = f7
key_quick_send = f9
key_force_stop_tts = f10
key_play_last_original = f6
```

> **注意**：`key_command_toggle` 預設值是 f7，但 `config.ini` 預設沒有這行。
> 如果你要改 F7 的鍵位，手動加這行再改。

> **KDE Wayland 注意**：`config.ini` 只影響 `pynput` 路徑，不會自動修改 KDE
> 的快捷鍵。目前 KDE 已註冊 Alt+F8／Alt+F9；要增加 F7/F10，需建立對應的 KDE
> 快捷鍵動作，詳見 [KDE Wayland 全域快捷鍵](kde_wayland_shortcuts.md)。

---

## 5. 工作區

系統有三個工作區，操作都作用在「**當前工作區**」：

| 工作區 | 用途 | 特性 |
|---|---|---|
| `buffer` | 待發送的訊息暫存 | 預設當前；只有它能 `/send` |
| `stt` | 第二個文字暫存 | 可自由讀寫、匯出 |
| `chat` | 對話歷史唯讀 | 只能 `/history` 看、`/clear chat` 清 |

切換工作區：

```
/ws          ← 列出所有工作區（標示當前）
/ws stt      ← 切換到 stt
/ws buffer   ← 切回 buffer
```

> **重要**：語音辨識出的文字**只進當前工作區**。想把語音收進 stt，先 `/ws stt`，
> 再按 Alt+F8（KDE）或 F8（X11）錄音。

---

## 6. 斜線指令

直接在終端機輸入框打就能用。

### 6.1 內容操作（作用於當前工作區）

| 指令 | 功能 |
|---|---|
| `/show` | 看當前工作區內容（有編號） |
| `/clear` | 清空當前工作區 |
| `/clear ui` | 清畫面顯示（不清工作區） |
| `/clear buffer`、`/clear stt`、`/clear chat` | 清指定工作區 |
| `/del <編號>` | 刪掉指定那一筆 |
| `/move <來源> <目標>` | 把某筆移到指定位置 |
| `/to_top [編號]` | 把那筆（預設最後一筆）移到最前面 |
| `/concat` | 把多筆壓成一筆 |
| `/copy` | 複製當前工作區到系統剪貼簿 |
| `/paste` | 從剪貼簿貼進來（每行一筆；chat 不支援） |
| `/export <檔名>` | 匯出工作區為 JSON |
| `/import <檔名>` | 從 JSON 匯入 |
| `/send` | 把 buffer 送給 LLM（只能在 buffer 用） |

### 6.2 對話管理

| 指令 | 功能 |
|---|---|
| `/new [名稱]` | 新建對話 |
| `/switch [名稱]` | 切換對話（預設 default） |
| `/list` | 列出所有對話 |
| `/rename <舊> <新>` | 改名 |
| `/delete <名稱>` | 刪除對話 |
| `/history` | 看目前對話的歷史 |
| `/save [檔名]` | 存到檔案 |
| `/load <檔名>` | 從檔案載入 |

### 6.3 其他

| 指令 | 功能 |
|---|---|
| `/stop` | 停止 TTS 朗讀 |
| `/help` | 指令一覽 |
| `/exit` | 離開程式 |

不加斜線直接打文字按 Enter，就是把這段文字加入當前工作區（和 F8 錄音進來一樣）。

---

## 7. 語音指令模式（F7）

按 F7 開始錄音、再按 F7 停止，辨識到的文字不會進工作區，而是被解析成指令。

支援的關鍵字（說中文或英文都可以）：

| 說出來的話 | 對應指令 |
|---|---|
| 發送、傳送、send | `/send` |
| 清除、clear | `/clear` |
| 顯示、show | `/show` |
| 停止、stop | `/stop` |
| 工作區、workspace | `/ws` |
| 新建、開啟對話、new | `/new` |
| 切換、switch | `/switch` |
| 列表、list | `/list` |
| 刪除、delete | `/delete` |
| 保存、儲存、save | `/save` |
| 歷史、紀錄、history | `/history` |
| 複製、copy | `/copy` |
| 貼上、paste | `/paste` |
| 壓縮、連接、concat | `/concat` |
| 置頂、to top | `/to_top` |
| 匯出、export | `/export` |
| 匯入、import | `/import` |
| 幫助、說明、help | `/help` |

---

## 8. 設定檔（config.ini）速查

### [AUDIO] — 錄音行為

```ini
silence_seconds = 1.5      # 靜音幾秒後自動停止錄音
silence_threshold = 300    # 靜音判斷閾值（越小越靈敏）
max_duration = 0           # 最長錄音秒數，0 = 不限
```

### [CONTROL] — 熱鍵

```ini
key_record_toggle = f8
key_command_toggle = f7    # 預設值，可手動加入並修改
key_quick_send = f9
key_force_stop_tts = f10
key_play_last_original = f6
```

### [STT] — Whisper

```ini
model_size = base          # tiny/base/small/medium/large-v2/large-v3
device = cpu               # cpu 或 cuda
compute_type = int8        # CPU: int8/float32；GPU: float16
language = auto            # auto/zh/en/ja/…
beam_size = 5              # 1=最快，5=預設，越大越準但越慢
vad_filter = true          # 靜音過濾，建議開著
initial_prompt =           # 上文提示，引導繁體／常用詞；留空不使用
```

### [SLM] — 本地摘要小模型

```ini
enabled = false             # 直通 LLM→TTS；啟用後長回覆會先摘要
model = gemma3:1b          # Ollama 模型名稱
base_url = http://localhost:11434/v1
summary_threshold = 20     # 回覆超過幾個字才啟動摘要
```

### [LLM] — 主對話模型

```ini
model = qwen/qwen3.5-9b
base_url = http://localhost:1234/v1
api_key =                  # LM Studio 未啟用驗證時留空
```

LM Studio 使用方式：

1. 在 Developer 頁啟動 Local Server，預設 port 為 `1234`。
2. 載入與 `model` 相同 ID 的模型；也可啟用 Just-In-Time loading。
3. 確認 `curl http://localhost:1234/v1/models` 能列出模型。
4. `[SERVER] enabled = false`，讓 Voice Client 直接呼叫 `[LLM]`。

目前預設 `[SLM] enabled = false`，因此 LLM 完整回覆會直接送進 Kokoro。若啟用 SLM，
還必須把 `[SLM]` 指向一個可用模型，否則長回覆只會進摘要流程而不會朗讀。

Gemini 或其他雲端 API 範例：

```ini
model = gemini-2.5-flash-lite
base_url = https://generativelanguage.googleapis.com/v1beta/openai/
api_key = 你的API金鑰
```

### [SERVER] — 轉發模式

```ini
enabled = false   # false = 直連 LLM；true = 把輸入 POST 給中間伺服器
url = http://localhost:8000/chat
```

### [TTS] — 語音合成

```ini
engine = kokoro
rate = 180                         # 只供 pyttsx3 使用
volume = 1.0                       # 音量 0.0–1.0
kokoro_model_dir = models/kokoro
kokoro_voice_en = af_heart
kokoro_voice_zh = zf_001
kokoro_speed = 1.0
```

`engine` 可設為 `kokoro` 或 `pyttsx3`。Kokoro 使用本機 ONNX 模型，中英混合文字會分段
合成；模型由長駐 worker 載入一次。`/stop`、F10 與 high priority 訊息都能取消目前播放。

---

## 9. 疑難排解

| 症狀 | 解法 |
|---|---|
| KDE Wayland 上 Alt+F8 沒反應 | 確認 Voice Client 正在執行、`/run/user/$UID/voice-client-control.sock` 存在，並查看 [KDE 快捷鍵文件](kde_wayland_shortcuts.md) |
| 啟動說「全域熱鍵已停用」 | `pynput` 路徑不可用；KDE 使用者確認是否同時顯示「Wayland 本機控制已啟用」，其他環境改用斜線指令 |
| 同時開兩個 Voice Client | 不支援；兩個程序會爭用同一個控制 socket，只保留一個桌面程序 |
| 錄音按了沒反應 | 確認麥克風權限，`pamixer --list-sources` 看看有沒有輸入裝置 |
| 辨識很慢 | `model_size = tiny`，`beam_size = 1` |
| Kokoro 完全沒聲音 | 確認 `models/kokoro/` 模型完整、系統有可用的 PortAudio 輸出裝置，並查看 `output/system.log` |
| pyttsx3 完全沒聲音 | Linux 確認已安裝 `espeak-ng` |
| TTS 講話很怪 | `pyttsx3` 的 rate 調慢，或換 `kokoro` 引擎 |
| LLM 沒有回應 | 確認 `[LLM] base_url` 對了，本地 Ollama 的話先確認 `ollama serve` 在跑 |
| LM Studio 沒有回應 | 確認 Local Server 已啟動、`/v1/models` 可連線，且 `model` ID 完全相同 |
| 打字輸入沒反應 | 游標要在終端機輸入框，不是在其他地方 |
| pyaudio 裝不起來 | `sudo pacman -S portaudio python-pyaudio` 試試系統包 |
| 手機連不上 | 確認同一個 WiFi；防火牆 `sudo ufw allow 8080`；網址用 `https://` |

日誌：`output/system.log`（等級在 `[LOGGING] level` 設定）。

---

## 10. 手機模式

1. 啟動：`python mobile_server.py`
2. 終端會顯示連線網址（例 `https://192.168.x.x:8080`），手機和電腦要在同一個 WiFi
3. 自簽憑證會有安全警告：點「進階」→「繼續前往」
4. 手機上可錄音（伺服器端 Whisper 辨識）、看回覆、瀏覽器原生語音朗讀

`[MOBILE]` 可設定 host、port、ssl。**SSL 建議開著**，現代手機瀏覽器要 HTTPS 才讓用麥克風。
