import time
import sys
import logging
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# 加入之前的非同步系統路徑
sys.path.append(str(Path(__file__).parent.parent / "07-async-orchestration"))
from async_system import AsyncSessionManager, AsyncOrchestrator

# 設定紀錄
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(message)s')

class TaskFileHandler(FileSystemEventHandler):
    """
    監控檔案系統事件的處理器。
    當有新檔案建立或內容變更時觸發。
    """
    def __init__(self, sm: AsyncSessionManager, target_session: str = "file_inbox"):
        self.sm = sm
        self.target_session = target_session

    def on_created(self, event):
        if not event.is_directory and event.src_path.endswith(('.txt', '.task')):
            self._process_file(event.src_path)

    def _process_file(self, file_path: str):
        path = Path(file_path)
        logging.info(f"偵測到新任務檔案: {path.name}")
        
        # 稍微等待檔案寫入完成
        time.sleep(0.1)
        
        try:
            content = path.read_text(encoding='utf-8').strip()
            if content:
                logging.info(f"將檔案內容加入 Session '{self.target_session}' 並觸發處理。")
                self.sm.append(self.target_session, content, trigger=True)
                
                # 處理完畢後，可以選擇將檔案移動到已完成目錄或刪除 (避免重複觸發)
                finished_dir = path.parent / "finished"
                finished_dir.mkdir(exist_ok=True)
                path.replace(finished_dir / path.name)
                logging.info(f"檔案已移至 '{finished_dir.name}' 目錄。")
        except Exception as e:
            logging.error(f"讀取檔案失敗: {e}")

def main():
    # 初始化核心組件
    orchestrator = AsyncOrchestrator(max_workers=3)
    sm = AsyncSessionManager(orchestrator, storage_dir="./file_watcher_sessions")

    # 設定監控目錄
    inbox_path = Path("./task_inbox")
    inbox_path.mkdir(exist_ok=True)
    
    # 啟動監控
    event_handler = TaskFileHandler(sm)
    observer = Observer()
    observer.schedule(event_handler, str(inbox_path), recursive=False)
    observer.start()

    print(f"=== [實驗] AI 助手檔案監控介面啟動 ===")
    print(f"監控目錄: {inbox_path.absolute()}")
    print("提示：你可以建立一個內容為 'Hello task' 的 .txt 檔案丟進去測試。")
    print("按下 Ctrl+C 停止監控。")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
        print("\n正在停止監控並退出...")
    
    observer.join()
    sm.save_all()

if __name__ == "__main__":
    # 注意：需安裝 watchdog 庫 (pip install watchdog)
    main()
