# TTS 中英文方案調查（含 Kokoro 安裝指南）

> 調查日期：2026-06-20；落地更新：2026-06-22。環境：Manjaro Linux、Python 3.12.13。

## 0. 現況結論（重要）

Kokoro 已於 2026-06-22 接入桌面 TTS，`config.ini` 預設為 `engine = kokoro`。

- 英文使用 Kokoro v1.0，中文使用專用 v1.1-zh 模型。
- `text_to_voice.py` 以長駐 worker 載入模型，中英混合文字會分段合成。
- 播放使用 PyAudio，保留 high priority 打斷、F10／`/stop` 與 mute 語意。
- `pyttsx3` 仍可作 fallback；Linux 使用該後端時才需要 `espeak-ng`。

---

## 1. 三條可走的路（中英文都支援）

| 方案 | 中英文 | 品質 | 離線 | 延遲 | 安裝成本 | 對現有程式衝擊 |
|---|---|---|---|---|---|---|
| **espeak-ng**（補裝即可救活現狀） | ✅ en + cmn(zh) | 低（機械音） | ✅ | 極低 | 一行 pacman | 零（pyttsx3 已接好） |
| **gTTS**（已安裝） | ✅ en + zh | 高（Google） | ❌ 需連網 | 中（每句一次 HTTP） | 已裝好 | 中（要改播放流程） |
| **Kokoro**（神經網路、本機） | ✅ 20 英 + 8 中 | 高 | ✅ | 中低（首次載模型較久） | 較高（見下） | 中（要新增引擎） |

### 1a. 最快救火：espeak-ng
```bash
sudo pacman -S espeak-ng        # extra/espeak-ng 1.52.0 已在官方源
```
裝完 pyttsx3 立刻能用，且 espeak-ng 同時支援英文與普通話（語音代碼 `cmn`/`zh`）。
缺點是音質機械、中文尤其生硬。**建議先裝它確保不啞，再評估 Kokoro。**

### 1b. 已在手上：gTTS
`gtts 2.5.4` 已在 `.venv`，中英文品質好，但**需連網**、每句一次 HTTP 往返、有延遲與隱私考量，
且目前 `text_to_voice.py` 是 pyttsx3 子進程架構，要接 gTTS 得改播放層（下載 mp3 → 用 pydub/
ffmpeg 播放）。適合「有網路、要好音質、不在意延遲」的場景。

---

## 2. Kokoro 安裝調查（重點）

Kokoro-82M 是 82M 參數的開源神經 TTS（Apache 權重），本機推論、品質高。
**支援 9 語言約 51 個語音，含美式英文 20 個、普通話 8 個** — 完全滿足中英文需求。

> 普通話語音：女聲 `zf_xiaobei / zf_xiaoni / zf_xiaoxiao / zf_xiaoyi`，
> 男聲 `zm_yunjian / zm_yunxi / zm_yunxia / zm_yunyang`（官方標註中文語音品質等級偏低 D，
> 訓練資料較少，但仍遠勝 espeak）。
> 美式英文如 `af_bella`(A-)、`af_heart`、`am_michael` 等品質較高。

Python 需求 `>=3.10, <3.13` — 本機 **3.12.13 ✅ 相容**。

有兩種實作，**建議用 kokoro-onnx**（輕、不強制 PyTorch）：

### 2a. 方案 A：`kokoro-onnx`（推薦，輕量、ONNX runtime）
```bash
# 在專案 venv 裡
VIRTUAL_ENV=.venv uv pip install kokoro-onnx soundfile
# 中文 v1.1 分詞／拼音
VIRTUAL_ENV=.venv uv pip install "misaki-fork[zh]"
```
下載模型檔（放到專案目錄，例如 `models/`）：
```bash
# 約 300MB；另有量化版 ~80MB
wget https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
wget https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
# 中文專用 v1.1
wget https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/kokoro-v1.1-zh.onnx
wget https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.1/voices-v1.1-zh.bin
wget -O config-v1.1-zh.json https://huggingface.co/hexgrad/Kokoro-82M-v1.1-zh/raw/main/config.json
```
最小範例：
```python
import soundfile as sf
from kokoro_onnx import Kokoro
from misaki import zh

# 英文
kokoro = Kokoro("models/kokoro-v1.0.onnx", "models/voices-v1.0.bin")
samples, sr = kokoro.create("Hello, this is a test.", voice="af_heart", lang="en-us")
sf.write("en.wav", samples, sr)
# 中文 v1.1 先由 Misaki 轉音素
g2p = zh.ZHG2P(version="1.1")
kokoro_zh = Kokoro(
    "models/kokoro-v1.1-zh.onnx",
    "models/voices-v1.1-zh.bin",
    vocab_config="models/config-v1.1-zh.json",
)
phonemes, _ = g2p("你好，這是一段測試。")
samples, sr = kokoro_zh.create(phonemes, voice="zf_001", is_phonemes=True)
sf.write("zh.wav", samples, sr)
```
- 體積：onnx ~300MB（量化 ~80MB）。
- espeak-ng：**中文路徑不需要**（走 misaki[zh]）；英文遇到詞表外字詞會 fallback 到
  espeak-ng，所以**建議仍裝 espeak-ng 當英文後援**（見 1a）。

### 2b. 方案 B：`kokoro`（官方套件，需 PyTorch，較重）
```bash
VIRTUAL_ENV=.venv uv pip install "kokoro>=0.9.4" soundfile "misaki[zh]"
sudo pacman -S espeak-ng     # 此版本明確需要 espeak-ng 做 OOD fallback
```
```python
from kokoro import KPipeline
pipeline = KPipeline(lang_code='z')           # 'z' = 普通話；'a' = 美式英文
for gs, ps, audio in pipeline("中國人民不信邪也不怕邪", voice="zf_xiaoxiao"):
    ...  # audio 為 numpy，自行寫檔/播放
```
比 onnx 版多拉 PyTorch（數百 MB～GB），且強制要 espeak-ng。除非要訓練/微調，否則用 A。

---

## 3. 本專案落地方式

1. `AudioPriorityPlayer` 依 `engine = kokoro | pyttsx3` 選擇後端。
2. Kokoro worker 在程序存活期間重用模型；取消播放使用單調遞增任務編號，不需殺掉 worker。
3. 中英混句依 CJK／ASCII 文字切片，分別使用 v1.1-zh 與 v1.0。
4. 模型位於 `models/kokoro/` 並由 `.gitignore` 排除，總大小約 717 MB。

## 4. 建議落地順序

目前以上落地項目均已完成；剩餘項目是實際喇叭與完整對話流程的人工驗證。

## 參考來源
- [kokoro-onnx (GitHub, thewh1teagle)](https://github.com/thewh1teagle/kokoro-onnx)
- [kokoro (PyPI)](https://pypi.org/project/kokoro/)
- [kokoro-onnx (PyPI)](https://pypi.org/project/kokoro-onnx/)
- [Kokoro-82M VOICES.md（語音清單與品質等級）](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)
- [pykokoro (PyPI)](https://pypi.org/project/pykokoro/)
