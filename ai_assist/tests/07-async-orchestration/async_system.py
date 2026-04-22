import threading
import time
import queue
import logging
import json
import atexit
from concurrent.futures import ThreadPoolExecutor
from typing import List, Dict, Callable, Optional, Any
from pathlib import Path

# 設定紀錄
logging.basicConfig(level=logging.INFO, format='[%(threadName)s] %(message)s')

class RWLock:
    def __init__(self):
        self._lock = threading.Lock()
        self._read_ready = threading.Condition(self._lock)
        self._readers = 0

    def acquire_read(self):
        with self._lock:
            self._readers += 1

    def release_read(self):
        with self._lock:
            self._readers -= 1
            if self._readers == 0:
                self._read_ready.notify_all()

    def acquire_write(self):
        self._lock.acquire()
        while self._readers > 0:
            self._read_ready.wait()

    def release_write(self):
        self._lock.release()

class AsyncSessionManager:
    def __init__(self, orchestrator: 'AsyncOrchestrator', storage_dir: str = "./sessions"):
        self._sessions: Dict[str, List[str]] = {}
        self._locks: Dict[str, RWLock] = {}
        self.orchestrator = orchestrator
        self._global_lock = threading.Lock()
        
        # 持久化設定
        self.storage_dir = Path(storage_dir)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._dirty_sessions = set() # 紀錄哪些 Session 有變動需要儲存
        
        # 啟動自動儲存背景執行緒
        self._stop_auto_save = threading.Event()
        self._auto_save_thread = threading.Thread(target=self._auto_save_loop, daemon=True)
        self._auto_save_thread.start()
        
        # 註冊退出鉤子
        atexit.register(self.save_all)

    def _get_lock(self, session_id: str) -> RWLock:
        with self._global_lock:
            if session_id not in self._locks:
                self._locks[session_id] = RWLock()
                # 嘗試從磁碟載入既有資料
                self._load_from_disk(session_id)
            return self._locks[session_id]

    def _load_from_disk(self, session_id: str):
        file_path = self.storage_dir / f"{session_id}.json"
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    self._sessions[session_id] = json.load(f)
                logging.info(f"成功從磁碟載入 Session '{session_id}'")
            except Exception as e:
                logging.error(f"載入 Session '{session_id}' 失敗: {e}")
                self._sessions[session_id] = []
        else:
            self._sessions[session_id] = []

    def append(self, session_id: str, content: str, trigger: bool = False) -> bool:
        lock = self._get_lock(session_id)
        lock.acquire_write()
        try:
            self._sessions[session_id].append(content)
            self._dirty_sessions.add(session_id) # 標記為髒資料
            logging.info(f"Session '{session_id}' 新增內容 (待儲存)")
        finally:
            lock.release_write()
        
        if trigger:
            return self.orchestrator.dispatch(session_id, content)
        return True

    def get_session(self, session_id: str) -> List[str]:
        lock = self._get_lock(session_id)
        lock.acquire_read()
        try:
            return list(self._sessions.get(session_id, []))
        finally:
            lock.release_read()

    def save_all(self):
        """強制儲存所有有變動的 Session 到磁碟"""
        with self._global_lock:
            sessions_to_save = list(self._dirty_sessions)
        
        for sid in sessions_to_save:
            self._save_to_disk(sid)
        
        logging.info("--- 磁碟持久化任務完成 ---")

    def _save_to_disk(self, session_id: str):
        lock = self._get_lock(session_id)
        lock.acquire_read() # 儲存時只需讀取鎖
        try:
            data = self._sessions.get(session_id, [])
            file_path = self.storage_dir / f"{session_id}.json"
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            with self._global_lock:
                self._dirty_sessions.discard(session_id)
            logging.info(f"已將 Session '{session_id}' 同步至磁碟")
        except Exception as e:
            logging.error(f"儲存 Session '{session_id}' 失敗: {e}")
        finally:
            lock.release_read()

    def _auto_save_loop(self):
        """背景定時儲存迴圈"""
        while not self._stop_auto_save.is_set():
            time.sleep(10) # 每 10 秒檢查一次
            if self._dirty_sessions:
                logging.info("偵測到變動，執行自動儲存...")
                self.save_all()

class AsyncOrchestrator:
    def __init__(self, max_workers: int = 5):
        self.executor = ThreadPoolExecutor(max_workers=max_workers, thread_name_prefix="AgentWorker")
        self.max_workers = max_workers
        self._active_tasks = 0
        self._task_lock = threading.Lock()

    def dispatch(self, session_id: str, content: str) -> bool:
        with self._task_lock:
            if self._active_tasks >= self.max_workers:
                return False
            self._active_tasks += 1
        self.executor.submit(self._run_task_wrapper, session_id, content)
        return True

    def _run_task_wrapper(self, session_id: str, content: str):
        try:
            logging.info(f"--- 鏈條任務啟動 (Session: {session_id}) ---")
            time.sleep(2) # 模擬複雜處理
        finally:
            with self._task_lock:
                self._active_tasks -= 1
            logging.info(f"--- 鏈條任務結束 ---")

# --- 測試腳本 ---
if __name__ == "__main__":
    print("=== [實驗] Session 持久化與自動儲存測試啟動 ===")
    
    orchestrator = AsyncOrchestrator(max_workers=5)
    # 指定儲存路徑為當前目錄下的 test_sessions
    sm = AsyncSessionManager(orchestrator, storage_dir="./test_sessions")

    # 1. 測試自動載入與寫入
    print("\n[動作] 寫入資料到 'user_chat'...")
    sm.append("user_chat", "這是第一條訊息")
    sm.append("user_chat", "這是第二條訊息", trigger=True)

    # 2. 測試手動儲存
    print("\n[動作] 執行手動儲存...")
    sm.save_all()

    # 3. 測試自動儲存 (等待 10 秒)
    print("\n[動作] 新增資料並等待自動儲存 (預計 10 秒後)...")
    sm.append("system_log", "自動儲存測試資料")
    
    # 模擬程式持續運行一段時間
    time.sleep(12)

    print("\n=== 測試完成 (請檢查 ./test_sessions 目錄) ===")
