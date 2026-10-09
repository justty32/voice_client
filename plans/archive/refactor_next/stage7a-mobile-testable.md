> 封存 2026-10-09，已全部落地（見 workflows/feature-dev/landed/README.md）
# 階段 7a：手機可測試化

[總覽](README.md)｜痛點 1 前置；B6；`wf/architecture/entrypoints.md` §6

前置：D2 已安裝 `fastapi`、`uvicorn`（`.venv/bin/python -c "import fastapi, uvicorn"` 成功；`httpx` 已在 `.venv`，TestClient 可用）。
未安裝則本階段與 7b 不做，其餘階段不受影響。

## 目標

`mobile/state.py` 匯入時就 `load_config()`、設日誌、建 `VoiceToText` 等元件（18-46 行），導致無法注入替身、零測試。
本階段把組裝改成工廠、`app` 改成 `create_app(state)`、修多連線互搶（B6），並用 `fastapi.testclient.TestClient` 建立手機現行行為的安全網。
**不改任何手機可觀察行為**（除 B6），7b 才對齊桌面。

## 動到的檔案

- `mobile/state.py`：改為
  - `@dataclass MobileState`：現有全部模組層級名稱轉成欄位（`cfg, audio_queue, stt_output_queue, acc_input_queue, acc_cmd_queue, acc_output_queue, summary_queue, summary_output_queue, send_queue, recv_queue, ui_event_queue, session_manager, voice_to_text, text_accumulator, summary_gen, http_client, export_dir, wsc, summary_threshold, slm_enabled`）；
  - `build_mobile_state(config, *, voice_to_text_cls=VoiceToText, http_client_cls=HttpClient, summary_cls=SummaryGenerator, setup_logging=True) -> MobileState`：建構邏輯搬進來，`*_cls` 參數供測試注入 fake；用 `app_wiring.settings` 的三個函式（階段 5）。
  - 模組層級不再有任何副作用。
- `mobile/push.py`、`mobile/inputs.py`、`mobile/outputs.py`：所有函式第一個參數改 `state: MobileState`，內部 `_x` 全域改 `state.x`（機械替換）。
- `mobile_server.py`：
  - `create_app(state: MobileState) -> FastAPI`：lifespan、static 掛載、`/`、`/ws` 都在裡面建立；
  - `__main__` 區：`state = build_mobile_state(load_config()); app = create_app(state); uvicorn.run(app, ...)`（傳物件，不再用 `"mobile_server:app"` 字串）；
  - 刪除 24-67 行的 re-export（`wf/architecture/legacy.md` §3：無任何使用者）。
- B6【改行為】：`create_app` 內只保留**一個** `_output_pusher` 任務（lifespan 啟動時建立，`state.current_ws` 指向最新連線）；
  新連線到來時關閉舊連線（`await old.close()`），pusher 對 `send_json` 失敗的事件改放回 queue 頭（或暫存）而非丟棄。
  `websocket_handler` 不再每連線 `create_task(_output_pusher)`。
- `tests/test_mobile_server.py`、`tests/_mobile_helpers.py`：`@unittest.skipUnless(importlib.util.find_spec("fastapi"), "fastapi 未安裝")`。

## 新增測試（以 TestClient，不需手機、不載 Whisper）

`tests/_mobile_helpers.py`：`FakeVoiceToText(cfg, audio_q, stt_q)`（`start/stop` 空；測試可直接往 `stt_q` 放字串）、`FakeHttpClient`（從 `send_queue` 取 payload，立即放 `{"type":"ChatReply","Content":{"full_response":"回覆:"+Content}}` 進 `recv_queue`）、`FakeSummary`（空）；`make_state(tmp)` 用 tmp 的 sessions／export 路徑與 `SLM.enabled=false`。

`tests/test_mobile_server.py`（每案 `with TestClient(app) as c, c.websocket_connect("/ws") as ws:`；收訊息用輪詢直到預期型別或 2 秒逾時）：

1. 連線後先收到 `{"type":"status","text":"待機"}` 與 `{"type":"sessions",...}`。
2. 送 `{"type":"text","content":"哈囉"}` → 收到 `message role=user text=哈囉`。
3. 送 `{"type":"cmd","cmd":"/list"}` → 收到 `message role=system` 含「對話列表」。
4. 文字入列後送 `{"type":"signal","signal":"QUICK_SEND"}` → 依序收到 `sending`、`status 傳送中`、`assistant`、`tts`、`status 待機`。
5. 往 `state.stt_output_queue` 放「語音文字」→ 收到 `message role=voice`。
6. `/copy`（buffer 有內容）→ 收到 `clipboard_write`；`/paste` → 收到 `clipboard_read`；回送 `clipboard_data` → `system` 訊息「已從剪貼簿貼上」。
7. B6：開第二條 WS 連線後，舊連線被關閉（`ws1.receive()` 拋 `WebSocketDisconnect`），事件只送到新連線。
8. `GET /` 回 200。

這 8 案就是 7b 的回歸基準：7b 做完後除了文案依 D9 調整外，事件型別序列必須相同。

## 步驟

1. 安裝依賴（D2）；`.venv/bin/python -c "import mobile_server"` 目前會失敗（`uvicorn`），裝完應成功但仍有匯入副作用。
2. 先寫 `_mobile_helpers.py` 與測試 1–3（會因匯入副作用無法注入 → 紅）。
3. `state.py` 工廠化、三個模組加 `state` 參數、`create_app` → 1–6、8 綠。
4. B6 單一 pusher → 7 綠。
5. CODE_MAP、`docs/user_manual/mobile.md`（啟動方式不變，說明單連線語意）。

## behavior-preserving

是，除 B6（多連線由「隨機瓜分」變「只服務最新連線」）。

## 驗證命令

```bash
.venv/bin/python -c "import fastapi, uvicorn, httpx; print('ok')"
.venv/bin/python -m pytest -q                                   # 全綠；≥ 上階段 + 至少 8（fastapi 缺席時 skip 8）
.venv/bin/python -m pytest -q tests/test_mobile_server.py -v
.venv/bin/python -c "import mobile.state; print('no side effects')" # 不應建立 output/ 日誌或載入模型
```

## 需同步的文件

- CODE_MAP「手機」節：`mobile/state.py` 改「`MobileState` 與 `build_mobile_state()` 工廠」；`mobile_server.py` 改「`create_app()`」；加測試檔。
- `docs/user_manual/mobile.md`：多連線時只保留最新；啟動命令若有變（仍是 `python mobile_server.py`）則不改。
- `workflows/tooling/README.md`：註明 `fastapi`／`uvicorn` 現在也是開發環境（測試）需要的套件。
- `WAIT_USER.md`：手機真機連線、重連行為。

## Done when

- `rg -n "^_cfg = load_config" mobile/state.py` 無命中；`rg -n "def build_mobile_state|def create_app" mobile/state.py mobile_server.py` 各 1。
- `rg -n "noqa: F401" mobile_server.py` 無命中。
- `tests/test_mobile_server.py` 存在；pytest 全綠且測試數 ≥ 428。

建議 commit：`refactor(mobile): 組裝改工廠、create_app()、單一 pusher；補 TestClient 測試`
