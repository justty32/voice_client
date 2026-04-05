import logging
import re
import time

import requests

log = logging.getLogger(__name__)

_DEFAULT_TIMEOUT = 60
_DEFAULT_RETRIES = 3


class LLMClient:
    """統一的 LLM API 呼叫介面，相容所有 OpenAI 格式的 API。

    適用後端：
    - OpenAI / Azure OpenAI
    - Google Gemini（OpenAI 相容端點）
    - Ollama（使用 http://localhost:11434/v1）
    - 任何 OpenAI 相容的本地或雲端服務
    """

    def __init__(self, model: str, base_url: str, api_key: str = "",
                 timeout: int = _DEFAULT_TIMEOUT, max_retries: int = _DEFAULT_RETRIES):
        self._model = model
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._timeout = timeout
        self._max_retries = max_retries

    def chat(self, system_prompt: str, user_message: str) -> str:
        """發送對話，回傳模型的回覆文字。失敗時會重試。"""
        messages: list[dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": user_message})

        last_exc = None
        for attempt in range(self._max_retries + 1):
            try:
                return self._chat_openai(messages)
            except requests.exceptions.RequestException as e:
                last_exc = e
                response = getattr(e, "response", None)
                status_code = getattr(response, "status_code", None)

                if status_code == 429:
                    if attempt >= self._max_retries:
                        log.error("Rate limited (429). No retries left.")
                        raise
                    wait_time = self._parse_retry_after(response)
                    log.warning(f"Rate limited (429). Waiting {wait_time}s before retry {attempt + 1}/{self._max_retries}")
                    time.sleep(wait_time)
                    continue

                if status_code and 500 <= status_code < 600:
                    if attempt >= self._max_retries:
                        log.error(f"Server error ({status_code}). No retries left.")
                        raise
                    wait_time = 2 ** attempt
                    log.warning(f"Server error ({status_code}). Retrying in {wait_time}s... ({attempt + 1}/{self._max_retries})")
                    time.sleep(wait_time)
                    continue

                if attempt >= self._max_retries:
                    log.error(f"LLM API call failed after {self._max_retries} retries: {e}")
                    raise

                log.warning(f"Request failed: {e}. Retrying in 1s... ({attempt + 1}/{self._max_retries})")
                time.sleep(1.0)

        if last_exc:
            raise last_exc
        raise RuntimeError("LLMClient.chat failed unexpectedly without exception")

    def _chat_openai(self, messages: list[dict]) -> str:
        url = self._base_url
        if not url.endswith("/chat/completions"):
            url = f"{url}/chat/completions"

        headers = {"Content-Type": "application/json"}
        if self._api_key:
            headers["Authorization"] = f"Bearer {self._api_key}"

        resp = requests.post(
            url,
            json={"model": self._model, "messages": messages},
            headers=headers,
            timeout=self._timeout,
        )
        if resp.status_code != 200:
            log.debug(f"API error response: {resp.text}")
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]

    def _parse_retry_after(self, response: requests.Response) -> float:
        """嘗試從 Response 中解析重試等待時間。"""
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass

        # Gemini RetryInfo in JSON body
        try:
            body = response.json()
            if isinstance(body, list) and body:
                body = body[0]
            for detail in body.get("error", {}).get("details", []):
                if detail.get("@type") == "type.googleapis.com/google.rpc.RetryInfo":
                    match = re.search(r"([\d\.]+)", detail.get("retryDelay", ""))
                    if match:
                        return float(match.group(1))
        except Exception:
            pass

        return 5.0
