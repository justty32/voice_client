import sys
from pathlib import Path
import logging

# 引入組件
sys.path.append(str(Path(__file__).parent.parent / "02-session"))
from session_manager import SessionManager
from chain_manager import ChainManager, ChainContext

# 關閉細節紀錄以便看清楚輸出
logging.getLogger().setLevel(logging.WARNING)

def run_test():
    print("=== [實驗] 鏈條管理器與 Mod 系統啟動 ===")
    
    # 1. 初始化
    sm = SessionManager()
    # 建立管理器並指定 plugins 目錄
    plugins_dir = Path(__file__).parent / "plugins"
    manager = ChainManager(sm, str(plugins_dir))
    
    # 2. 載入 Mod (熱插拔測試)
    manager.load_plugins()
    print(f"目前共載入 {len(manager.chains)} 個鏈條處理器。")

    # 3. 測試簡單觸發
    print("\n--- 測試 1: 簡單觸發 (GreetingMod) ---")
    sm.append("user_input", "hello there!")
    
    # 4. 測試連鎖反應 (AutoTaskMod -> CalculationMod)
    print("\n--- 測試 2: 連鎖反應與深度限制 ---")
    # 我們在 AutoTaskMod 中會觸發 internal_logic，
    # 這會進一步觸發 CalculationMod，形成一條連鎖鏈。
    sm.append("user_input", "please start a task")

    # 5. 檢查最終 Session 狀態
    print("\n--- 最終 Session 內容 ---")
    for sid in sm.list_sessions():
        print(f"Session '{sid}': {sm.get_session(sid)}")

if __name__ == "__main__":
    run_test()
