import configparser
import logging
import threading
from queue import Empty, Queue

from utils.llm_client import LLMClient
from utils.prompt_loader import load_prompt

log = logging.getLogger(__name__)

class SummaryGenerator:
    """接收 LLM 回覆並生成摘要的元件。"""

    def __init__(
        self,
        config: configparser.ConfigParser,
        summary_queue: Queue,
        summary_output_queue: Queue,
    ):
        self._summary_queue = summary_queue
        self._output_queue = summary_output_queue

        slm = config["SLM"]
        self._enabled = slm.getboolean("enabled", True)
        self._model = slm.get("model", "gemma3:1b")
        base_url = slm.get("base_url", "http://localhost:11434")

        self._llm = LLMClient(self._model, base_url)
        self._summary_prompt = load_prompt("slm_summary")

        self._running = False
        self._thread: threading.Thread | None = None

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="SummaryGenerator")
        self._thread.start()

    def stop(self):
        self._running = False

    def _loop(self):
        while self._running:
            try:
                task = self._summary_queue.get(timeout=0.1)
            except Empty:
                continue

            if not self._enabled:
                continue

            text = task.get("text", "")
            try:
                self._output_queue.put({"type": "status", "text": "SLM摘要中"})
                summary = self._llm.chat(self._summary_prompt, text)
                if summary and summary.strip():
                    self._output_queue.put({
                        "type": "summary",
                        "text": summary,
                        "model": self._model,
                    })
            except Exception as exc:
                log.warning("SLM summary failed: %s", exc)
            finally:
                self._output_queue.put({"type": "status", "text": "待機"})
