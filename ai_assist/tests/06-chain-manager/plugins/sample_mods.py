import sys
from pathlib import Path

# 加入必要的路徑
sys.path.append(str(Path(__file__).parent.parent))

from chain_manager import BaseChain, ChainContext
from session_manager import SessionManager

class GreetingMod(BaseChain):
    """一個簡單的問候 Mod"""
    def should_trigger(self, session_id: str, content: str) -> bool:
        # 當使用者輸入包含 "hello" 時觸發
        return session_id == "user_input" and "hello" in content.lower()

    def process(self, session_id: str, content: str, sm: SessionManager, context: ChainContext):
        print(f"[{self.name()}] 偵測到問候語，準備回覆...")
        sm.append("assistant_output", "你好！我是你的 AI 助手。很高興見到你。")

class AutoTaskMod(BaseChain):
    """一個會產生連鎖反應的 Mod"""
    def should_trigger(self, session_id: str, content: str) -> bool:
        # 當使用者輸入包含 "task" 時觸發
        return session_id == "user_input" and "task" in content.lower()

    def process(self, session_id: str, content: str, sm: SessionManager, context: ChainContext):
        print(f"[{self.name()}] 偵測到任務請求，正在建立工作鏈...")
        # 模擬產生新字串，這可能會觸發其他鏈條
        sm.append("internal_logic", "START_CALCULATION")

class CalculationMod(BaseChain):
    """處理內部邏輯的 Mod"""
    def should_trigger(self, session_id: str, content: str) -> bool:
        return session_id == "internal_logic" and content == "START_CALCULATION"

    def process(self, session_id: str, content: str, sm: SessionManager, context: ChainContext):
        print(f"[{self.name()}] 執行複雜計算中...")
        import time
        time.sleep(0.05) # 模擬耗時操作
        sm.append("assistant_output", "計算任務已完成。")
