# SenseVoice STT 方案調查（中文辨識的替代引擎）

> 調查日期：2026-06-22　環境：Manjaro Linux、Python 3.12（`.venv`，uv 建立）、
> NVIDIA RTX 5060 Ti 16GB（CUDA 13 系統）

## 0. 為什麼有這份調查（結論先講）

使用者主要講中文，抱怨原 `base` 模型常認錯字。已先把 STT 升級為
**faster-whisper `large-v3-turbo` / `large-v3`（GPU）**，真人驗收準度明顯改善。
本文是更進一步的調查：**若想要中文辨識再上一層樓，SenseVoice 是本機方案裡最有潛力
超越 Whisper 的選項**。

- **值得做**：SenseVoice-Small 又小、又快、且**中文/粵語辨識普遍勝過 Whisper**。
- **但別用官方 `funasr`**：它會把整個 PyTorch（~2-3GB，還要對 CUDA 版本）拉進來，
  破壞本專案「只用 CTranslate2、不裝 torch」的輕量架構。**建議走 `sherpa-onnx`**
  （ONNX runtime，不需 torch，風格與現狀一致）。
- **這是調查，尚未實作。** 目前 STT 仍是 faster-whisper。

---

## 1. SenseVoice-Small 規格

| 項目 | 數字／說明 |
|---|---|
| 參數量 | **234M**（與 whisper-small 同級；large-v3 約 1.5B） |
| 模型大小（磁碟） | **~900MB**（< turbo 1.6GB、< large-v3 2.9GB） |
| VRAM | **約 1~2GB**（16GB 卡無感；large-v3 約需 ~7GB） |
| 推論速度 | 非自回歸，**比 whisper-large 快 ~15×**（10 秒音訊約 70ms） |
| 語言 | 中文／粵語／英／日／韓；**中文是強項** |
| 額外能力 | 情緒辨識（SER）、語者事件偵測（AED）、語言辨識（LID） |

## 2. 準度：中文勝過 Whisper

官方論文（FunAudioLLM, arXiv 2407.04051）benchmark：SenseVoice-Small 在中文／粵語
多數測試集**贏過對應的 Whisper**。代表性數據：

- **粵語 CER**：Whisper-large-v3 **10.41%** vs SenseVoice **7.09%**。
- 普通話多數測試集亦較佳（Librispeech 純英文除外，Whisper 仍強）。

對「主要講中文」的使用情境，這是最直接的吸引力：**更小、更快、對中文更準**。

## 3. 接進本專案的工程量

### 3.1 好消息：STT 介面很乾淨

`VoiceToText`（`voice_to_text.py`）對外契約單純，換引擎**不需動 `app.py` /
`mobile_server.py` 的接線**：

- 建構：`VoiceToText(config, audio_queue, stt_output_queue)`（`voice_to_text.py:15`）
- 輸入：WAV `BytesIO`，**16kHz / mono / 16-bit**（`config.ini [AUDIO] sample_rate=16000`；
  mobile 端轉檔見 `mobile_server.py:75-76`）
- 輸出：純文字 `str`，放進 `stt_output_queue`（`voice_to_text.py:50-52`）
- 接線點（皆**不需改**）：`app.py:297`（實例化）、`app.py:349/402`（起停）、
  Exchange 綁定 `app.py:170-171,189`、mobile `mobile_server.py:110,161,167`

### 3.2 要做的改動

| 檔案 | 改動 | 估計 |
|---|---|---|
| `voice_to_text.py` | 抽出引擎抽象 + 工廠，依 `[STT] engine` 選 `faster-whisper`／`sensevoice` | +80~100 行 |
| `config.ini` | `[STT]` 新增 `engine = faster-whisper` | +1 行 |
| `requirements.txt` | 新增 `sherpa-onnx`（**不要** funasr/torch） | +1~2 行 |
| `tests/test_voice_to_text.py` | 引擎選擇／參數解析測試（參考既有 fake 模式） | +15~20 行 |
| `tests/`（新檔） | 端到端流程測試，仿 `test_voice_flow_integration.py` 的 `FakeLegacyStt` | +20~30 行 |
| `docs/architecture.md`、`README.md` | 說明引擎切換與安裝 | +15~25 行 |

