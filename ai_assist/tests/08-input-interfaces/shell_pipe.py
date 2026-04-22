import sys
import time
from pathlib import Path

# 加入之前的非同步系統路徑
sys.path.append(str(Path(__file__).parent.parent / "07-async-orchestration"))
from async_system import AsyncSessionManager, AsyncOrchestrator

def main():
    # 初始化核心組件
    orchestrator = AsyncOrchestrator(max_workers=3)
    sm = AsyncSessionManager(orchestrator, storage_dir="./shell_sessions")

    print("=== [實驗] AI 助手 Shell 管道介面啟動 ===")
    print("提示：你可以直接輸入文字，或使用管道 (例如 echo 'hello' | python shell_pipe.py)")
    print("輸入 'exit' 退出。")

    # 檢查是否為管道輸入 (如: echo "task" | python shell_pipe.py)
    if not sys.stdin.isatty():
        for line in sys.stdin:
            content = line.strip()
            if content:
                print(f"[管道輸入] {content}")
                sm.append("shell_input", content, trigger=True)
        # 管道讀取完畢後等待一小段時間讓助手處理完畢
        time.sleep(2)
        sm.save_all()
        return

    # 交互式輸入
    try:
        while True:
            try:
                content = input(">> ").strip()
                if content.lower() == 'exit':
                    break
                if content:
                    sm.append("shell_input", content, trigger=True)
            except EOFError:
                break
    except KeyboardInterrupt:
        pass
    finally:
        print("\n正在儲存 Session 並退出...")
        sm.save_all()

if __name__ == "__main__":
    main()
