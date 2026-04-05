import configparser
import json
import os
from datetime import datetime, timezone


class SessionManager:
    """會話管理器（同步呼叫）。管理對話串的建立、切換、列表。"""

    def __init__(self, config: configparser.ConfigParser):
        ws = config["WORKSPACE"]
        self._sessions_file = ws.get("sessions_file", "output/.sessions.json")
        self._deleted_dir = ws.get("deleted_sessions_dir", "output/deleted")
        self._sessions: dict = {}
        self._current_title: str | None = None
        self._load()

    # ── Persistence ────────────────────────────────────────────────────

    def _load(self):
        os.makedirs(os.path.dirname(self._sessions_file), exist_ok=True)
        if os.path.exists(self._sessions_file):
            with open(self._sessions_file, "r", encoding="utf-8") as f:
                self._sessions = json.load(f)

    def _save_sessions(self):
        with open(self._sessions_file, "w", encoding="utf-8") as f:
            json.dump(self._sessions, f, ensure_ascii=False, indent=2)

    # ── Session operations ─────────────────────────────────────────────

    def new_session(self, title: str) -> dict:
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
        if title in self._sessions:
            self._current_title = title
            return True
        return False

    def list_sessions(self) -> list[str]:
        titles = []
        for title in self._sessions.keys():
            if title == self._current_title:
                titles.append(f"{title} (當前)")
            else:
                titles.append(title)
        return titles

    @property
    def current_title(self) -> str | None:
        return self._current_title

    def get_current_session(self) -> dict | None:
        if self._current_title:
            return self._sessions.get(self._current_title)
        return None

    def add_message(self, role: str, content: str):
        session = self.get_current_session()
        if session is not None:
            session["history"].append({
                "role": role,
                "content": content,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
            self._save_sessions()

    def delete_session(self, title: str) -> tuple[bool, str]:
        """刪除指定 Session，刪除前先備份至 output/deleted。"""
        if title == self._current_title:
            return False, "不能刪除當前正在使用的對話。"
        
        if title not in self._sessions:
            return False, f"找不到對話: {title}"
            
        # 備份
        try:
            os.makedirs(self._deleted_dir, exist_ok=True)
            # 建立檔名安全的 title
            safe_title = "".join(c for c in title if c.isalnum() or c in (" ", "-", "_")).strip()
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_path = os.path.join(self._deleted_dir, f"{safe_title}_{timestamp}.json")
            
            with open(backup_path, "w", encoding="utf-8") as f:
                json.dump(self._sessions[title], f, ensure_ascii=False, indent=2)
                
            # 刪除
            del self._sessions[title]
            self._save_sessions()
            return True, f"已刪除對話 {title}，備份存於 {backup_path}"
        except Exception as e:
            return False, f"刪除失敗: {e}"

    def save_session_to_file(self, filename: str | None = None) -> tuple[bool, str]:
        """將當前對話另存為 JSON 檔案。"""
        if not self._current_title or self._current_title not in self._sessions:
            return False, "目前沒有開啟對話。"
            
        try:
            if not filename:
                filename = self._current_title
            
            if not filename.lower().endswith(".json"):
                filename += ".json"
                
            # 如果只是檔名，存放在 output 目錄
            if os.sep not in filename and "/" not in filename and "\\" not in filename:
                filename = os.path.join(os.path.dirname(self._sessions_file), filename)
            
            os.makedirs(os.path.dirname(filename), exist_ok=True)
            with open(filename, "w", encoding="utf-8") as f:
                json.dump(self._sessions[self._current_title], f, ensure_ascii=False, indent=2)
            
            return True, f"對話已另存至: {filename}"
        except Exception as e:
            return False, f"儲存失敗: {e}"
