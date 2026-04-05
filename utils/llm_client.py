import logging

import requests

log = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 60


class LLMClient:
    """統一的 LLM API 呼叫介面。

    自動偵測 API 類型：
    - base_url 含 '/v1' 或提供 api_key → OpenAI 相容介面
    - 否則 → Ollama API
    """

    def __init__(self, model: str, base_url: str, api_key: str = "", timeout: int = _DEFAULT_TIMEOUT):
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._use_openai = "/v1" in self._base_url or bool(api_key)

    def chat(self, system_prompt: str, user_message: str) -> str:
        """發送對話，回傳模型的回覆文字。失敗時拋出例外。"""
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})

        if self._use_openai:
            return self._chat_openai(messages)
        return self._chat_ollama(messages)

    # ── Backends ───────────────────────────────────────────────────────

    def _chat_ollama(self, messages: list[dict]) -> str:
        url = f"{self._base_url}/api/chat"
        resp = requests.post(
            url,
            json={"model": self._model, "messages": messages, "stream": False},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return resp.json()["message"]["content"]

    def _chat_openai(self, messages: list[dict]) -> str:
        url = f"{self._base_url}/chat/completions"
        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"
        resp = requests.post(
            url,
            json={"model": self._model, "messages": messages},
            headers=headers,
            timeout=self._timeout,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
