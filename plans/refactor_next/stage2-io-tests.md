# 階段 2：I/O 層測試安全網＋三個邊界 bug

[總覽](README.md)｜痛點 9；B1、B9、B13

## 目標

替目前零測試的純邏輯 I/O 模組補單元測試（全部用 mock，不碰網路／麥克風／stdin），讓後面階段改 `stop()`、改錯誤路徑時有網接著。
寫測試時會直接撞到三個已確認 bug，於同階段修掉並明列。

## 動到的檔案

新增測試：

- `tests/test_terminal_input.py`：`mock.patch("builtins.input", side_effect=[...])` 驅動 `TerminalInput._loop`（先設 `_running=True`）。案例：
  空行略過；純文字進 `cli_text_queue`；`/send` → `{"cmd":"/send","args":[]}`；`/Export my file` 小寫化＋args；`/foo bar` → `{"cmd":"unknown","args":["/foo bar"]}`；
  `/exit` → cmd queue 有 `/exit` 且 text queue 有 `EXIT_SIGNAL` 並結束；`EOFError` → `EXIT_SIGNAL`。
- `tests/test_http_client.py`（config 需 `SERVER`、`WORKSPACE.failed_dir`（指向 tmp）、`LLM` 三節；`load_prompt("llm_system")` 讀 `prompts/`，不用 mock）：
  - 本地模式 `_dispatch` 無 `Content` → `None`；
  - `_post_http`：`mock.patch("http_client.requests.post")` 連續拋例外 → 嘗試 `retry+1` 次、回 `{"type":"Error"}`、`failed_dir` 多一個 json；成功回 `resp.json()`；
  - `_call_local`：把 `client._llm.chat` 換成記錄參數的 fake；歷史為空 → `user_input == content`；
    **歷史 ≥ 2 筆時 `user_input` 末段必須是本次 `Content`**（這條在修 B1 前是紅的）；`chat` 拋例外 → Error＋備份。
- `tests/test_summary_generator.py`：fake `_llm.chat`；成功 → 輸出序列 `status SLM摘要中 → summary → status 待機`；拋例外 → 只有兩個 status（階段 4e 會改這條）；`enabled=false` → 任務被吞、無輸出。
- `tests/test_logging_setup.py`：`log_file` 設成純檔名時不得拋例外（修 B13 前紅）；測後 `logging.root.handlers.clear()` 還原，`chdir` 到 tmp。
- `tests/test_local_control.py` 追加：`_running=True`、`_socket=None` 時呼叫 `_loop()` 直接返回、不拋 `AssertionError`（修 B9 前紅）。
- `tests/test_config.py`：`load_config("不存在.ini")` 回空 `ConfigParser`、不拋。
- `tests/test_llm_client.py`：以 mock 驗 `utils/llm_client.py` 的 retry 次數語意（`range(max_retries + 1)`）與成功回傳；先讀該檔確認介面。

修改（【改行為】＝修 bug）：

- `http_client.py:115-117`【改行為 B1】：歷史迴圈變數改名（`hist_role`／`hist_content`），`user_input` 用本次 `content`。
- `utils/logging_setup.py:15`【改行為 B13】：`d = os.path.dirname(log_file); if d: os.makedirs(d, exist_ok=True)`。
- `local_control.py:86-94`【改行為 B9】：`_loop` 內先 `sock = self._socket; if sock is None: break`，用區域變數 `recv`，移除 `assert`。

`keyboard_listener.py`（需 `pynput`）、`tui_renderer.py`（需 `rich` 與終端）本階段不補；列 WAIT_USER。

## 步驟

1. 先寫各測試檔，跑一次，確認除了 B1／B9／B13 三條以外全綠（其餘紅的代表對現碼理解有誤，先修測試）。
2. 修三個 bug，跑到全綠。
3. 更新 CODE_MAP 測試清單、`docs/architecture/testing.md`。

## behavior-preserving

測試新增：是。三處修改：**否（修 bug）**，可觀察差異：
- B1：`SERVER.enabled=false` 且歷史 ≥ 2 筆時，送給 LLM 的「目前的對話內容」是使用者本次輸入。
- B13：`WORKSPACE.log_file=system.log` 可啟動。
- B9：關機時不再可能印 `AssertionError` traceback。

## 驗證命令

```bash
.venv/bin/python -m pytest -q                       # 全綠；≥ 上階段 + 至少 18（terminal 7、http 6、summary 3、logging 1、local_control 1、config 1、llm 2 以上）
.venv/bin/python -m pytest -q tests/test_http_client.py -k history   # B1 驗收
python -m compileall -q -x '/(\.venv|\.git)/' .
```

## 需同步的文件

- CODE_MAP：「指令、工作區與對話」測試行加 `test_http_client.py`、`test_summary_generator.py`；「介面」加 `test_terminal_input.py`；「設定、工具」加 `test_logging_setup.py`、`test_config.py`、`test_llm_client.py`。
- `docs/architecture/testing.md` 單元測試清單。
- `docs/user_manual/config.md`：`log_file` 可為純檔名（若該文件有描述此欄位）。

## Done when

- 七個新測試檔存在；pytest 全綠且測試數 ≥ 381。
- `rg -n "content = msg\[1\]" http_client.py` 無命中。
- `rg -n "assert self._socket" local_control.py` 無命中。
- `rg -n 'if d:|if directory' utils/logging_setup.py` 命中 1 行。

建議 commit：先 `test: 補 terminal_input／http_client／summary_generator 等 I/O 單元測試`，再 `fix: 本地 LLM 歷史覆蓋 content、log_file 純檔名、LocalControl 停機 assert`（或合一）。
