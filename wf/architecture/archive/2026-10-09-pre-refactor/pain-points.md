> 封存 2026-10-09，由 docs/architecture.md 與 workflows/common/code-map/CODE_MAP.md 取代（重構前快照，refactor_next 已落地）

# 痛點總結（依影響排序）

[入口](README.md)

這裡只列結構問題與證據，不提出解法（解法交給重構計畫）。排序依據：對正確性與資料的影響
→ 對後續重構的阻礙程度 → 維護成本。

## 1. 雙入口雙實作：手機繞過 Data Tunnel

手機入口沒有用 `core/`、`modules/`，自己用一套 queue 輪詢＋舊工作區實作，把聊天、對話、工作區、
/send 邏輯重寫了一份（[entrypoints.md](entrypoints.md) §3，8 組重複），而且已經出現至少 10 項可查證的
行為差異（同檔 §4）。舊模組 `text_accumulator.py`、`workspace_controller.py` 只因手機而存在
（`mobile/state.py:13,16`），並用掉 79 個測試（[tests.md](tests.md) §4）；手機本身 0 個測試，
`.venv` 裡也無法匯入。

## 2. 共享可變狀態不走隧道，而且沒有鎖

`SessionManager` 被 3 條執行緒直接呼叫，`Workspace` 被 WM 與 CommandRouter 兩條執行緒同時操作，
都沒有鎖（[layering.md](layering.md) §4）。已確認的後果：語音文字遺失（B3）、sessions 檔損毀後
歷史全部歸零（B4，`session_manager.py:40-42,84-85`）。手機的 `_wsc.stt` 也有相同模式。

## 3. 錯誤與狀態沒有閉環

legacy I/O 模組失敗時只記 log，不回報上游：Kokoro worker 死亡（B2）、STT 模型載入失敗（B7）、
靜音錄音（B8）、摘要失敗（B14）都會讓 UI 卡住或沒有聲音，而且沒有提示。框架層的錯誤只發固定文字
（`core/module.py:59-63`），沒有結構化的錯誤 topic。

## 4. 協定沒有單一事實來源

topic 名稱、payload 鍵、ui_event role 都是散落的字面字串；控制 topic 字串和 dict 兩種風格混用；
斜線指令集有 3 份（手機再 1 份）（[dataflow.md](dataflow.md) §5）。文件已經漂移：`tts` 的生產者
（`docs/architecture/topics.md`）、「stop 以 join 收尾」（`docs/architecture/runtime.md`）都與程式不符。
目前沒有契約測試能抓出這類漂移。

## 5. 組裝與生命週期分散

`app.py:main()` 手寫建構、start、stop 三份清單（`app.py:99-118,151-167,204-218`）；legacy 的 `stop()`
不 join；停機沒有 drain；兩處繞過隧道直接放進 queue（`app.py:172-185,203`）。default session、
export_dir、SLM 設定的解讀在 `app.py` 與 `mobile/state.py` 各寫一份（[layering.md](layering.md) §3），
SLM.enabled 還被 `summary_generator.py:24` 另外讀一次。手機則是匯入時就建立所有元件（`mobile/state.py:18-46`）。

## 6. I/O 層與業務邏輯互相滲透

`HttpClient` 持有 `SessionManager` 並自己組歷史上下文（`http_client.py:25-28,109-125`；B1 的 bug 就出在這裡）；
`WorkspaceCommandMixin` 在業務 handler 內直接同步呼叫本機剪貼簿（`command_handlers/workspace.py:131,138`），
所以手機無法共用；`modules/cli_text_bridge.py:16` 依賴輸入裝置模組的常數。

## 7. Exchange 能力不足以承載第二個前端

一個 topic 只能有一個消費者、沒有 unregister、queue 無上限（`core/exchange.py:30-33`、`core/endpoint.py:14,30`）。
手機需要的「每條連線一個 WS 消費者」以及 `ui_event` 廣播，用現有 API 都做不到；`audio` 也沒有背壓。

## 8. 根層扁平、同一元件拆在兩層

根層有 17 個 `.py`，入口、語音 I/O、終端介面、LLM I/O、領域資料、舊路徑、設定全部混在一起
（[layering.md](layering.md) §1）。`text_to_voice.py`+`tts/`、`app.py`+`app_wiring/`、`mobile_server.py`+`mobile/`
是「根層入口＋套件」的拆法，靠 re-export 維持舊匯入路徑（[legacy.md](legacy.md) §3）。
`modules/` 往回依賴根層的 `workspace.py`、`terminal_input.py`。

## 9. 測試網的空洞落在 I/O 與組裝

`http_client`、`summary_generator`、`terminal_input`、`keyboard_listener`、`tui_renderer`、`utils/*`、
`app.main()`、`mobile/*` 都沒有測試；`record`、`voice_to_text`、`text_to_voice` 只有淺層測試。
整合測試用假物件代替真實 I/O 模組（[tests.md](tests.md) §3、§5），所以真實 queue 協定沒有被驗證。

## 10. 非產品內容與死碼混在 repo

`ai_assist/`（另一個實驗專案）與 `server_sample/`（測試用對端伺服器）在 repo 根層受 git 追蹤，
`MUTE`/`UNMUTE`、`handle_copy`/`handle_paste`、`chunk_flushed`、`created_at` 等沒有消費者
（[legacy.md](legacy.md) §2–§4）。影響較小，但會干擾導航與 codemap 範圍判斷。
