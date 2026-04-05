import configparser
import json
import logging
import os
import threading
import time
from queue import Empty, Queue

import requests

from utils.llm_client import LLMClient
from utils.prompt_loader import load_prompt

log = logging.getLogger(__name__)


class HttpClient:
    """網路通訊層。從 send_queue 取 payload，送出後將回應放入 recv_queue。

    雙模式：
    - SERVER.enabled = true  → HTTP POST 到遠端伺服器（含重試與失敗備份）
    - SERVER.enabled = false → 本地 LLM 直接回應
    """

    def __init__(self, config: configparser.ConfigParser, send_queue: Queue, recv_queue: Queue, session_manager: "SessionManager"):
        self._send_queue = send_queue
        self._recv_queue = recv_queue
        self._session_manager = session_manager

        srv = config["SERVER"]
        self._enabled = srv.getboolean("enabled", False)
        self._url = srv.get("url", "")
        self._timeout = int(srv.get("timeout", 30))
        self._retry = int(srv.get("retry", 3))

        ws = config["WORKSPACE"]
        self._failed_dir = ws.get("failed_dir", "output/failed")

        llm = config["LLM"]
        llm_retry = int(llm.get("retry", str(self._retry)))
        self._llm = LLMClient(
            model=llm.get("model", "qwen2.5:7b"),
            base_url=llm.get("base_url", "http://localhost:11434"),
            api_key=llm.get("api_key", ""),
            max_retries=llm_retry,
        )
        self._system_prompt = load_prompt("llm_system")

        self._thread: threading.Thread | None = None
        self._running = False

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True, name="HttpClient")
        self._thread.start()

    def stop(self):
        self._running = False

    # ── Worker ─────────────────────────────────────────────────────────

    def _loop(self):
        while self._running:
            try:
                payload = self._send_queue.get(timeout=0.1)
            except Empty:
                continue
            response = self._dispatch(payload)
            if response:
                self._recv_queue.put(response)

    def _dispatch(self, payload: dict) -> dict | None:
        # Approval results and other non-chat payloads have no "Content"
        if "Content" not in payload:
            if self._enabled:
                return self._post_http(payload)
            return None

        if self._enabled:
            return self._post_http(payload)
        return self._call_local(payload)

    # ── HTTP mode ──────────────────────────────────────────────────────

    def _post_http(self, payload: dict) -> dict | None:
        last_exc = None
        for attempt in range(self._retry):
            try:
                resp = requests.post(self._url, json=payload, timeout=self._timeout)
                resp.raise_for_status()
                return resp.json()
            except Exception as exc:
                last_exc = exc
                log.warning("HTTP attempt %d/%d failed: %s", attempt + 1, self._retry, exc)
                if attempt < self._retry - 1:
                    time.sleep(1)
        self._save_failed(payload)
        return {"type": "Error", "message": str(last_exc)}

    # ── Local LLM mode ─────────────────────────────────────────────────

    def _call_local(self, payload: dict) -> dict | None:
        content = payload.get("Content", "")
        if not content:
            return None
        
        # 獲取歷史紀錄並格式化
        session = self._session_manager.get_current_session()
        formatted_history = ""
        if session and "history" in session:
            # 限制歷史紀錄長度，避免過長導致 429
            # 這裡我們手動將對話串接成一段文字，讓模型理解上下文
            for msg in session["history"][-6:-1]: # 取最後幾筆作為上下文，排除剛加入的一筆
                role_label = "使用者" if msg["role"] == "user" else "AI助手"
                formatted_history += f"{role_label}: {msg['content']}\n"
        
        # 組合上下文與當前問題
        if formatted_history:
            user_input = f"以下是之前的對話背景：\n{formatted_history}\n目前的對話內容：{content}"
        else:
            user_input = content
            
        try:
            reply = self._llm.chat(self._system_prompt, user_input)
            return {
                "type": "ChatReply",
                "Title": payload.get("Title", ""),
                "Content": {"full_response": reply},
                "model": self._llm._model,
            }
        except Exception as exc:
            log.error("Local LLM failed: %s", exc)
            self._save_failed(payload)
            return {"type": "Error", "message": str(exc)}

    # ── Failed payload backup ──────────────────────────────────────────

    def _save_failed(self, payload: dict):
        try:
            os.makedirs(self._failed_dir, exist_ok=True)
            path = os.path.join(self._failed_dir, f"{int(time.time())}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(payload, f, ensure_ascii=False, indent=2)
            log.info("Saved failed payload: %s", path)
        except Exception as exc:
            log.error("Could not save failed payload: %s", exc)
