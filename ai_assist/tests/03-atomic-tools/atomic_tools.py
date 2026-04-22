import subprocess
import shlex
import os
from pathlib import Path
from typing import List, Optional
import logging

# 引入先前的沙盒邏輯 (為了測試獨立性，這裡直接整合核心邏輯)
class SandboxError(Exception):
    pass

class AtomicTools:
    """
    AI 助手的工具箱：包含沙盒檔案操作與受限 Shell 指令。
    """
    def __init__(self, workspace_path: str):
        self.workspace = Path(workspace_path).resolve()
        if not self.workspace.exists():
            self.workspace.mkdir(parents=True, exist_ok=True)
            
        # 定義允許的 Shell 指令白名單
        self.ALLOWED_COMMANDS = {'ls', 'rm', 'mv', 'touch', 'mkdir', 'grep', 'cat', 'cp'}

    def _validate_path(self, target_path: str) -> Path:
        """驗證路徑是否在沙盒內"""
        try:
            # 處理相對於工作目錄的路徑
            full_path = (self.workspace / target_path).resolve()
            if not str(full_path).startswith(str(self.workspace)):
                raise SandboxError(f"安全攔截：路徑 '{target_path}' 超出工作目錄範圍。")
            return full_path
        except Exception as e:
            raise SandboxError(f"路徑驗證失敗: {e}")

    # --- 檔案 CRUD 操作 ---
    
    def read_file(self, path: str) -> str:
        """讀取檔案內容"""
        target = self._validate_path(path)
        if not target.is_file():
            raise FileNotFoundError(f"找不到檔案: {path}")
        return target.read_text(encoding='utf-8')

    def write_file(self, path: str, content: str):
        """寫入檔案內容"""
        target = self._validate_path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')
        return f"成功寫入檔案: {path}"

    def delete_file(self, path: str):
        """刪除檔案"""
        target = self._validate_path(path)
        if target.is_file():
            target.unlink()
            return f"成功刪除檔案: {path}"
        raise FileNotFoundError(f"找不到可刪除的檔案: {path}")

    # --- 受限 Shell 指令執行 ---

    def execute_shell(self, cmd_line: str) -> str:
        """
        執行受限的 Shell 指令。
        格式範例: "ls -la", "grep 'pattern' file.txt"
        """
        try:
            # 使用 shlex 解析指令字串，避免簡單分割造成的安全問題
            args = shlex.split(cmd_line)
            if not args:
                return "無效的指令"

            main_cmd = args[0]
            
            # 1. 檢查指令是否在白名單內
            if main_cmd not in self.ALLOWED_COMMANDS:
                return f"拒絕執行：指令 '{main_cmd}' 不在允許的清單內 ({', '.join(self.ALLOWED_COMMANDS)})。"

            # 2. 針對指令中的路徑進行安全檢查 (簡單檢查所有參數)
            # 注意：這裡是一個基礎的防護，實務上可能需要更精密的參數解析
            for arg in args[1:]:
                if arg.startswith('-'): continue # 跳過旗標
                if '/' in arg or '\\' in arg or '..' in arg:
                    self._validate_path(arg) # 驗證路徑安全性

            # 3. 執行指令，設定 cwd 為沙盒根目錄
            result = subprocess.run(
                args,
                cwd=self.workspace,
                capture_output=True,
                text=True,
                timeout=10, # 設定超時防止掛起
                shell=False # 禁用 shell=True 以增加安全性
            )
            
            if result.returncode == 0:
                return result.stdout if result.stdout else "指令執行成功 (無輸出)。"
            else:
                return f"指令執行失敗: {result.stderr}"

        except Exception as e:
            return f"系統錯誤: {str(e)}"

# --- 測試與示範 ---
if __name__ == "__main__":
    print("=== 原子工具測試開始 ===")
    tools = AtomicTools("./agent_workspace")

    # 1. 測試檔案寫入與讀取
    print("\n[測試] 檔案操作:")
    print(tools.write_file("test.txt", "這是一行測試文字。\nAI 助手正在運作。"))
    print(f"讀取內容:\n{tools.read_file('test.txt')}")

    # 2. 測試受限 Shell 指令
    print("\n[測試] Shell 指令 (ls):")
    print(tools.execute_shell("ls -l"))

    print("\n[測試] Shell 指令 (mkdir):")
    print(tools.execute_shell("mkdir sub_folder"))
    print(tools.execute_shell("ls -F"))

    # 3. 測試安全性攔截
    print("\n[測試] 安全攔截 (嘗試讀取父目錄):")
    try:
        tools.read_file("../secret.txt")
    except SandboxError as e:
        print(f"檔案操作攔截成功: {e}")

    print("\n[測試] 安全攔截 (嘗試執行危險指令):")
    print(tools.execute_shell("rm -rf /")) # 雖然有 rm，但會被路徑驗證或權限擋下
    print(tools.execute_shell("ping google.com")) # 不在白名單

    print("\n=== 測試完成 ===")
