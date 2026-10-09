# Voice Client 架構文檔

更新日期：2026-10-09
適用版本：`refactor/data-tunnel` 分支（資料隧道重構與 refactor_next **全部完成**；桌面與手機共用 `build_core()`）

## 1. 總覽

Voice Client（V-TUI Assistant）是一個語音優先的終端 AI 客戶端：
語音經本地 STT（faster-whisper）轉為文字、累積在工作區、由使用者掌控何時送往
LLM，回覆再經摘要（本地 SLM）與 TTS 朗讀。

系統已完成從「中央路由器」到「**資料隧道（Data Tunnel）**」架構的重構：
所有模組都是掛在具名通道（topic）上的**生產者／消費者**，資料交換由單執行緒
交換核心統一執行。桌面入口是 `app.py`（`main.py` 為薄殼）；手機入口 `mobile_server.py`
與桌面共用同一套核心，只替換邊緣裝置。

- 協定單一來源 `protocol/`：topic 名稱（`topics.py`）、payload 建構函式（`payloads.py`）、指令集（`commands.py`）。
- 組裝 `app_wiring/`：`topology.py` 的 `wire()` 純接線；`assembly.py` 的 `build_core()` 建 queue、
  SessionManager、原生模組與 Exchange，`Lifecycle` 統一啟停；`settings.py` 共用設定解讀。
- 業務模組 `modules/`；legacy 元件依領域分在 `speech/`、`ui/`、`llm/`、`domain/`；手機邊緣在 `mobile/`。

```
            生產者執行緒                交換核心（單執行緒）            消費者執行緒
        ┌──────────────┐           ┌──────────────────────┐        ┌──────────────┐
        │ Recorder     │─ outbox ─▶│                      │─ inbox ▶│ STT          │
        │ STT          │─ outbox ─▶│  Exchange            │─ inbox ▶│ 當前工作區    │
        │ 終端輸入      │─ outbox ─▶│  每次 tick 只搬一筆   │─ inbox ▶│ CommandRouter│
        │ 熱鍵／本機IPC │─ outbox ─▶│  依路由表 topic→inbox │─ inbox ▶│ TUI / TTS    │
        └──────────────┘           └──────────────────────┘        └──────────────┘
```

## 章節

§ 編號沿用原文件，報告與舊筆記中的「architecture.md §N」照下表找：

<!-- wf-nav -->
- §2 資料隧道框架（`core/`、交換語意、模組模型）→ [architecture/framework.md](architecture/framework.md)
- §3 通道（topic）規劃、§4 工作流 → [architecture/topics.md](architecture/topics.md)
- §5 新舊模組對照、§6 遷移路線圖 → [architecture/migration.md](architecture/migration.md)
- §7 執行緒模型與錯誤處理 → [architecture/runtime.md](architecture/runtime.md)
- §8 測試 → [architecture/testing.md](architecture/testing.md)

改資料流、topic、啟停順序時，更新對應章節檔；本檔只留總覽與目錄。

## 相關文件

- 使用手冊：`docs/user_manual.md`
- KDE Wayland 快捷鍵：`docs/kde_wayland_shortcuts.md`
