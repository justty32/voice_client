from typing import List, Dict, Callable, Any
import logging

# 設定簡易紀錄
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

class SessionManager:
    """
    管理多個 Session (字串陣列) 並處理觸發事件的核心類別。
    """
    def __init__(self):
        # 儲存結構: { session_id: [str1, str2, ...] }
        self._sessions: Dict[str, List[str]] = {}
        # 監聽器: 每當有新字串加入，會通知這些回呼函式
        self._listeners: List[Callable[[str, str, 'SessionManager'], None]] = []

    def create_session(self, session_id: str):
        """建立一個新的 Session"""
        if session_id not in self._sessions:
            self._sessions[session_id] = []
            logging.info(f"建立新 Session: {session_id}")

    def append(self, session_id: str, content: str):
        """向指定的 Session 加入新字串，並觸發監聽器"""
        if session_id not in self._sessions:
            self.create_session(session_id)
        
        self._sessions[session_id].append(content)
        logging.info(f"Session '{session_id}' 新增內容: {content[:50]}...")
        
        # 觸發所有監聽器
        self._notify(session_id, content)

    def get_session(self, session_id: str) -> List[str]:
        """讀取特定 Session 的完整歷史紀錄"""
        return self._sessions.get(session_id, [])

    def list_sessions(self) -> List[str]:
        """列出目前所有的 Session ID"""
        return list(self._sessions.keys())

    def subscribe(self, callback: Callable[[str, str, 'SessionManager'], None]):
        """註冊一個監聽器。當任何 Session 有變動時，呼叫該函式。"""
        self._listeners.append(callback)

    def _notify(self, session_id: str, new_content: str):
        """執行所有註冊的處理邏輯"""
        for listener in self._listeners:
            try:
                # 傳遞: 觸發的 ID、新的內容、以及管理器本身 (以便讀取其他 Session)
                listener(session_id, new_content, self)
            except Exception as e:
                logging.error(f"監聽器執行失敗: {e}")

# --- 測試與範例 ---
if __name__ == "__main__":
    manager = SessionManager()

    # 定義一個簡單的 AI 助手處理邏輯
    def simple_agent_callback(trigger_id: str, content: str, sm: SessionManager):
        print(f"\n[AI 助手被觸發] 觸發來源: {trigger_id}")
        
        if trigger_id == "user_input":
            print(f"-> 正在處理使用者輸入: '{content}'")
            
            # 關鍵功能：讀取另一個 Session (例如系統日誌) 的內容
            logs = sm.get_session("system_logs")
            print(f"-> 檢查系統日誌背景 (共 {len(logs)} 筆資料)...")
            
            if "ERROR" in "".join(logs):
                print("-> [警告] 偵測到系統日誌中有錯誤，助手將優先處理修復任務。")
            
            # 模擬處理後產出到另一個 Session
            sm.append("assistant_response", f"已收到您的指令: {content}。目前系統狀況良好。")

    # 註冊處理器
    manager.subscribe(simple_agent_callback)

    # 模擬工作流
    print("--- 模擬工作流開始 ---")
    
    # 1. 系統產生一些背景日誌
    manager.append("system_logs", "INFO: 系統啟動中...")
    manager.append("system_logs", "ERROR: 找不到數據庫連線。") # 埋入一個錯誤
    
    # 2. 使用者輸入指令
    manager.append("user_input", "請幫我備份資料夾。")
    
    print("\n--- 檢查助手回應 Session ---")
    print(manager.get_session("assistant_response"))
