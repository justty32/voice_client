import os
from pathlib import Path
from typing import Union

class SandboxError(Exception):
    """當嘗試進行非法路徑操作時拋出的異常"""
    pass

class SafeSandbox:
    def __init__(self, root_path: Union[str, Path]):
        # 確保 root_path 是絕對路徑
        self.root = Path(root_path).resolve()
        if not self.root.exists():
            self.root.mkdir(parents=True, exist_ok=True)
            
    def _safe_path(self, target_path: Union[str, Path]) -> Path:
        """
        驗證目標路徑是否位於沙盒目錄內。
        如果是，返回解析後的絕對路徑；否則拋出 SandboxError。
        """
        try:
            # resolve() 會處理所有的 '..' 並返回絕對路徑
            resolved_path = (self.root / target_path).resolve()
            
            # 檢查解析後的路徑是否以沙盒根目錄開頭
            if not str(resolved_path).startswith(str(self.root)):
                raise SandboxError(f"非法路徑嘗試: {target_path} 試圖越過沙盒邊界")
            
            return resolved_path
        except Exception as e:
            raise SandboxError(f"路徑驗證失敗: {str(e)}")

    def read_text(self, file_path: str) -> str:
        """安全地讀取文字檔"""
        target = self._safe_path(file_path)
        if not target.is_file():
            raise FileNotFoundError(f"找不到檔案: {file_path}")
        return target.read_text(encoding='utf-8')

    def write_text(self, file_path: str, content: str):
        """安全地寫入文字檔"""
        target = self._safe_path(file_path)
        # 確保父目錄存在
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding='utf-8')

    def list_dir(self, sub_dir: str = ".") -> list:
        """安全地列出目錄內容"""
        target = self._safe_path(sub_dir)
        if not target.is_dir():
            raise NotADirectoryError(f"不是目錄: {sub_dir}")
        return [p.name for p in target.iterdir()]

    def delete_file(self, file_path: str):
        """安全地刪除檔案"""
        target = self._safe_path(file_path)
        if target.is_file():
            target.unlink()
        elif target.exists():
            raise SandboxError(f"無法刪除: {file_path} 不是檔案")

if __name__ == "__main__":
    # 簡單的單元測試
    print("--- 開始沙盒安全性測試 ---")
    sandbox_root = Path("./test_workspace")
    sb = SafeSandbox(sandbox_root)
    
    # 1. 正常操作測試
    print("測試 1: 寫入與讀取檔案...")
    sb.write_text("hello.txt", "你好，沙盒！")
    content = sb.read_text("hello.txt")
    print(f"讀取內容: {content}")
    
    # 2. 越界攻擊測試
    print("\n測試 2: 越界路徑攻擊 (../../secret.txt)...")
    try:
        sb.read_text("../../secret.txt")
    except SandboxError as e:
        print(f"成功攔截攻擊: {e}")
        
    # 3. 子目錄操作測試
    print("\n測試 3: 子目錄隔離測試...")
    sb.write_text("logs/app.log", "Log data")
    print(f"目錄內容: {sb.list_dir('.')}")
    print(f"logs 目錄內容: {sb.list_dir('logs')}")
    
    print("\n--- 測試完成 ---")
