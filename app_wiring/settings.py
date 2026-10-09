"""app_wiring/settings.py — 桌面與手機入口共用的設定解讀。

純函式：除了 `ensure_default_session()` 會經 SessionManager 落盤之外，不做其他 I/O。
各函式與原本散在 `app.py:main()`、`mobile/state.py` 的寫法逐字等價。
"""

import os


def ensure_default_session(sm) -> None:
    """若尚無目前對話，切到 "default"；不存在則建立。"""
    if not sm.current_title:
        if not sm.switch_session("default"):
            sm.new_session("default")


def export_dir_from(config) -> str:
    """`[WORKSPACE] export_file` 的所在目錄；無目錄部分時回傳 "."。"""
    return (
        os.path.dirname(config.get("WORKSPACE", "export_file", fallback="output/export.json"))
        or "."
    )


def slm_settings(config) -> tuple[int, bool]:
    """回傳 `(summary_threshold, enabled)`；`[SLM]` 缺節或缺鍵時為 `(20, True)`。"""
    return (
        config.getint("SLM", "summary_threshold", fallback=20),
        config.getboolean("SLM", "enabled", fallback=False),
    )
