import configparser
import json
import logging
import os
import threading
import time
from queue import Empty, Queue

log = logging.getLogger(__name__)

class TextAccumulator:
    """文字累積與緩存中心。"""

    def __init__(
        self,
        config: configparser.ConfigParser,
        input_queue: Queue,
        cmd_queue: Queue,
        acc_output_queue: Queue,
    ):
        self._input_queue = input_queue
        self._cmd_queue = cmd_queue
        self._output_queue = acc_output_queue

        self._buffer: list[str] = []
        self._running = False
        self._thread: threading.Thread | None = None

        # Workspace paths
        self._export_path = config.get("WORKSPACE", "export_file", fallback="output/export.json")
        export_dir = os.path.dirname(self._export_path)
        if export_dir:
            os.makedirs(export_dir, exist_ok=True)

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="TextAccumulator")
        self._thread.start()

    def stop(self):
        self._running = False
        if self._buffer:
            temp_path = os.path.join(os.path.dirname(self._export_path) or ".", "_buffer_temp.json")
            try:
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(self._buffer, f, ensure_ascii=False, indent=2)
                log.info("Auto-saved buffer to %s", temp_path)
            except Exception as e:
                log.error("Failed to auto-save buffer: %s", e)

    def _loop(self):
        while self._running:
            # Commands priority
            try:
                cmd = self._cmd_queue.get_nowait()
                self._handle_cmd(cmd)
            except Empty:
                pass

            try:
                item = self._input_queue.get_nowait()
                if item.get("type") == "text" and item.get("text", "").strip():
                    self._buffer.append(item["text"])
            except Empty:
                pass

            time.sleep(0.01)

    def _handle_cmd(self, cmd: dict):
        op = cmd.get("cmd")
        args = cmd.get("args", [])
        filename = args[0] if args else None

        if op == "flush":
            self._flush()
        elif op == "peek":
            self._peek()
        elif op == "export":
            self._export(filename)
        elif op == "import":
            self._import(filename)
        elif op == "clear":
            self._clear()
        elif op == "concat":
            self._concat()
        elif op == "to_top":
            self._to_top()

    def _get_path(self, filename: str | None, is_import: bool = False) -> str | None:
        if not filename:
            if is_import:
                # Import 預設讀取暫存檔
                base_dir = os.path.dirname(self._export_path)
                return os.path.join(base_dir if base_dir else ".", "_buffer_temp.json")
            else:
                # Export 不再提供預設路徑，強制要求參數
                return None
        
        # Ensure filename has extension, default .json
        if "." not in filename:
            filename += ".json"
            
        # If it's just a filename, put it in the same directory as default export
        # Check both / and \ for cross-platform robustness
        if os.sep not in filename and "/" not in filename and "\\" not in filename:
            base_dir = os.path.dirname(self._export_path)
            return os.path.join(base_dir if base_dir else ".", filename)
        return filename

    def _peek(self):
        if self._buffer:
            lines = "\n".join(f"  [{i+1}] {t}" for i, t in enumerate(self._buffer))
            text = f"[暫存區 · {len(self._buffer)} 筆]\n{lines}"
        else:
            text = "[暫存區是空的]"
        self._output_queue.put({"type": "buffer_peek", "text": text})

    def _export(self, filename: str | None):
        path = self._get_path(filename, is_import=False)
        if not path:
            self._output_queue.put({"type": "buffer_peek", "text": "[錯誤] 請指定匯出檔名。例如: /export my_data"})
            return

        try:
            # Ensure directory exists
            export_dir = os.path.dirname(path)
            if export_dir:
                os.makedirs(export_dir, exist_ok=True)
            
            if path.lower().endswith(".txt"):
                with open(path, "w", encoding="utf-8") as f:
                    f.write("\n".join(self._buffer))
            else:
                with open(path, "w", encoding="utf-8") as f:
                    json.dump(self._buffer, f, ensure_ascii=False, indent=2)
            
            msg = f"[系統] 暫存區已匯出至: {path}"
            log.info("Exported buffer to %s", path)
        except Exception as e:
            msg = f"[錯誤] 匯出失敗: {e}"
            log.error("Export failed: %s", e)
        self._output_queue.put({"type": "buffer_peek", "text": msg})

    def _import(self, filename: str | None):
        path = self._get_path(filename, is_import=True)
        if not path or not os.path.exists(path):
            self._output_queue.put({"type": "buffer_peek", "text": f"[錯誤] 找不到檔案: {path if path else ''}"})
            return
            
        try:
            if path.lower().endswith(".txt"):
                with open(path, "r", encoding="utf-8") as f:
                    lines = f.readlines()
                new_items = [line.strip() for line in lines if line.strip()]
                self._buffer.extend(new_items)
                msg = f"[系統] 已從 {path} 匯入 {len(new_items)} 行文字（追加至末尾）。"
            else:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    new_items = [str(item) for item in data]
                    self._buffer.extend(new_items)
                    msg = f"[系統] 已從 {path} 匯入 {len(new_items)} 筆資料（追加至末尾）。"
                else:
                    msg = "[錯誤] 匯入格式不正確，應為 JSON 陣列。"
            log.info("Imported buffer from %s (appended)", path)
        except Exception as e:
            msg = f"[錯誤] 匯入失敗: {e}"
            log.error("Import failed: %s", e)
        self._output_queue.put({"type": "buffer_peek", "text": msg})

    def _clear(self):
        count = len(self._buffer)
        self._buffer.clear()
        self._output_queue.put({"type": "buffer_peek", "text": f"[系統] 暫存區已清空（原含 {count} 筆）。"})
        log.info("Cleared buffer.")

    def _concat(self):
        if not self._buffer:
            return
        count = len(self._buffer)
        combined = " ".join(self._buffer)
        self._buffer = [combined]
        self._output_queue.put({"type": "buffer_peek", "text": f"[系統] 已連接暫存區文字（將 {count} 筆壓縮為 1 筆）。"})
        log.info("Concatenated buffer.")

    def _to_top(self):
        if len(self._buffer) < 2:
            return
        last_item = self._buffer.pop()
        self._buffer.insert(0, last_item)
        self._output_queue.put({"type": "buffer_peek", "text": "[系統] 已將最後一筆文字移至最前方。"})
        log.info("Moved last item to top.")

    def _flush(self):
        if not self._buffer:
            return
        combined = " ".join(self._buffer)
        self._buffer.clear()

        if not combined.strip():
            return

        self._output_queue.put({
            "type": "payload",
            "payload": {
                "Title": "",        # Main Loop fills in
                "Content": combined,
                "Metadata": {},     # Main Loop fills in
            },
        })
