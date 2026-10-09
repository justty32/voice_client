# 架構文檔：測試

[架構文檔入口](../architecture.md)

## 8. 測試

### 單元測試

- 框架單元測試：`tests/test_core_message.py`、`test_core_endpoint.py`、
  `test_core_exchange.py`、`test_core_module.py`、`test_core_adapter.py`
- 業務模組測試：`tests/test_workspace_manager.py`、`test_stt_gate.py`、
  `test_command_router_*.py`（熱鍵、狀態事件、工作區、剪貼簿、對話、語音）、
  `test_chat_flow_reply.py`、`test_chat_flow_summary.py`、`test_cli_text_bridge.py`
- 領域資料結構測試：`tests/test_workspace*.py`、`test_session_manager.py`、`test_session_io.py`
- 共用 helper（`_` 開頭，不被收集）：`tests/_helpers.py`、`_router_helpers.py`、`_chat_flow_helpers.py`
- 工具測試：`tests/test_codemap.py`
- 協定契約測試：`tests/test_protocol_contract.py`（`protocol.topics.ALL`＝`wire()` 路由＝codemap 掃描＝`topics.md` 表，生產者逐 topic 比對）、`test_protocol_literals.py`（產品碼不得用 topic 字面字串）

I/O 層測試（全部 mock，不碰網路、stdin 或 LLM 伺服器）：`tests/test_http_client.py`、`test_summary_generator.py`、`test_terminal_input.py`、`test_llm_client.py`、`test_config.py`、`test_logging_setup.py`。

### 接線與整合測試

- 接線測試：`tests/test_app_wiring.py`（經 `build_core()` 組裝後的端到端路由驗證）；
  組裝與啟停：`test_app_assembly.py`（路由＝`ALL`、queue 鍵＝`wire()`、不匯入硬體模組、settings 等價）、`test_lifecycle.py`
- 手機伺服器測試：`tests/test_mobile_{server,alignment}.py`（`fastapi.testclient`；缺 fastapi／httpx 時 skip）、
  `tests/test_mobile_wiring.py`（接線與邊緣轉換，不需 fastapi）；替身與 tmp 路徑在 `tests/_mobile_fakes.py`
- 本機控制測試：`tests/test_local_control.py`（白名單、轉發、未知命令、去抖）
- 框架整合測試：`tests/test_core_integration.py`（生產者→Exchange→消費者全鏈）、
  `test_voice_flow_integration.py`（語音資料流：audio→STT→當前工作區）、
  `test_command_flow_integration_{voice,cli}.py`（指令流：熱鍵／語音指令／終端全鏈）、
  `test_chat_flow_integration_{http,summary,playback}.py`（聊天流：HTTP 往返／摘要／重播全鏈）

### 執行方式

- 執行：`.venv/bin/python -m pytest -q`（測試以 unittest 撰寫，`python -m unittest discover -s tests` 亦可）
