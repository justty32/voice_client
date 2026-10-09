"""domain/session_io.py — SessionManager 的持久化與檔案格式 helper（純函式，不持鎖）。

鎖、目前對話狀態與錯誤記錄留在 `domain/session_manager.py`；本檔只負責
sessions 檔格式解讀、history 正規化、原子寫入、匯出入路徑解析與歷史文字格式。
"""

import json
import os
from datetime import datetime


def parse_sessions_data(data) -> tuple[dict, str | None]:
    """解讀 sessions 檔內容，回傳 (sessions, last_used_title)。

    新格式：{"last_used_title": ..., "sessions": {...}}；舊格式：直接以 title 為鍵的 dict；
    其它型別視為空集合。
    """
    if isinstance(data, dict) and "sessions" in data:
        return data.get("sessions", {}), data.get("last_used_title")
    if isinstance(data, dict):
        return data, None
    return {}, None


def migrate_history(session: dict) -> None:
    """把 history 正規化為 List[List[str]]（每筆 [role, content, timestamp]）。

    相容舊格式：history 內為 {role, content, timestamp} 的 dict。
    """
    hist = session.get("history")
    if not isinstance(hist, list):
        session["history"] = []
        return
    migrated: list[list[str]] = []
    for item in hist:
        if isinstance(item, dict):
            migrated.append([
                str(item.get("role", "")),
                str(item.get("content", "")),
                str(item.get("timestamp", "")),
            ])
        elif isinstance(item, (list, tuple)):
            role = str(item[0]) if len(item) > 0 else ""
            content = str(item[1]) if len(item) > 1 else ""
            ts = str(item[2]) if len(item) > 2 else ""
            migrated.append([role, content, ts])
        # 其它型別略過
    session["history"] = migrated


def write_sessions_atomic(path: str, sessions: dict, current_title: str | None) -> None:
    """原子寫入：先寫暫存檔，再以 os.replace 取代正式檔，避免寫到一半留下壞檔。"""
    output = {
        "last_used_title": current_title,
        "sessions": sessions,
    }
    tmp = f"{path}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def write_json(path: str, obj) -> None:
    """以 UTF-8、縮排 2 寫出 JSON（刪除備份與另存對話共用）。"""
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)


def deleted_backup_path(deleted_dir: str, title: str) -> str:
    """刪除前備份檔路徑：<deleted_dir>/<檔名安全的 title>_<時間戳>.json。"""
    safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return os.path.join(deleted_dir, f"{safe_title}_{timestamp}.json")


def resolve_session_path(filename: str, sessions_file: str) -> str:
    """補上 .json 副檔名；只給檔名（不含路徑分隔）時放在 sessions 檔所在目錄。"""
    if not filename.lower().endswith(".json"):
        filename += ".json"
    if os.sep not in filename and "/" not in filename and "\\" not in filename:
        filename = os.path.join(os.path.dirname(sessions_file), filename)
    return filename


def format_history(session: dict | None) -> str:
    """把對話歷史排成 /history 顯示用的文字。"""
    if not session or not session.get("history"):
        return "目前沒有對話歷史。"

    lines = [f"--- 對話歷史: {session['title']} ---"]
    for msg in session["history"]:
        role = msg[0] if len(msg) > 0 else "unknown"
        content = msg[1] if len(msg) > 1 else ""

        if role == "user":
            prefix = "用戶說："
        elif role == "assistant":
            prefix = "AI回覆："
        else:
            prefix = f"[{role}] "

        lines.append(f"{prefix}{content}")
    return "\n".join(lines)
