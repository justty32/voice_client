import time
import inspect
import importlib.util
import os
from pathlib import Path
from typing import List, Dict, Any, Optional, Callable
import logging

# 基礎 Session Manager 引入 (假設在同級或上級目錄)
import sys
sys.path.append(str(Path(__file__).parent.parent / "02-session"))
from session_manager import SessionManager

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(message)s')

class ChainContext:
    """傳遞給鏈條的上下文資訊，包含資源統計"""
    def __init__(self, max_depth: int = 10):
        self.depth = 0
        self.max_depth = max_depth
        self.start_time = time.time()
        self.execution_stats = [] # 儲存每一層的耗時

class BaseChain:
    """Mod 作者必須繼承的基類"""
    def name(self) -> str:
        return self.__class__.__name__

    def should_trigger(self, session_id: str, content: str) -> bool:
        """判斷是否要觸發此鏈條"""
        return False

    def process(self, session_id: str, content: str, sm: SessionManager, context: ChainContext):
        """實際的處理邏輯"""
        pass

class ChainManager:
    def __init__(self, session_manager: SessionManager, plugins_dir: str):
        self.sm = session_manager
        self.plugins_dir = Path(plugins_dir)
        self.chains: List[BaseChain] = []
        self.max_call_depth = 5 # 限制連鎖反應的深度
        
        if not self.plugins_dir.exists():
            self.plugins_dir.mkdir(parents=True)

        # 監聽 Session 變動
        self.sm.subscribe(self.on_session_update)

    def load_plugins(self):
        """動態載入 plugins 目錄下的所有 .py 檔案作為鏈條"""
        self.chains = []
        for file in self.plugins_dir.glob("*.py"):
            if file.name == "__init__.py": continue
            
            spec = importlib.util.spec_from_file_location(file.stem, file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            
            # 尋找繼承自 BaseChain 的類別
            for name, obj in inspect.getmembers(module):
                if inspect.isclass(obj) and issubclass(obj, BaseChain) and obj is not BaseChain:
                    self.chains.append(obj())
                    logging.info(f"成功載入鏈條 Mod: {name} (來自 {file.name})")

    def on_session_update(self, session_id: str, content: str, sm: SessionManager):
        """當 Session 更新時，啟動調度流程"""
        # 建立一個初始上下文
        context = ChainContext(max_depth=self.max_call_depth)
        self._dispatch(session_id, content, context)

    def _dispatch(self, session_id: str, content: str, context: ChainContext):
        """內部的調度邏輯，支援遞迴呼叫限制"""
        if context.depth >= context.max_depth:
            logging.warning(f"!!! 達到最大呼叫深度 ({context.max_depth})，停止連鎖反應 !!!")
            return

        for chain in self.chains:
            if chain.should_trigger(session_id, content):
                start = time.time()
                context.depth += 1
                
                logging.info(f" [Depth {context.depth}] 啟動鏈條: {chain.name()}")
                
                try:
                    # 執行鏈條邏輯
                    chain.process(session_id, content, self.sm, context)
                except Exception as e:
                    logging.error(f"鏈條 {chain.name()} 執行出錯: {e}")
                
                elapsed = time.time() - start
                context.execution_stats.append({
                    "chain": chain.name(),
                    "depth": context.depth,
                    "time_ms": elapsed * 1000
                })
                
                # 減少深度，以便同層的其他鏈條繼續
                context.depth -= 1

    def print_report(self, context: ChainContext):
        """列印本次觸發的資源統計報告"""
        print("\n=== 鏈條執行資源統計報告 ===")
        total_time = (time.time() - context.start_time) * 1000
        for stat in context.execution_stats:
            print(f"- {stat['chain']} (D{stat['depth']}): {stat['time_ms']:.2f} ms")
        print(f"總執行時間: {total_time:.2f} ms")
        print("============================\n")
