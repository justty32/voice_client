# 使用手冊：STT 引擎

[使用手冊入口](../user_manual.md)

## 2. STT 引擎安裝與調整

STT 引擎是 [faster-whisper](https://github.com/SYSTRAN/faster-whisper)，本地跑、離線、不送雲端。

### 2.1 模型第一次啟動自動下載

設定好 `model_size` 後，第一次執行 `python main.py` 時 Whisper 會自動下載模型到 `~/.cache/huggingface/hub/`。下載完後就是離線使用。

### 2.2 模型大小選擇

在 `config.ini` 的 `[STT]` 區設定：

```ini
[STT]
model_size = large-v3
```

| 模型 | 大小 | 速度 | 準確度 | 適合場景 |
|---|---|---|---|---|
| `tiny` | 75 MB | 最快 | 最低 | 低資源機器、快速測試 |
| `base` | 145 MB | 快 | 尚可 | CPU 日常用夠了 |
| `small` | 483 MB | 中 | 好 | 想更準但不換 GPU |
| `medium` | 1.5 GB | 慢 | 很好 | CPU 跑會明顯延遲 |
| `large-v2` | 3 GB | 很慢 | 最好 | 需要 GPU |
| `large-v3` | 3 GB | 很慢 | 最好（新版） | **預設值**，需要 GPU |
| `large-v3-turbo` | 1.6 GB | 快（GPU） | 很好（略低於 v3） | **GPU 推薦，速度／準度最佳平衡** |

> 預設（`config.ini` 與程式缺鍵時相同）是 `large-v3`、`device = cuda`、`compute_type = float16`、
> `language = zh`。沒有 NVIDIA GPU 時請改成 CPU 設定（見 2.3、2.4）。

一般建議：CPU 跑用 `base`（或 `small` 可接受），有 GPU 用 `large-v3-turbo`（快又準、VRAM 省）；要極致準度才用 `large-v3`。

> 想要中文辨識再上一層樓？有個比 Whisper 對中文更準的替代引擎（SenseVoice）調查
> 記在 [docs/sensevoice_investigation.md](../sensevoice_investigation.md)，尚未實作。

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
> 裝好後 `speech/voice_to_text.py` 啟動時會自動預載它，無需設 `LD_LIBRARY_PATH`。

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
