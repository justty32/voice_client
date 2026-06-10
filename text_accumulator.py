import configparser
import logging
import os
import threading
import time
from queue import Empty, Queue

from utils import clipboard
from workspace import Workspace

log = logging.getLogger(__name__)


def _to_int(s) -> int | None:
    try:
        return int(s)
    except (ValueError, TypeError):
        return None

class TextAccumulator:
    """文字累積與緩存中心（buffer 工作區）。

    內部以 Workspace 承載暫存內容：每筆輸入文字為一個 entry。對外指令行為
    （flush/peek/clear/concat/to_top/export/import）與訊息格式維持不變。
    """

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

        self._ws = Workspace("buffer")
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

    def count(self) -> int:
        """目前 buffer 筆數（供 /ws 列舉用；CPython GIL 下讀取為原子操作）。"""
        return self._ws.count()

    def stop(self):
        self._running = False
        if not self._ws.is_empty():
            temp_path = os.path.join(os.path.dirname(self._export_path) or ".", "_buffer_temp.json")
            try:
                self._ws.export(temp_path)
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
                    self._ws.append(item["text"])
            except Empty:
                pass

            time.sleep(0.01)

    def _handle_cmd(self, cmd: dict):
        op = cmd.get("cmd")
        args = cmd.get("args", [])
        # 以空格 join 支援含空格的檔名（與 session /save 行為一致）
        filename = " ".join(args) if args else None

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
            self._to_top(args)
        elif op == "delete":
            self._delete(args)
        elif op == "move":
            self._move(args)
        elif op == "copy":
            self._copy()
        elif op == "paste":
            self._paste()

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
        if not self._ws.is_empty():
            lines = "\n".join(f"  [{i+1}] {t}" for i, t in enumerate(self._ws.lines()))
            text = f"[暫存區 · {self._ws.count()} 筆]\n{lines}"
        else:
            text = "[暫存區是空的]"
        self._output_queue.put({"type": "buffer_peek", "text": text})

    def _export(self, filename: str | None):
        path = self._get_path(filename, is_import=False)
        if not path:
            self._output_queue.put({"type": "buffer_peek", "text": "[錯誤] 請指定匯出檔名。例如: /export my_data"})
            return

        try:
            self._ws.export(path)
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
            added = self._ws.import_file(path, append=True)
            unit = "行文字" if path.lower().endswith(".txt") else "筆資料"
            msg = f"[系統] 已從 {path} 匯入 {added} {unit}（追加至末尾）。"
            log.info("Imported buffer from %s (appended)", path)
        except ValueError as e:
            # 例如 JSON 不是陣列
            msg = f"[錯誤] {e}"
            log.error("Import failed: %s", e)
        except Exception as e:
            msg = f"[錯誤] 匯入失敗: {e}"
            log.error("Import failed: %s", e)
        self._output_queue.put({"type": "buffer_peek", "text": msg})

    def _clear(self):
        count = self._ws.clear()
        self._output_queue.put({"type": "buffer_peek", "text": f"[系統] 暫存區已清空（原含 {count} 筆）。"})
        log.info("Cleared buffer.")

    def _concat(self):
        if self._ws.is_empty():
            return
        count = self._ws.count()
        self._ws.concat_all(" ")
        self._output_queue.put({"type": "buffer_peek", "text": f"[系統] 已連接暫存區文字（將 {count} 筆壓縮為 1 筆）。"})
        log.info("Concatenated buffer.")

    def _to_top(self, args=None):
        idx = None
        if args:
            idx = _to_int(args[0])
            if idx is None:
                self._output_queue.put({"type": "buffer_peek", "text": "用法: /to_top [編號]（需為數字）"})
                return
        if not self._ws.move_to_top((idx - 1) if idx else -1):
            if idx:
                self._output_queue.put({"type": "buffer_peek", "text": f"[錯誤] 暫存區沒有第 {idx} 筆，或筆數不足。"})
            return
        where = f"第 {idx} 筆" if idx else "最後一筆文字"
        self._output_queue.put({"type": "buffer_peek", "text": f"[系統] 已將{where}移至最前方。"})
        log.info("Moved item to top.")

    def _delete(self, args):
        idx = _to_int(args[0]) if args else None
        if idx is None:
            self._output_queue.put({"type": "buffer_peek", "text": "用法: /del <編號>（需為數字）"})
            return
        if self._ws.delete(idx - 1):
            self._output_queue.put({"type": "buffer_peek", "text": f"[系統] 已刪除暫存區第 {idx} 筆。"})
        else:
            self._output_queue.put({"type": "buffer_peek", "text": f"[錯誤] 暫存區沒有第 {idx} 筆。"})

    def _move(self, args):
        if len(args) < 2:
            self._output_queue.put({"type": "buffer_peek", "text": "用法: /move <來源編號> <目標編號>"})
            return
        src = _to_int(args[0])
        dst = _to_int(args[1])
        if src is None or dst is None:
            self._output_queue.put({"type": "buffer_peek", "text": "用法: /move <來源編號> <目標編號>（需為數字）"})
            return
        if self._ws.move(src - 1, dst - 1):
            self._output_queue.put({"type": "buffer_peek", "text": f"[系統] 已將暫存區第 {src} 筆移到第 {dst} 位。"})
        else:
            self._output_queue.put({"type": "buffer_peek", "text": "[錯誤] 移動失敗（編號超出範圍）。"})

    def _copy(self):
        if self._ws.is_empty():
            self._output_queue.put({"type": "buffer_peek", "text": "[暫存區是空的，沒有可複製的內容]"})
            return
        text = self._ws.flatten(seg_sep=" ", entry_sep="\n")
        ok, err = clipboard.copy(text)
        msg = f"[系統] 已複製暫存區 {self._ws.count()} 筆到剪貼簿。" if ok else f"[錯誤] {err}"
        self._output_queue.put({"type": "buffer_peek", "text": msg})

    def _paste(self):
        ok, data = clipboard.paste()
        if not ok:
            self._output_queue.put({"type": "buffer_peek", "text": f"[錯誤] {data}"})
            return
        lines = [ln.strip() for ln in data.splitlines() if ln.strip()]
        for ln in lines:
            self._ws.append(ln)
        self._output_queue.put({"type": "buffer_peek", "text": f"[系統] 已從剪貼簿貼上 {len(lines)} 筆到暫存區。"})

    def _flush(self):
        if self._ws.is_empty():
            return
        combined = self._ws.flatten(seg_sep=" ", entry_sep=" ")
        self._ws.clear()

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
