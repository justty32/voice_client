# CODE_MAP — Voice Client 程式碼導航

修改前從相關領域開始，不必遍讀整個 repo。行數、依賴與 topic 生產／消費圖可即時查：
`python workflows/common/code-map/codemap.py [big|topics|deps M|show P]`。

## 框架與接線

- `main.py`：桌面薄入口。
- `app.py`：`main()` 呼叫 `build_core`、以 `parts.queues` 建 legacy 元件、用 `Lifecycle` 單一清單啟停；re-export
  `wire`、`_dict_to_ui_event`、`_UiEventClass`、`_setup_logging`。
- `app_wiring/topology.py`：`wire()` 純接線，legacy queue／原生模組登錄進 Exchange。
- `app_wiring/assembly.py`：`build_core()` 組出 queue、SessionManager、原生模組、Exchange 並 `wire()`（不匯入硬體／網路模組）；`Lifecycle` 啟停註冊表。
- `app_wiring/settings.py`：桌面／手機共用設定解讀（default 對話、匯出目錄、SLM 參數）。
- `app_wiring/ui_events.py`：ui_event dict → `UiEvent`（rich 缺席時有相容替代類）。

隧道核心（`core/` 不依賴業務模組）：

- `core/message.py`：隧道訊息。
- `core/endpoint.py`：Inbox／Outbox。
- `core/exchange.py`：topic 路由與單執行緒交換。
- `core/module.py`：原生業務模組基底；`handle()` 例外交給可覆寫的 `on_handle_error()`（預設發含例外文字的 ui_event）。
- `core/adapter.py`：legacy queue 與隧道轉接。
- 測試：`tests/test_core_*`、`tests/test_app_wiring.py`、`test_app_assembly.py`、`test_lifecycle.py`。

## 協定

- `protocol/topics.py`：18 個 topic 名稱常數＋`ALL`（協定單一來源，只依賴標準庫；codemap 解析其常數）。
- `protocol/payloads.py`：payload 建構函式（`ui_message`、`command`、`outbound_chat`…）與控制字串常數。
- `protocol/commands.py`：指令集單一來源：斜線指令、對話管理子集、熱鍵五訊號與其標準化 cmd 名稱。
- 測試：`tests/test_protocol_commands.py`（指令集＝派發表鍵＝/help＝使用手冊）、`tests/test_protocol_contract.py`（wire／codemap／docs 三方比對）、`tests/test_protocol_literals.py`（禁止 topic 字面字串）。

## 語音管線

- `record.py`：PyAudio 錄音、VAD、pre-roll、切片；STOP 帶 `flushed`；失敗退避重試。
- `voice_to_text.py`：faster-whisper STT；每段結局經 `stt_event_queue` 回報。
- `text_to_voice.py`：`AudioPriorityPlayer` 優先級調度、播放中斷、Kokoro worker 啟停與存活偵測；
  re-export `tts/` 內的 worker 與分段函式。
- `tts/language.py`：CJK 偵測、espeak 語音選擇、中英分段。
- `tts/pyttsx3_worker.py`：pyttsx3 平台 driver 選擇與子 process 播放 worker。
- `tts/kokoro_worker.py`：長駐 Kokoro 子 process（懶載入模型、合成、可取消播放）。
- `modules/stt_gate.py`：辨識文字在 normal／command 模式間分流。
- 測試：`tests/test_record.py`、`test_voice_to_text.py`、`test_text_to_voice.py`、`test_stt_gate.py`、
  `test_voice_flow_integration.py`。

## 指令、工作區與對話

- `modules/command_router.py`：熱鍵、斜線、語音指令的派發表（`_build_handlers`）；錄音／STT 狀態列。
- `modules/command_handlers/`：CommandRouter 的工作區、對話與語音解析實作。
- `modules/workspace_manager.py`：當前工作區與 raw_text 唯一去向。
- `modules/cli_text_bridge.py`：CLI 文字／EOF 轉隧道訊息。
- `modules/chat_flow.py`：LLM 回覆、歷史、摘要決策、重播與 TTS 派發。
- `workspace.py`：通用工作區資料結構；執行緒安全（RLock），`drain()` 原子取出並清空。
- `session_manager.py`：多對話持久化；執行緒安全（RLock）、原子落盤、壞檔備份 `.corrupt-*`、同名 `/new` 拒絕。
- `http_client.py` / `summary_generator.py`：LLM 與摘要 I/O（摘要失敗出 `summary_failed`）。

測試：`tests/test_command_router_*`、`test_workspace*`、`test_chat_flow*`、
`test_session_manager.py`、`test_cli_text_bridge.py`、`test_http_client.py`、`test_summary_generator.py`；
共用 helper 在 `tests/_*helpers.py`。

## 介面

- `terminal_input.py`：終端文字與斜線指令來源。
- `keyboard_listener.py`：X11 等可由 `pynput` 監聽環境的全域熱鍵來源。
- `local_control.py`：Wayland/KDE 使用的 Unix socket 控制入口；只接受白名單命令，
  並送入與 `KeyboardListener` 共用的命令 queue。
- `tui_renderer.py`：Rich 終端呈現。
- 測試：`tests/test_local_control.py`、`test_terminal_input.py`。

## 手機

手機與桌面共用 `build_core()` 的 Data Tunnel，只替換邊緣裝置（瀏覽器錄音、WS 推送）。

- `mobile_server.py`：`create_app(state)`（lifespan 以 `Lifecycle` 啟停、單一 pusher、只服務最新連線、停機匯出 buffer）與啟動入口。
- `mobile/state.py`：`MobileState`（持 `CoreParts`）、`build_mobile_state()`（`*_cls` 注入替身）、`autosave_buffer()`；匯入無副作用。
- `mobile/edge.py`：`EdgeSink`（Exchange 投遞 → WS 事件）與 `BrowserClipboard`（注入 CommandRouter）。

前端往返：

- `mobile/inputs.py`：前端輸入轉送進 legacy queue；`/exit`、`/paste` 邊緣攔截。
- `mobile/outputs.py`：WS 推送迴圈（送失敗重送、對話清單變動補推 sessions）；`mobile/push.py`：邊緣推送 helper。
- `mobile/audio.py`（音訊 → WAV）、`mobile/net.py`（LAN IP）、`mobile/ssl_cert.py`（自簽憑證）、`static/`（前端）。
- 測試：`tests/test_mobile_server.py`（TestClient）、`test_mobile_wiring.py`（接線）；替身在 `tests/_mobile_fakes.py`。

## 設定與工具

- `config.py` / `config.ini`：設定讀取與預設值。
- `utils/`：LLM、clipboard、prompt 等共用工具；`utils/logging_setup.py` 為桌面與手機共用日誌設定。
- 測試：`tests/test_config.py`、`test_llm_client.py`、`test_logging_setup.py`。
