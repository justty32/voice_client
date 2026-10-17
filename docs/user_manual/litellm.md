# 使用手冊：經 LiteLLM proxy 連線 LLM

[使用手冊入口](../user_manual.md)

## 11. 經本地 LiteLLM proxy 連線

`[LLM]` 與 `[SLM]` 都走 OpenAI 相容 API：程式把請求送到 `{base_url}/chat/completions`，
body 為 `{"model", "messages"}`，`api_key` 非空時加 `Authorization: Bearer <api_key>`
（見 `llm/llm_client.py`）。LiteLLM proxy 對外正是這個介面，所以**不需改程式碼，只改 `config.ini`**。

接 proxy 的好處：後端模型（LM Studio、Ollama、Gemini、OpenAI…）集中在 proxy 設定，
可在 proxy 端做 fallback、重試與用量紀錄，Voice Client 只認一個固定的模型別名。

### 11.1 安裝與啟動 proxy

建議與專案 `.venv` 分開安裝，避免依賴互相干擾：

```bash
uv tool install 'litellm[proxy]'      # 或 pipx install 'litellm[proxy]'
```

設定檔範例（例如 `~/.config/litellm/config.yaml`）：

```yaml
model_list:
  - model_name: voice-main            # 對 Voice Client 公開的別名
    litellm_params:
      model: openai/qwen/qwen3.5-9b   # openai/ 前綴＝轉給 OpenAI 相容後端
      api_base: http://localhost:1234/v1   # LM Studio
      api_key: dummy
  - model_name: voice-gemini          # 雲端備援
    litellm_params:
      model: gemini/gemini-2.5-flash-lite
      api_key: os.environ/GEMINI_API_KEY

router_settings:
  fallbacks: [{"voice-main": ["voice-gemini"]}]

general_settings:
  master_key: sk-local-voice          # 選用；設了之後所有請求都要帶這把 key
```

啟動並確認：

```bash
litellm --config ~/.config/litellm/config.yaml --port 4000
curl http://localhost:4000/v1/models -H "Authorization: Bearer sk-local-voice"
```

### 11.2 Voice Client 設定

```ini
[LLM]
model = voice-main                    # proxy 的 model_name，不是後端真實模型 ID
base_url = http://localhost:4000/v1
api_key = sk-local-voice              # 等於 master_key；proxy 未設 master_key 時留空
retry = 0
```

`[SLM]` 可以同樣改走 proxy（在 `model_list` 加一個摘要用別名，例如 `voice-slm`）。
`[SERVER] enabled` 維持 `false`，Voice Client 才會直接呼叫 `[LLM]`。改完需重啟程式。

### 11.3 注意事項

- **`model` 填別名**：填後端真實 ID 會被 proxy 拒絕（找不到 model）。
- **重試交給 proxy**：`[LLM] retry` 建議維持 `0`。兩層都重試會讓失敗時等待時間成倍增加。
- **逾時**：Voice Client 單次請求逾時固定 60 秒（`llm/llm_client.py` 的 `_DEFAULT_TIMEOUT`，
  目前不可由 config 設定）。LM Studio 首次載入模型或 fallback 到雲端可能超過，
  必要時在 proxy 端調 `request_timeout`／`timeout`，讓 proxy 先失敗並回報。
- **proxy 沒開**：Voice Client 會顯示 `[錯誤] …` 連線錯誤並備份到 `[WORKSPACE] failed_dir`。
  需要常駐時可寫成 systemd user service 開機自動啟動。
- **其他後端**：在 `model_list` 加條目即可（例如 Ollama 用 `ollama_chat/<模型>`、
  `api_base: http://localhost:11434`）；provider 前綴與參數以所裝 LiteLLM 版本的官方文件為準。
- **手機模式**共用同一份 `[LLM]` 設定；proxy 跑在桌機本機即可，不需對外開放 4000 埠。
