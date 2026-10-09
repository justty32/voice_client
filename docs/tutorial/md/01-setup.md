# 1. 準備與第一次開機

[入門手冊目錄](../README.md)｜下一章：[說話變文字](02-talk.md)

## 先準備三樣東西

就像做菜前要先買菜，小幫手需要幾個工具才能工作：

1. **麥克風和喇叭**：耳朵和嘴巴要用的。
2. **系統套件**（Manjaro / Arch）：

   ```bash
   sudo pacman -S --needed python portaudio ffmpeg espeak-ng
   ```

   `portaudio` 讓程式能錄音，`espeak-ng` 讓它能說話，`ffmpeg` 是手機模式轉換聲音用的。
3. **Python 套件**：在專案資料夾裡執行

   ```bash
   python -m venv .venv
   .venv/bin/pip install -r requirements.txt
   ```

## 告訴它 AI 住在哪裡

小幫手自己不是 AI，它是幫你**寄信給 AI** 的信差。所以要先告訴它 AI 的地址。
打開 `config.ini`，找到 `[LLM]` 這一段：

```ini
[LLM]
model = qwen/qwen3.5-9b
base_url = http://localhost:1234/v1
```

`base_url` 是 AI 的地址。如果你用 LM Studio 或 Ollama 在自己電腦上跑 AI，
通常是 `http://localhost:...` 開頭；`model` 是那個 AI 的名字。

> 小提醒：`config.ini` 裡的每一段都有預設值，第一次只要改 `[LLM]` 就好。

## 第一次開機

```bash
.venv/bin/python main.py
```

畫面下方的狀態列出現「**待機**」，就代表它準備好了，正在等你說話。

第一次啟動會比較慢，因為速記員（語音辨識模型）要先「讀書」——把模型載入記憶體。
之後就快了。

## 要離開的時候

打 `/exit` 再按 Enter。小幫手會把每個房間的燈關好（依序停下所有模組）再離開。

下一章：[說話變文字](02-talk.md)
