# tooling — 外部工具與執行期依賴

| 工具／服務 | 用途 | 缺少時 |
|---|---|---|
| FFmpeg | 手機錄音解碼／轉檔 | 手機音訊處理不可用 |
| PortAudio + PyAudio | 桌面麥克風錄音 | Recorder 無法啟動 |
| faster-whisper 模型 | 本地 STT | 首次可能需下載；離線且無快取時不可用 |
| espeak-ng | Linux pyttsx3 後端 | 本地 TTS 初始化失敗 |
| Ollama 或 OpenAI-compatible API | LLM／SLM | 對話或摘要不可用 |
| OpenSSL／cryptography | 手機 HTTPS 憑證 | 手機瀏覽器麥克風權限可能受限 |

設定入口是 `config.ini`。敏感 API key 不應提交；建議後續改用環境變數或本機覆寫檔。
