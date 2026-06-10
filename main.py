"""
main.py — Voice Client 啟動薄殼（資料隧道架構）

此檔案僅作為使用者熟悉的啟動入口點存在。
所有實際邏輯（接線、模組建構、主迴圈）均已移至 app.py。

啟動方式不變：
    python main.py
"""

from app import main

if __name__ == "__main__":
    main()
