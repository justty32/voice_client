# dev-env — 開發環境

## 基本需求

- Python 3.10+
- 專案虛擬環境 `.venv`
- FFmpeg
- PortAudio／PyAudio
- Linux TTS 使用 `espeak-ng`

Debian/Ubuntu：

```bash
sudo apt install python3-dev portaudio19-dev ffmpeg espeak-ng libssl-dev
```

Python 依賴：

```bash
.venv/bin/python -m pip install -r requirements.txt
```

## 執行

```bash
.venv/bin/python main.py
.venv/bin/python app.py
uv run app.py
.venv/bin/python mobile_server.py
```

## 環境差異

- X11：可使用 `pynput` 全域熱鍵。
- KDE Plasma + Wayland：可用 KDE Global Shortcuts + `local_control.py`；本機設定見
  `docs/kde_wayland_shortcuts.md`。
- 其他 Wayland／SSH／headless：沒有桌面快捷鍵提供者時改用斜線指令。
- 沒有麥克風／喇叭仍可做大部分單元與接線測試。
- Ollama／遠端 LLM、Whisper 模型與手機 HTTPS 屬執行期依賴，不應成為核心單元測試前置。
