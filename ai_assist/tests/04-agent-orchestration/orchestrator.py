import sys
import os
from pathlib import Path

# 將上層目錄加入 path 以便引入之前的組件 (實務上建議使用 package 結構)
sys.path.append(str(Path(__file__).parent.parent / "02-session"))
sys.path.append(str(Path(__file__).parent.parent / "03-atomic-tools"))

from session_manager import SessionManager
from atomic_tools import AtomicTools

class AgentOrchestrator:
    def __init__(self, workspace_path: str):
        # 初始化工具箱與沙盒
        self.tools = AtomicTools(workspace_path)
        # 初始化 Session 管理器
        self.session_manager = SessionManager()
        
        # 註冊被動觸發監聽器
        self.session_manager.subscribe(self.handle_event)
        
    def handle_event(self, session_id: str, content: str, sm: SessionManager):
        """
        被動觸發處理鏈條：
        當任何 Session 有變動時，此函式會被調用。
        """
        # 避免助手回應後觸發無限迴圈 (只處理使用者輸入的 Session)
        if session_id != "user_input":
            return

        print(f"\n[事件偵測] Session: {session_id} | 內容: {content}")
        
        # 1. 意圖解析 (目前使用簡單關鍵字，未來對接 10B 模型)
        intent = self._simple_intent_parser(content)
        
        if intent == "list_files":
            print("-> 觸發任務: 列出檔案")
            result = self.tools.execute_shell("ls")
            sm.append("assistant_output", f"目錄列表結果:\n{result}")
            
        elif intent == "create_file":
            print("-> 觸發任務: 建立檔案")
            # 簡單解析檔案名稱，例如 "create file test.txt"
            filename = content.split()[-1] if len(content.split()) > 2 else "new_file.txt"
            result = self.tools.write_file(filename, "由 AI 助手自動生成的內容。")
            sm.append("assistant_output", result)
            
        elif intent == "unknown":
            print("-> 未知意圖，保持靜默或請求更高級推理。")
            # sm.append("assistant_output", "我不明白您的意思，請嘗試 'list files'。")

    def _simple_intent_parser(self, text: str) -> str:
        """模擬 10B 模型的意圖識別邏輯"""
        text = text.lower()
        if "list files" in text or "ls" == text.strip():
            return "list_files"
        if "create file" in text:
            return "create_file"
        return "unknown"

# --- 測試自動化觸發鏈條 ---
if __name__ == "__main__":
    print("=== AI 助手協調器 (Orchestrator) 測試開始 ===")
    
    # 建立協調器，工作目錄設定為 agent_lab
    orchestrator = AgentOrchestrator("./agent_lab")
    sm = orchestrator.session_manager

    # 模擬使用者動作：將字串放入 Session
    print("\n[動作] 使用者輸入: 'list files'")
    sm.append("user_input", "list files")
    
    print("\n[動作] 使用者輸入: 'create file agent_note.txt'")
    sm.append("user_input", "create file agent_note.txt")

    # 再次列出檔案看看是否成功建立
    print("\n[動作] 使用者輸入: 'ls'")
    sm.append("user_input", "ls")

    print("\n=== 最終 Session 狀態檢查 ===")
    print(f"使用者輸入紀錄: {sm.get_session('user_input')}")
    print(f"助手回應紀錄: {sm.get_session('assistant_output')}")
