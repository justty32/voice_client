# TTS 中英文方案調查（含 Kokoro 安裝指南）

> 調查日期：2026-06-20　環境：Manjaro Linux、Python 3.12.13（`.venv`，uv 建立）

## 0. 現況結論（重要）

**目前本機 TTS 完全發不出聲。**

- `config.ini` 設定 `engine = pyttsx3`，`text_to_voice.py` 在 Linux 寫死使用 `espeak` driver。
- 但本機 **沒有安裝 espeak / espeak-ng**，`pyttsx3.init("espeak")` 直接拋
  `RuntimeError: ... do not have eSpeak or eSpeak-ng installed!`。
- 換言之：「有沒有可用的中英文模型」→ **現在沒有**，需先補裝後端。

另注意：`config.ini` 內的 `engine`、`kokoro_url` 這些鍵，`text_to_voice.py` 目前
**完全沒讀**（寫死 pyttsx3）。要切換引擎需改程式，不是改設定就好。

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
# 中文分詞/拼音需要 misaki[zh]（jieba + pypinyin），英文 OOD 才需 espeak-ng
VIRTUAL_ENV=.venv uv pip install "misaki[zh]"
```
下載模型檔（放到專案目錄，例如 `models/`）：
```bash
# 約 300MB；另有量化版 ~80MB
wget https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx
wget https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin
```
最小範例：
```python
import soundfile as sf
from kokoro_onnx import Kokoro

kokoro = Kokoro("models/kokoro-v1.0.onnx", "models/voices-v1.0.bin")
# 英文
samples, sr = kokoro.create("Hello, this is a test.", voice="af_heart", lang="en-us")
sf.write("en.wav", samples, sr)
# 中文（語音用 zf_/zm_，lang 用 "zh"）
samples, sr = kokoro.create("你好，這是一段測試。", voice="zf_xiaoxiao", lang="zh")
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

## 3. 接進本專案的注意事項（給未來實作）

1. `text_to_voice.py` 目前是「每句 spawn 一個 pyttsx3 子進程、直接播放」。
   Kokoro 是「合成出 numpy/wav → 需要自己播放」，所以接 Kokoro 要：
   - 在 worker 裡載入一次模型（**不要每句重載**，載入慢）；
   - 合成 → 用 `sounddevice` / `pydub` / ffmpeg 播放；
   - 保留現有的優先級佇列與「high 打斷」語意（打斷 = 停止當前播放）。
2. 應讓 `config.ini` 的 `engine` 真正生效：`pyttsx3 | gtts | kokoro` 三選一，
   各自一個後端類別，`AudioPriorityPlayer` 依設定挑選。
3. 中英混合句：Kokoro 單次 `create` 綁定一個 `lang`，混合中英可能需要分段（依語言切片）
   或接受以單一語言模型硬唸。先確認實際語料再決定。
4. 語音檔/模型不要進 git，加到 `.gitignore`（onnx + voices.bin 共 ~300MB）。

## 4. 建議落地順序

1. **立刻**：`sudo pacman -S espeak-ng` → 確保 TTS 不啞（零改碼）。
2. **短期**：把 `engine` 設定接通，讓 pyttsx3 / gtts 可切換。
3. **目標**：導入 `kokoro-onnx`（中英文高品質、離線），作為預設引擎，espeak-ng 留作後援。

## 參考來源
- [kokoro-onnx (GitHub, thewh1teagle)](https://github.com/thewh1teagle/kokoro-onnx)
- [kokoro (PyPI)](https://pypi.org/project/kokoro/)
- [kokoro-onnx (PyPI)](https://pypi.org/project/kokoro-onnx/)
- [Kokoro-82M VOICES.md（語音清單與品質等級）](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)
- [pykokoro (PyPI)](https://pypi.org/project/pykokoro/)
