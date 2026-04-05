import configparser
import json
import os
from datetime import datetime, timezone


class SessionManager:
    """會話管理器（同步呼叫）。管理對話串的建立、切換、列表與權限記憶。"""

    def __init__(self, config: configparser.ConfigParser):
        ws = config["WORKSPACE"]
        self._sessions_file = ws.get("sessions_file", "output/.sessions.json")
        self._permissions_file = ws.get("permissions_file", "output/.permissions.json")
        self._sessions: dict = {}
        self._permissions: dict = {}
        self._current_title: str | None = None
        self._load()

    # ── Persistence ────────────────────────────────────────────────────

    def _load(self):
        for path, attr in [
            (self._sessions_file, "_sessions"),
            (self._permissions_file, "_permissions"),
        ]:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    setattr(self, attr, json.load(f))

    def _save_sessions(self):
        with open(self._sessions_file, "w", encoding="utf-8") as f:
            json.dump(self._sessions, f, ensure_ascii=False, indent=2)

    def _save_permissions(self):
        with open(self._permissions_file, "w", encoding="utf-8") as f:
            json.dump(self._permissions, f, ensure_ascii=False, indent=2)

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
        return list(self._sessions.keys())

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

    # ── Permission operations ──────────────────────────────────────────

    def is_permitted(self, action: str) -> bool:
        return self._permissions.get(action) == "always"

    def set_permission(self, action: str, level: str):
        if level == "approved_always":
            self._permissions[action] = "always"
            self._save_permissions()
