"""app_wiring — app.py 的拆分子模組（純接線層輔助）。

- topology.py：wire()，把所有模組登錄進 Exchange
- ui_events.py：ui_event dict → UiEvent 轉換
- assembly.py：build_core() 核心組裝、Lifecycle 啟停註冊表
- settings.py：桌面／手機共用的設定解讀

對外入口仍是 `app`（`from app import main, wire, _dict_to_ui_event`）。
"""
