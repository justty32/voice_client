# Roadmap

記錄「確定會做，但尚未排入實作」的項目。進入認真設計時移到 specs；開始施工前建立 plan。

## Open

- TTS backend 抽象化，使 `config.ini [TTS].engine` 真正控制 pyttsx3／其他引擎。
- 導入 Kokoro ONNX，保留 espeak 作為低成本 fallback。
- 將 `mobile_server.py` 對齊 Data Tunnel（refactor_next 7b 已完成），之後移除舊桌面路由相容元件（待 D4）。
