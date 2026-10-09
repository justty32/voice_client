# 使用手冊：設定檔速查

[使用手冊入口](../user_manual.md)

## 8. 設定檔（config.ini）速查

下列範例的值是 **repo 附的 `config.ini`** 內容；註解中的「程式預設」是缺鍵時的 fallback。
改設定後需重啟程式。

### [AUDIO] — 錄音行為

```ini
sample_rate = 16000        # 取樣率（STT 需 16 kHz）
channels = 1
chunk_size = 1024          # 每次讀取的 frame 數
silence_seconds = 1.5      # 說完話後靜音幾秒就切出一段送 STT（錄音繼續，直到再按一次錄音鍵）
silence_threshold = 300    # 靜音判斷閾值（越小越靈敏）
max_duration = 0           # 連續講話時單段最長秒數，到了強制切段；0 = 不限
```

`chunk_duration` 目前會被讀取但不影響行為。錄音期間每段都會即時辨識並寫入工作區；
按鍵停止時只在最後一段確實有語音時才送 STT。

### [CONTROL] — 熱鍵（只影響 pynput／X11 路徑）

```ini
key_record_toggle = f8
key_command_toggle = f7    # config.ini 沒有這行；程式預設 f7，可手動加入並修改
key_quick_send = f9
key_force_stop_tts = f10
key_play_last_original = f6
```

### [STT] — Whisper

```ini
model_size = large-v3      # 程式預設 base；tiny/base/small/medium/large-v2/large-v3/large-v3-turbo
device = cuda              # 程式預設 cpu；cpu 或 cuda
compute_type = float16     # 程式預設 int8；CPU: int8/float32；GPU: float16
language = zh              # 程式預設 auto；auto/zh/en/ja/…
beam_size = 5              # 1=最快，越大越準但越慢
vad_filter = true          # 靜音過濾，建議開著
initial_prompt = 以下是繁體中文的句子。   # 上文提示；留空不使用
```

沒有 NVIDIA GPU 的機器請改回 `device = cpu`、`compute_type = int8`、較小的 `model_size`，
細節見 [STT 引擎](stt.md)。

### [SLM] — 本地摘要小模型

```ini
enabled = false            # 程式預設 true；false＝LLM 回覆直接朗讀
model = gemma3:1b          # Ollama 模型名稱
base_url = http://localhost:11434/v1
api_key =
summary_threshold = 20     # 回覆達幾個字才先摘要再朗讀
retry = 0                  # 失敗重試次數（程式預設 3）
```

啟用後，達門檻的長回覆先送 SLM 摘要、朗讀摘要；摘要失敗或回空時會顯示
`[摘要失敗] …，改播原文` 並朗讀完整原文。摘要提示詞在 `prompts/slm_summary.txt`。

### [LLM] — 主對話模型

```ini
model = qwen/qwen3.5-9b
base_url = http://localhost:1234/v1
api_key =                  # LM Studio 未啟用驗證時留空
retry = 0                  # 失敗重試次數（缺鍵時沿用 [SERVER] retry）
```

系統提示詞在 `prompts/llm_system.txt`。LLM 呼叫失敗時，送出的內容會備份到
`[WORKSPACE] failed_dir`，畫面顯示 `[錯誤] …` 並朗讀。

LM Studio 使用方式：

1. 在 Developer 頁啟動 Local Server，預設 port 為 `1234`。
2. 載入與 `model` 相同 ID 的模型；也可啟用 Just-In-Time loading。
3. 確認 `curl http://localhost:1234/v1/models` 能列出模型。
4. `[SERVER] enabled = false`，讓 Voice Client 直接呼叫 `[LLM]`。

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
timeout = 30      # 秒
retry = 0         # 程式預設 3
```

`server_sample/server.py` 是轉發模式的測試對端範例。

### [TTS] — 語音合成

```ini
engine = kokoro                    # 程式預設 pyttsx3；kokoro 或 pyttsx3
rate = 180                         # 只供 pyttsx3 使用
volume = 1.0                       # 音量 0.0–1.0
kokoro_model_dir = models/kokoro   # 相對路徑以專案根為準
kokoro_voice_en = af_heart
kokoro_voice_zh = zf_001
kokoro_speed = 1.0
```

Kokoro 使用本機 ONNX 模型，中英混合文字會分段合成；模型由長駐 worker 載入一次。
`/stop`、F10 與 high priority 訊息都能取消目前播放。

### [WORKSPACE] — 檔案位置

```ini
sessions_file = output/.sessions.json   # 對話集合
failed_dir = output/failed              # LLM 失敗時的送出內容備份
log_file = output/system.log
```

另有兩個 `config.ini` 沒寫、但程式會讀的鍵：`export_file`（預設 `output/export.json`，
取其目錄作為 `/export`、`/import` 與手機 `_buffer_temp.json` 的目錄）與
`deleted_sessions_dir`（預設 `output/deleted`，`/delete` 前的備份）。
`/save`、`/load` 只給檔名時放在 `sessions_file` 所在目錄。

### [LOGGING]、[MOBILE]

```ini
[LOGGING]
level = INFO

[MOBILE]
host = 0.0.0.0
port = 8080
ssl = true
ssl_cert = output/ssl/cert.pem   # 不存在時自動產生自簽憑證
ssl_key = output/ssl/key.pem
```

### 目前未被程式讀取的鍵

`config.ini` 裡的 `[SESSION] auto_save`、`backup_interval`，`[WORKSPACE] output_dir`、
`permissions_file`，`[UI] status_refresh_rate` 目前沒有任何程式讀取，改了不會生效。