> 註：本專案目前**沒有**任何「依 config 切換 driver/engine」的前例可抄
> （TTS 的 `text_to_voice.py` 是依 `sys.platform` 寫死，不是 config 切換）；
> 這個引擎抽象要新建，會成為日後加引擎的範本。

### 3.3 三個必須先處理的坑

1. **依賴變重（最重要的決策）**：SenseVoice 官方走 `funasr` → **拉進整個 PyTorch**
   （~2-3GB，須對齊 CUDA）。本專案特意只用 CTranslate2、**沒裝 torch**。
   → **改用 `sherpa-onnx`**（ONNX runtime，不需 torch，輕量），才不會把架構拖回 torch。
2. **輸出要清洗**：SenseVoice 會吐標記，如 `<|zh|><|NEUTRAL|><|Speech|>你好`，
   需加一步 postprocess 去標記後才是乾淨文字（FunASR 有 `rich_transcription_postprocess`，
   sherpa-onnx 路徑則自行 strip）。
3. **輸入要轉接**：funasr 的 `generate()` 吃檔案路徑／numpy，不直接吃 `BytesIO`；
   需加轉接（或走 sherpa-onnx 的 array 介面，從 WAV 解出 PCM numpy）。
4. **繁體未定**：資料稱「繁簡都能輸出」，但官方頁未明示，**須實測**；
   若偏簡體，需與 Whisper 相同做繁簡後處理（OpenCC 之類）。

### 3.4 工時現實估計

- 核心引擎切換（sherpa-onnx 路徑）：**~1 天**（介面乾淨，主要是新引擎類 + 輸出清洗）。
- 繁體／標記清洗驗證 + 真人中文驗收：**~0.5~1 天**。
- 比「教科書式」估的 4~6 天樂觀，因為 queue 介面單純、上下游不動。

## 4. 最小程式骨架（參考，未落地）

引擎抽象（放 `voice_to_text.py` 頂部）：

```python
class SttEngine:
    def load_model(self) -> None: ...
    def transcribe(self, audio_buffer) -> str: ...

def _create_engine(name, cfg) -> SttEngine:
    if name == "faster-whisper": return FasterWhisperEngine(cfg)
    if name == "sensevoice":     return SenseVoiceEngine(cfg)
    raise ValueError(f"Unknown STT engine: {name}")
```

SenseVoice（**sherpa-onnx 路徑，不需 torch**）大致長相：

```python
import sherpa_onnx, soundfile as sf, numpy as np
# 載入：sherpa_onnx.OfflineRecognizer.from_sense_voice(model="...sense-voice.onnx", ...)
# transcribe：從 WAV BytesIO 解出 16k mono float32 → recognizer 推論 → strip 標記
```

官方 funasr 路徑（**會帶 torch，本專案不建議**）僅供對照：

```python
from funasr import AutoModel
model = AutoModel(model="iic/SenseVoiceSmall", device="cuda:0", hub="hf")
res = model.generate(input="audio.wav", language="auto", use_itn=True)
```

## 5. 建議下一步

1. **先做最小 spike**：用 `sherpa-onnx` 在本機把 SenseVoice 跑起來、餵一段真實中文音訊，
   實測**準度與繁簡輸出**，確認值得再正式接。
2. spike 過關 → 進 feature-dev 做完整 `engine` 切換（含測試與文件同步）。
3. 若 spike 發現繁體要額外處理或 sherpa-onnx 整合卡關，再回頭評估是否值得。

## 6. 參考來源

- SenseVoice GitHub：<https://github.com/FunAudioLLM/SenseVoice>
- SenseVoiceSmall · HuggingFace：<https://huggingface.co/FunAudioLLM/SenseVoiceSmall>
- FunAudioLLM 論文（arXiv 2407.04051）：<https://arxiv.org/html/2407.04051v1>
- FunASR vs Whisper 中文實測討論：<https://github.com/modelscope/FunASR/discussions/2947>
- FunASR toolkit：<https://github.com/modelscope/FunASR>
</content>
</invoke>
