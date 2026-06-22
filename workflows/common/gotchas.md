# 共通踩坑

- 系統 Python 可能沒有測試依賴；優先使用 `.venv/bin/python`。
- `pynput` 全域熱鍵在 Wayland、SSH 或 headless 環境不可用；KDE Wayland 可改走
  `local_control.py`，不能看到 `pynput` warning 就誤判整個快捷鍵流程失敗。
- KDE `.desktop` 快捷鍵是使用者環境設定，不在 repo 內；專案搬家、刪除 `.venv`
  或換使用者後，必須更新其中的絕對 `Exec` 路徑並重建 KDE service cache。
- 不要同時啟動兩個桌面 Voice Client；它們共用同一個
  `$XDG_RUNTIME_DIR/voice-client-control.sock`。
- 音訊整合測試有三層：純 queue／mock、系統裝置可見、實際聽感；前兩層通過不代表第三層完成。
- `mobile_server.py` 尚未完全對齊桌面 Data Tunnel；修改共享元件時要檢查兩條入口。
- TTS 的 `config.ini [TTS].engine` 目前不代表所有後端都已實際接通，先核對 `text_to_voice.py`。
