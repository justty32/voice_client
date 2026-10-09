# 已落地功能索引

只記錄穩定、值得快速導航的功能摘要；實作細節以 CODE_MAP、docs 與 git log 為準。

- Data Tunnel 桌面架構：`core/`、`modules/`、`app.py`。
- 多工作區、統一指令路由與聊天摘要流程。
- 手機 FastAPI／WebSocket 模式。
- 錄音靜音前置保留與避免純靜音反覆送 STT。
- espeak 中文／英文 voice 自動選擇。
- KDE Plasma Wayland F8：KDE Global Shortcuts 經 `local_control.py` 控制錄音切換。
- refactor_next（2026-10-09）：`protocol/` 協定單一來源＋契約測試、共享狀態加鎖、錯誤閉環（`stt_event`）、
  `build_core()`／`Lifecycle` 組裝、指令派發表、手機改走 Data Tunnel（`mobile/edge.py`）。
