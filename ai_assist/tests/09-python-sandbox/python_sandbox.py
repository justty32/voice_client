import ast
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import List, Set
import logging

# 設定紀錄
logging.basicConfig(level=logging.INFO, format='[PythonSandbox] %(message)s')

class SecurityViolation(Exception):
    """當偵測到非法代碼行為時拋出"""
    pass

class PythonSandbox:
    def __init__(self, workspace_path: str):
        self.workspace = Path(workspace_path).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        
        # 核心安全設定：禁止的模組與函式
        self.FORBIDDEN_MODULES = {
            'socket', 'requests', 'urllib', 'http', 'smtplib', # 禁止網路
            'os', 'subprocess', 'shutil', 'sys', 'pathlib',    # 禁止直接系統操作
            'threading', 'multiprocessing', 'builtins'         # 禁止資源競爭
        }
        self.FORBIDDEN_FUNCTIONS = {
            'eval', 'exec', 'open', 'getattr', 'setattr', 'delattr', '__import__'
        }

    def _static_analysis(self, code: str):
        """
        使用抽象語法樹 (AST) 進行靜態掃描。
        在執行前攔截任何非法引用或危險函式。
        """
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            raise SecurityViolation(f"代碼語法錯誤: {e}")

        for node in ast.walk(tree):
            # 1. 檢查 import 語句
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name.split('.')[0] in self.FORBIDDEN_MODULES:
                        raise SecurityViolation(f"拒絕引用危險模組: {alias.name}")
            
            elif isinstance(node, ast.ImportFrom):
                if node.module and node.module.split('.')[0] in self.FORBIDDEN_MODULES:
                    raise SecurityViolation(f"拒絕引用危險模組: {node.module}")

            # 2. 檢查函式呼叫 (禁止 eval, exec, open 等)
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name):
                    if node.func.id in self.FORBIDDEN_FUNCTIONS:
                        raise SecurityViolation(f"拒絕使用危險函式: {node.func.id}")

        logging.info("靜態安全掃描通過。")

    def run_code(self, code: str, timeout: int = 5) -> str:
        """
        安全地執行 Python 代碼。
        """
        # 1. 執行靜態分析
        try:
            self._static_analysis(code)
        except SecurityViolation as e:
            return f"安全攔截: {str(e)}"

        # 2. 建立臨時執行檔 (在沙盒目錄內)
        with tempfile.NamedTemporaryFile(suffix=".py", dir=self.workspace, delete=False, mode='w', encoding='utf-8') as f:
            # 可以在這裡加入預定義的安全標頭，例如禁用特定功能
            f.write(code)
            temp_file_path = Path(f.name)

        try:
            # 3. 執行子程序
            # 我們禁用環境變數，並將執行路徑鎖定在工作目錄
            result = subprocess.run(
                [sys.executable, temp_file_path.name],
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=timeout,
                env={}, # 清空環境變數，防止洩漏系統資訊
            )
            
            if result.returncode == 0:
                return result.stdout if result.stdout else "代碼執行成功 (無輸出)。"
            else:
                return f"執行錯誤:\n{result.stderr}"

        except subprocess.TimeoutExpired:
            return "錯誤: 代碼執行超時 (可能存在無限迴圈)。"
        except Exception as e:
            return f"系統錯誤: {str(e)}"
        finally:
            # 4. 清理臨時檔案
            if temp_file_path.exists():
                temp_file_path.unlink()

# --- 測試與範例 ---
if __name__ == "__main__":
    print("=== [實驗] Python 安全沙盒測試啟動 ===")
    sandbox = PythonSandbox("./python_sandbox_lab")

    # 1. 測試正常計算代碼
    print("\n[測試 1] 正常代碼 (數學運算):")
    code1 = """
def fib(n):
    return n if n <= 1 else fib(n-1) + fib(n-2)
print(f'Fib(10) = {fib(10)}')
    """
    print(sandbox.run_code(code1))

    # 2. 測試危險模組攔截 (import socket)
    print("\n[測試 2] 安全攔截 (嘗試 import socket):")
    code2 = "import socket\ns = socket.socket()"
    print(sandbox.run_code(code2))

    # 3. 測試危險函式攔截 (eval)
    print("\n[測試 3] 安全攔截 (嘗試使用 eval):")
    code3 = "eval('print(123)')"
    print(sandbox.run_code(code3))

    # 4. 測試讀寫檔案攔截 (open)
    print("\n[測試 4] 安全攔截 (嘗試使用 open):")
    code4 = "with open('secret.txt', 'w') as f: f.write('data')"
    print(sandbox.run_code(code4))
    
    # 5. 測試超時攔截
    print("\n[測試 5] 超時攔截 (無限迴圈):")
    code5 = "while True: pass"
    print(sandbox.run_code(code5, timeout=2))

    print("\n=== 測試完成 ===")
