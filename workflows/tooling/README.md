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

## 開發／測試用 Python 套件

`fastapi`、`uvicorn` 除了手機模式執行期需要，也是 `tests/test_mobile_server.py` 的依賴；
`httpx` 只供 `fastapi.testclient` 使用（列於 `requirements.txt` 的開發段）。缺少時該測試檔整檔 skip。

## 開發輔助工具

| 工具 | 用途 |
|---|---|
| `python workflows/common/code-map/codemap.py [big\|topics\|deps M\|show P\|json]` | AST 即時掃描：行數、依賴、topic 生產／消費圖 |
| `bash wf/tools/wf-lint.sh .` | 文件連結、超標檔、大清單、模板殘留檢查 |
| `python3 wf/tools/fix_moved_links.py` | 搬檔後依 moves.tsv 修 md 連結 |
