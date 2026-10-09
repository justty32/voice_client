"""domain/session_manager.py — 多對話管理（狀態與鎖）；檔案格式與 I/O helper 在 domain/session_io.py。"""

import configparser
import copy
import json
import logging
import os
import threading
from datetime import datetime, timezone

from domain import session_io
from domain.workspace import Workspace

log = logging.getLogger(__name__)


class SessionManager:
    """會話管理器（同步呼叫）。管理對話串的建立、切換、列表。

    執行緒安全：CommandRouter、ChatFlow、HttpClient 會從不同執行緒直接呼叫，
    所有公開方法在 self._lock（RLock，允許內部互呼）內執行；sessions 檔以
    暫存檔＋os.replace 原子寫入。
    """

    def __init__(self, config: configparser.ConfigParser):
        ws = config["WORKSPACE"]
        self._sessions_file = ws.get("sessions_file", "output/.sessions.json")
        self._deleted_dir = ws.get("deleted_sessions_dir", "output/deleted")
        self._sessions: dict = {}
        self._current_title: str | None = None
        self._lock = threading.RLock()
        self._load()

    # ── Persistence ────────────────────────────────────────────────────

    def _load(self):
        os.makedirs(os.path.dirname(self._sessions_file), exist_ok=True)
        if os.path.exists(self._sessions_file):
            try:
                with open(self._sessions_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                # 新格式含 last_used_title 與 sessions 鍵；舊格式直接以 title 為鍵
                self._sessions, self._current_title = session_io.parse_sessions_data(data)
            except (json.JSONDecodeError, Exception) as exc:
                self._backup_corrupt_file(exc)
                self._sessions = {}
                self._current_title = None
        
        # 將所有 session 的 history 遷移為新格式 [role, content, timestamp]
        for session in self._sessions.values():
            if isinstance(session, dict):
                self._migrate_history(session)

        # 再次確認恢復的 title 確實存在於列表中
        if self._current_title and self._current_title not in self._sessions:
            self._current_title = None

    def _backup_corrupt_file(self, exc: Exception) -> None:
        """sessions 檔無法解析時，先改名備份為 .corrupt-<時間戳> 再以空集合啟動；不刪任何檔。"""
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup = f"{self._sessions_file}.corrupt-{stamp}"
        try:
            os.replace(self._sessions_file, backup)
            log.error("sessions 檔損毀（%s），已備份為 %s，以空對話集合啟動。", exc, backup)
        except OSError as move_exc:
            log.error("sessions 檔損毀（%s），且備份失敗（%s），以空對話集合啟動。", exc, move_exc)

    @staticmethod
    def _migrate_history(session: dict):
        """把 history 正規化為 [role, content, timestamp]；實作見 session_io.migrate_history。"""
        session_io.migrate_history(session)

    def _save_sessions(self):
        """原子寫入：先寫暫存檔，再以 os.replace 取代正式檔，避免寫到一半留下壞檔。"""
        with self._lock:
            session_io.write_sessions_atomic(self._sessions_file, self._sessions, self._current_title)

    def _current(self) -> dict | None:
        """內部用：回傳當前對話的內部 dict 參照（呼叫端須已持有鎖）。"""
        if self._current_title:
            return self._sessions.get(self._current_title)
        return None

    # ── Session operations ─────────────────────────────────────────────

    def new_session(self, title: str) -> dict | None:
        """建立並切換到新對話；同名對話已存在時回 None 且不改任何狀態（不覆蓋）。"""
        with self._lock:
            if title in self._sessions:
                return None
            session = {
                "title": title,
                "created_at": datetime.now(timezone.utc).isoformat(),
                "history": [],
            }
            self._sessions[title] = session
            self._current_title = title
            self._save_sessions()
            return session

    def switch_session(self, title: str) -> bool:
        with self._lock:
            if title in self._sessions:
                self._current_title = title
                self._save_sessions() # 切換時立即記住
                return True
            return False

    def list_sessions(self) -> list[str]:
        with self._lock:
            titles = []
            for title in self._sessions.keys():
                if title == self._current_title:
                    titles.append(f"{title} (當前)")
                else:
                    titles.append(title)
            return titles

    @property
    def current_title(self) -> str | None:
        with self._lock:
            return self._current_title

    def next_auto_title(self, prefix: str = "session_") -> str:
        """回傳第一個未被使用的自動標題 session_N（N 從 1 起）。"""
        with self._lock:
            n = 1
            while f"{prefix}{n}" in self._sessions:
                n += 1
            return f"{prefix}{n}"

    def get_current_session(self) -> dict | None:
        """回傳當前對話的深複本；修改回傳值不影響內部狀態。"""
        with self._lock:
            session = self._current()
            return copy.deepcopy(session) if session is not None else None

    def add_message(self, role: str, content: str):
        with self._lock:
            session = self._current()
            if session is not None:
                session["history"].append([
                    str(role),
                    str(content),
                    datetime.now(timezone.utc).isoformat(),
                ])
                self._save_sessions()

    def message_count(self) -> int:
        """當前對話的訊息筆數。"""
        with self._lock:
            session = self._current()
            if session and isinstance(session.get("history"), list):
                return len(session["history"])
            return 0

    def clear_history(self) -> int:
        """清空當前對話的歷史，回傳被清除的筆數。"""
        with self._lock:
            session = self._current()
            if session is None:
                return 0
            n = len(session.get("history", []))
            session["history"] = []
            self._save_sessions()
            return n

    def _apply_history_op(self, op) -> bool:
        """以 Workspace 包裝當前對話歷史執行 op(ws)->bool，成功則寫回並存檔。"""
        with self._lock:
            session = self._current()
            if session is None:
                return False
            ws = Workspace.from_list("chat", session.get("history", []))
            if op(ws):
                session["history"] = ws.to_list()
                self._save_sessions()
                return True
            return False

    def delete_message(self, idx: int) -> bool:
        """刪除當前對話第 idx 則訊息（0-based）。"""
        return self._apply_history_op(lambda ws: ws.delete(idx))

    def move_message(self, src: int, dst: int) -> bool:
        """把當前對話第 src 則訊息移到第 dst 位（0-based）。"""
        return self._apply_history_op(lambda ws: ws.move(src, dst))

    def move_message_to_top(self, idx: int = -1) -> bool:
        """把當前對話指定訊息移到最前；idx 預設 -1 為最後一則。"""
        return self._apply_history_op(lambda ws: ws.move_to_top(idx))

    def delete_session(self, title: str) -> tuple[bool, str]:
        """刪除指定 Session，刪除前先備份至 output/deleted。"""
        with self._lock:
            if title == self._current_title:
                return False, "不能刪除當前正在使用的對話。"

            if title not in self._sessions:
                return False, f"找不到對話: {title}"

            # 備份
            try:
                os.makedirs(self._deleted_dir, exist_ok=True)
                backup_path = session_io.deleted_backup_path(self._deleted_dir, title)
                session_io.write_json(backup_path, self._sessions[title])

                # 刪除
                del self._sessions[title]
                self._save_sessions()
                return True, f"已刪除對話 {title}，備份存於 {backup_path}"
            except Exception as e:
                return False, f"刪除失敗: {e}"

    def save_session_to_file(self, filename: str | None = None) -> tuple[bool, str]:
        """將當前對話另存為 JSON 檔案。"""
        with self._lock:
            if not self._current_title or self._current_title not in self._sessions:
                return False, "目前沒有開啟對話。"

            try:
                if not filename:
                    filename = self._current_title
                # 只給檔名時存放在 output 目錄
                filename = session_io.resolve_session_path(filename, self._sessions_file)

                os.makedirs(os.path.dirname(filename), exist_ok=True)
                session_io.write_json(filename, self._sessions[self._current_title])

                return True, f"對話已另存至: {filename}"
            except Exception as e:
                return False, f"儲存失敗: {e}"

    def load_session_from_file(self, filename: str) -> tuple[bool, str]:
        """從 JSON 檔案載入對話，載入後自動切換。"""
        with self._lock:
            try:
                # 只給檔名時從 output 目錄找
                filename = session_io.resolve_session_path(filename, self._sessions_file)

                if not os.path.exists(filename):
                    return False, f"找不到檔案: {filename}"

                with open(filename, "r", encoding="utf-8") as f:
                    session_data = json.load(f)

                title = session_data.get("title")
                if not title:
                    return False, "檔案格式不正確，找不到 title 欄位。"

                if title in self._sessions:
                    return False, f"當前已存在同名對話: {title}，請先使用 /rename 指令更改現有對話名稱。"

                # 載入的檔案可能是舊格式，遷移 history
                self._migrate_history(session_data)
                self._sessions[title] = session_data
                self._current_title = title
                self._save_sessions()
                return True, f"已從 {filename} 載入並切換至對話: {title}"
            except Exception as e:
                return False, f"載入失敗: {e}"

    def rename_session(self, old_title: str, new_title: str) -> tuple[bool, str]:
        """更改對話名稱。"""
        with self._lock:
            if old_title not in self._sessions:
                return False, f"找不到對話: {old_title}"

            if new_title in self._sessions:
                return False, f"新名稱 {new_title} 已被使用。"

            session = self._sessions.pop(old_title)
            session["title"] = new_title
            self._sessions[new_title] = session

            if self._current_title == old_title:
                self._current_title = new_title

            self._save_sessions()
            return True, f"對話已從 {old_title} 重命名為 {new_title}"

    def get_history(self) -> str:
        """獲取當前對話的歷史紀錄字串。"""
        with self._lock:
            return session_io.format_history(self._current())
