# 使用手冊：安裝

[使用手冊入口](../user_manual.md)

## 1. 安裝（Manjaro）

### 1.1 系統套件

```bash
sudo pacman -S --needed python portaudio ffmpeg espeak-ng
```

- `portaudio`：pyaudio 錄音依賴
- `ffmpeg`：手機模式音訊轉檔（只跑桌面 TUI 可略）
- `espeak-ng`：`[TTS] engine = pyttsx3` 時的 Linux 朗讀後端；預設 Kokoro 不需要（英文詞表外字詞可作後援）

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

預設 TTS 是 Kokoro，模型檔（約 717 MB）不在 repo 內，需自行下載到 `models/kokoro/`，
步驟見 [TTS 調查與 Kokoro 安裝](../tts_kokoro_investigation.md) §2a。

### 1.3 熱鍵支援

- **X11**：F6–F10 全域熱鍵正常。
- **KDE Plasma + Wayland**：`pynput` 無法抓全域鍵，但可以使用 KDE Global
  Shortcuts 呼叫 `local_control.py`。目前本機已設定 Alt+F8／Alt+F9；完整設定與故障排除見
  [KDE Wayland 全域快捷鍵](../kde_wayland_shortcuts.md)。
- **其他 Wayland、SSH / headless**：沒有 KDE 快捷鍵時使用斜線指令，TUI 打字流程不受影響。
