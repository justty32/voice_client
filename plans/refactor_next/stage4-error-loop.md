# 階段 4：錯誤與狀態閉環

[總覽](README.md)｜痛點 3；B2、B7、B8、B14、P5

## 目標

legacy I/O 模組失敗時只記 log（`wf/architecture/pain-points.md` §3），UI 卡在「處理中」或無聲。本階段讓每條失敗路徑都回到上游：
新增 `stt_event` topic、錄音事件帶 `flushed`、摘要失敗 fallback、Kokoro worker 存活偵測、框架錯誤帶例外文字。
全部【改行為】，每項都列測試。子任務 4a–4f 各自可獨立 commit。

## 4a 框架錯誤帶例外訊息（P5）

- `core/module.py:55-63`：例外分支改呼叫 `self.on_handle_error(msg, exc)`；基底預設實作 emit 原 ui_event，但文字改為
  `f"[{self.name} 錯誤] 處理 {msg.topic} 失敗：{exc}"`。`"ui_event"` 字面仍留在 core（可覆寫 hook 就是解耦點；結構化 error topic 本輪不做）。
- 測試：`tests/test_core_module.py` 既有錯誤案例改斷言文字含例外訊息；新增「子類覆寫 `on_handle_error` 後基底不再 emit」。

## 4b 錄音靜音復位（B8 前半）

- `record.py:102-109`：`recording_stopped` 事件改 `recorder_event("recording_stopped", flushed=had_speech_before_reset)`（用階段 1 的建構函式）。
- `modules/command_router.py:201-203`：`flushed is False` → `ui_status("待機")`；否則維持「處理中」。
- 測試：
  - `tests/test_record.py` 新增以假 stream 驅動 `_loop(stream, pa)` 的案例：fake `stream.read()` 回全零 bytes（靜音）或高振幅 int16（語音），
    fake `pa.get_sample_size()` 回 2；在 `read` 的第 N 次呼叫把 `STOP` 放入 cmd queue、再把 `rec._running=False`。
    靜音 → 事件 `{"event":"recording_stopped","flushed":False}` 且 audio queue 空；語音 → `flushed True` 且 audio queue 有一個 WAV `BytesIO`（`wave.open` 可讀）。
    `test_record.py:16-17` 的 `numpy` stub 只在 numpy 不存在時生效；`.venv` 有 numpy，`_rms` 可真算。
  - `tests/test_command_router_hotkeys.py` 新增 `flushed False → 待機`；既有第 13 案（無 `flushed` 鍵 → 處理中）保留，代表舊 payload 相容。

## 4c `stt_event` topic：STT 失敗／空結果／完成回報（B7 前半、B8 後半、D6）

- `voice_to_text.py`：建構子加 `stt_event_queue: Queue | None = None`（預設 None，手機與舊呼叫者不受影響）。
  - `_load_model` 失敗 → put `{"event":"stt_error","message":str(exc)}`；
  - `_transcribe` 時 `_model is None` → `{"event":"stt_error","message":"STT 模型未載入"}`（每段都報，使用者才看得到）；
  - 轉譯例外 → `stt_error`；結果空 → `{"event":"stt_empty"}`；有文字 → 先 put 文字到 `stt_output_queue`，再 `{"event":"stt_done"}`。
- `protocol/topics.py` 加 `STT_EVENT="stt_event"`；`protocol/payloads.py` 加 `stt_event(event, **extra)`。
- `app_wiring/topology.py`：`legacy_queues` 新增必要鍵 `"stt_event"`，`register_producer("stt_event", OutboxAdapter(lq["stt_event"], topic=STT_EVENT, source="voice_to_text"))`。
- `app.py`：建 `stt_event_queue`，傳入 `VoiceToText(..., stt_event_queue=...)` 與 `legacy_queues`。
- `modules/command_router.py`：`consumes` 加 `STT_EVENT`；`handle` 分派到 `_handle_stt_event`：`stt_error` → `ui_message("system", f"[STT 錯誤] {message}")`＋`ui_status("待機")`；`stt_empty`／`stt_done` → `ui_status("待機")`。
- 測試：`tests/test_voice_to_text.py` 新增三案（mock `_load_model` 失敗、`_model=None`、fake model 回空／回字串，驅動一次 `_loop` 迭代——可把 `_loop` 的迴圈體抽成 `_process_one(audio_buffer)` 以便單測，behavior-preserving）；
  `tests/test_command_router_hotkeys.py` 新增 `stt_event` 三案；`tests/test_app_wiring.py`／`tests/_wiring_helpers.py` 加 `stt_event` queue 並新增路由案；契約測試自動要求 docs 同步。

