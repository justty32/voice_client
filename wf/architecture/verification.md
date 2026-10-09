# 報告查證（拆檔後現況）

[入口](README.md)

查證兩份 2026-07-02 的報告：`reports/bug-review.md`（B 編號）、`reports/architecture-improvements.md`（P 編號）。
狀態分三種：**仍成立**（位置相同或只是行號漂移）、**路徑改變**（仍成立但搬到新檔）、**已修**。
這輪拆檔都是 behavior-preserving，所以沒有任何一條因此被修掉。

## 1. bug-review：B1–B5

| # | 狀態 | 現在位置 |
|---|---|---|
| B1 本地 LLM `content` 被歷史迴圈覆蓋 | 仍成立 | `http_client.py:104,117,123`（行號沒變） |
| B2 Kokoro worker 死亡後 TTS 永久停擺 | 路徑改變（同檔，行號漂移） | `text_to_voice.py:148-154`（`_play`）、`179-182`（`_is_playing`）、`219-230`（`_drain_kokoro_results`）；沒有任何 `is_alive()` 檢查 |
| B3 Workspace 跨執行緒競態 | 仍成立 | `command_handlers/workspace.py:187-188`、`workspace.py:90-99`、`workspace_manager.py:50-51` |
| B4 SessionManager 無鎖、非原子寫入 | 仍成立 | `session_manager.py:79-85`、`125-133`；`_load` 失敗時清空（40-42） |
| B5 `new_session` 同名覆蓋、自動編號碰撞 | 路徑改變 | `session_manager.py:89-98`、`command_handlers/session.py:9`；手機在 `mobile/inputs.py:97` |

## 2. bug-review：B6–B10

| # | 狀態 | 現在位置 |
|---|---|---|
| B6 多條 WS 連線互搶共享 queue | 路徑改變 | `mobile_server.py:109-134`（每條連線一個 pusher）、`mobile/outputs.py:58-116` |
| B7 STT 模型載入失敗靜默；Recorder 執行緒死亡 | 仍成立 | `voice_to_text.py:87-100,102-104`、`record.py:55-78` |
| B8 靜音錄音後狀態卡在「處理中」 | 路徑改變 | `record.py:102-109`、`command_router.py:201-203`；手機在 `mobile/inputs.py:20-30` |
| B9 LocalControl 停機 assert 競態 | 仍成立 | `local_control.py:86-94`、`73-81` |
| B10 Recorder 待機時不讀 stream（疑似） | 仍成立 | `record.py:113-118` |

## 3. bug-review：B11–B14 與附註

| # | 狀態 | 現在位置 |
|---|---|---|
| B11 SttGate 模式與在途 STT 的順序競態（疑似） | 仍成立 | `stt_gate.py:40-64`、`command_router.py:163-181` |
| B12 桌面與手機指令行為不一致 | 路徑改變，差異更多 | `mobile/inputs.py:95-186` vs `command_router.py:80-159`；完整差異表見 [entrypoints.md](entrypoints.md) |
| B13 `log_file` 沒有目錄部分時 `makedirs("")` 崩潰 | 路徑改變（兩處合併成一處） | `utils/logging_setup.py:15` |
| B14 摘要失敗後長回覆不朗讀 | 仍成立 | `summary_generator.py:54-67`、`chat_flow.py:75-82` |

| 附註 | 狀態 | 現在位置 |
|---|---|---|
| CLAUDE.md 測試基準過時 | 仍成立（現在是 358 passed, 9 subtests） | `CLAUDE.md` 驗證要求段 |
| TextAccumulator 每輪 sleep，吞吐量受限 | 仍成立 | `text_accumulator.py:83` |
| `MUTE`/`UNMUTE` 死碼 | 仍成立 | `text_to_voice.py:238-243` |
| `/to_top 0` 被當成沒有參數 | 仍成立 | `command_handlers/workspace.py:109`、`text_accumulator.py:201` |

## 4. architecture-improvements：P1–P5

| # | 狀態 | 現況 |
|---|---|---|
| P1 mobile 對齊 Data Tunnel | 路徑改變 | 624 行拆成 `mobile_server.py`(168)＋`mobile/`(7 檔 559 行)；匯入時就建構的問題移到 `mobile/state.py:18-46`；重複邏輯對照見 [entrypoints.md](entrypoints.md) |
| P2 共享狀態無鎖 | 仍成立 | 見 B3、B4 |
| P3 topic／payload 集中定義 | 仍成立 | 沒有協定模組；指令集三份：`terminal_input.py:7`、`command_router.py:80-159`、`session.py:72-77`，手機再一份 `mobile/inputs.py:180-183` |
| P4 Exchange 沒有 fan-out／unregister／背壓 | 仍成立 | `core/exchange.py:30-33`、`core/endpoint.py:14,30` |
| P5 錯誤只發固定文字 | 仍成立 | `core/module.py:57-63` |

## 5. architecture-improvements：P6–P10

| # | 狀態 | 現況 |
|---|---|---|
| P6 legacy stop 不 join、啟停清單三份 | 路徑改變 | 清單在 `app.py:99-118 / 151-167 / 204-218`；不 join 的位置見 [dataflow.md](dataflow.md) §6 |
| P7 舊模組移除條件 | 路徑改變 | 引用者從 `mobile_server.py` 變成 `mobile/state.py:13,16` |
| P8 派發用 if/elif 鏈、mixin 隱式耦合 | 仍成立 | `command_router.py:80-159`；SessionManager 防禦 tuple 在 `120-123` |
| P9 HttpClient 讀對話歷史 | 仍成立 | `http_client.py:25-28,109-119` |

| # | 狀態 | 現況 |
|---|---|---|
| P10-1 可觀測性（`created_at` 沒人用） | 仍成立 | `core/message.py:13` |
| P10-2 測試缺口 | 仍成立 | 見 [tests.md](tests.md) |
| P10-3 文件寫「unittest，非 pytest」 | **已修** | `docs/architecture/testing.md` 已改成 pytest 為主 |

報告總體評估裡「`app.py` 基本上是純接線」：`wire()` 已經抽到 `app_wiring/topology.py`，
但 `main()` 仍有業務初始化與呈現文字（見 [layering.md](layering.md) §3）。
