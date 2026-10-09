# 使用手冊：設定檔速查

[使用手冊入口](../user_manual.md)

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