## 4d Recorder 執行緒死亡後重試（B7 後半）

- `record.py:55-78`：`_worker` 外層加 `while self._running:` 重試，每次失敗 emit 既有 `error` 事件後以退避 `min(2**n, 30)` 秒等待（以 0.1 秒步進檢查 `_running`，可中斷）；成功進入 `_loop` 後 `n=0`。
- 測試：`tests/test_record.py` 既有案例改為 `PyAudio` 先拋一次、第二次回 fake（`open` 回 fake stream）並在進入 `_loop` 後把 `_running=False`；斷言 error 事件恰 1 筆、第二次有進 `_loop`（以 `mock.patch.object(rec, "_loop")` 計數）。退避在測試中以 `mock.patch("record.time.sleep")` 跳過。

## 4e 摘要失敗 fallback（B14）

- `summary_generator.py:54-67`：例外或空摘要 → put `{"type":"summary_failed","message":str(exc) 或 "空摘要","text":原文}`；`finally` 的 `待機` 維持。
- `modules/chat_flow.py:100-107`：`summary_failed` → `ui_message("system", f"[摘要失敗] {message}，改播原文")`＋`tts_item(text, "medium")`。
- 測試：`tests/test_summary_generator.py`（階段 2）改例外案例斷言多一筆 `summary_failed`；`tests/test_chat_flow_summary.py` 新增 fallback 案。

## 4f Kokoro worker 存活偵測（B2，D7）

- `text_to_voice.py`：`_dispatcher` 每輪先 `_check_kokoro_alive()`：`_engine=="kokoro"` 且 `_kokoro_process is not None` 且 `not is_alive()` →
  `log.error`、`_current_task_id=None`、`_heap.clear()`；`_kokoro_restarts < 1` → `_start_kokoro_worker()`、計數＋1；否則 `_kokoro_dead=True`。
  `_play` 在 `_kokoro_dead` 時 log warning 並丟棄任務（不再 put 進死佇列）。
- 測試：`tests/test_text_to_voice.py` 新增：fake process（`is_alive()` 回 False）＋`mock.patch.object(player, "_start_kokoro_worker")` → 呼叫一次重啟、`_current_task_id` 清空、heap 清空；第二次死亡 → 不再重啟且 `_play` 不 put。

## 步驟

4a → 4b → 4c → 4e → 4d → 4f（4c 牽涉 topic 新增，獨立 commit；其餘可各自 commit）。每個子任務後跑全套。

## behavior-preserving

否（全部是錯誤路徑的行為補強）。正常路徑不變，唯 D6：STT 成功後狀態列從「處理中」變「待機」。

## 驗證命令

```bash
.venv/bin/python -m pytest -q                                    # 全綠；≥ 上階段 + 至少 14
.venv/bin/python -m pytest -q tests/test_protocol_contract.py    # stt_event 已進 protocol／wire／codemap／docs
python workflows/common/code-map/codemap.py topics | rg -n "^stt_event" -A2
```

## 需同步的文件

- `docs/architecture/topics.md`：加 `stt_event` 行、`recorder_event` payload 加 `flushed`、`summary_out` 加 `summary_failed`。
- `docs/architecture/runtime.md` §7 錯誤策略：改寫為本階段的閉環敘述。
- CODE_MAP：`record.py`（重試）、`voice_to_text.py`（stt_event）、`text_to_voice.py`（存活偵測）描述。
- `docs/user_manual/troubleshooting.md`：「STT 模型未載入」「摘要失敗改播原文」「Kokoro 重啟一次」三條。
- `WAIT_USER.md`：加本階段的真機驗證項（見總覽）。

## Done when

- `rg -n "stt_event" protocol/topics.py app_wiring/topology.py app.py modules/command_router.py voice_to_text.py docs/architecture/topics.md` 每檔 ≥ 1 行。
- `rg -n "summary_failed" summary_generator.py modules/chat_flow.py` 各 ≥ 1 行。
- `rg -n "is_alive" text_to_voice.py` ≥ 2 行（原 `_stop_kokoro_worker` 之外新增）。
- pytest 全綠且測試數 ≥ 404；契約測試綠。

建議 commit：`feat(錯誤閉環): stt_event topic、靜音錄音復位、摘要失敗 fallback、Kokoro 存活偵測`（或依子任務拆）
