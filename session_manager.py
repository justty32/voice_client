import configparser
import json
import os
from datetime import datetime, timezone

from workspace import Workspace


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
            try:
                with open(self._sessions_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    
                # 如果是新格式：包含 last_used_title 和 sessions 鍵
                if isinstance(data, dict) and "sessions" in data:
                    self._sessions = data.get("sessions", {})
                    self._current_title = data.get("last_used_title")
                # 如果是舊格式：直接就是一個以 title 為鍵的 dict
                elif isinstance(data, dict):
                    self._sessions = data
                    self._current_title = None
                else:
                    self._sessions = {}
                    self._current_title = None
            except (json.JSONDecodeError, Exception):
                self._sessions = {}
                self._current_title = None
        
        # 將所有 session 的 history 遷移為新格式 [role, content, timestamp]
        for session in self._sessions.values():
            if isinstance(session, dict):
                self._migrate_history(session)

        # 再次確認恢復的 title 確實存在於列表中
        if self._current_title and self._current_title not in self._sessions:
            self._current_title = None

    @staticmethod
    def _migrate_history(session: dict):
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

    def _save_sessions(self):
        output = {
            "last_used_title": self._current_title,
            "sessions": self._sessions
        }
        with open(self._sessions_file, "w", encoding="utf-8") as f:
            json.dump(output, f, ensure_ascii=False, indent=2)

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
            self._save_sessions() # 切換時立即記住
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
            session["history"].append([
                str(role),
                str(content),
                datetime.now(timezone.utc).isoformat(),
            ])
            self._save_sessions()

    def message_count(self) -> int:
        """當前對話的訊息筆數。"""
        session = self.get_current_session()
        if session and isinstance(session.get("history"), list):
            return len(session["history"])
        return 0

    def clear_history(self) -> int:
        """清空當前對話的歷史，回傳被清除的筆數。"""
        session = self.get_current_session()
        if session is None:
            return 0
        n = len(session.get("history", []))
        session["history"] = []
        self._save_sessions()
        return n

    def _apply_history_op(self, op) -> bool:
        """以 Workspace 包裝當前對話歷史執行 op(ws)->bool，成功則寫回並存檔。"""
        session = self.get_current_session()
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

    def load_session_from_file(self, filename: str) -> tuple[bool, str]:
        """從 JSON 檔案載入對話，載入後自動切換。"""
        try:
            if not filename.lower().endswith(".json"):
                filename += ".json"
            
            # 如果只是檔名，從 output 目錄找
            if os.sep not in filename and "/" not in filename and "\\" not in filename:
                filename = os.path.join(os.path.dirname(self._sessions_file), filename)
            
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
        session = self.get_current_session()
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
