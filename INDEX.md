# INDEX — Voice Client 專案地圖

Voice Client 將麥克風、STT、工作區、LLM、摘要、TTS 與桌面／手機介面串成一個語音優先客戶端。

| 路徑 | 內容 |
|---|---|
| `main.py` / `app.py` | 桌面入口與 Data Tunnel 接線 |
| `core/` | Message、Inbox/Outbox、Exchange、TunnelModule、Adapter |
| `protocol/` | topic 名稱常數與 payload 建構函式（協定單一來源） |
| `modules/` | WorkspaceManager、SttGate、CommandRouter、ChatFlow、CLI bridge |
| `record.py` / `voice_to_text.py` / `text_to_voice.py` | 錄音、STT、TTS |
| `keyboard_listener.py` / `local_control.py` | X11 熱鍵與 Wayland/KDE 本機控制 |
| `mobile_server.py` / `static/` | 手機 Web 模式 |
| `workspace.py` / `session_manager.py` | 工作區與對話持久化 |
| `tests/` | 單元、整合與接線測試 |
| `ai_assist/` / `server_sample/` | 非產品內容：另一實驗專案文件與 `SERVER.enabled=true` 的測試對端；codemap 排除 |
| `docs/` | 架構、使用手冊與技術調查 |
| `plans/` | 現役與歷史設計／實作計畫 |
| `reports/` | 程式碼健檢報告（bug、擴展方向、架構改進） |
| `workflows/` | 開發工作流與 durable 工程知識 |
| `wf/` | 通用工作流 kernel 補充包（tidy、decisions、wf-lint 等）|

## 導航入口

- 程式碼地圖：[workflows/common/code-map/CODE_MAP.md](workflows/common/code-map/CODE_MAP.md)
- 工作流派發：[WORKFLOWS.md](WORKFLOWS.md)
- 架構文件：[docs/architecture.md](docs/architecture.md)
- 使用手冊：[docs/user_manual.md](docs/user_manual.md)
- KDE Wayland 快捷鍵：[docs/kde_wayland_shortcuts.md](docs/kde_wayland_shortcuts.md)
- 開發環境：[workflows/dev-env.md](workflows/dev-env.md)
