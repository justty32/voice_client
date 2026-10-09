# 下一步重構計畫（refactor_next）

- 擬定日期：2026-10-09
- 事實基礎：[wf/architecture/](../../wf/architecture/README.md)（現況調查、[痛點排序](../../wf/architecture/pain-points.md)、
  [報告查證](../../wf/architecture/verification.md)）；`reports/bug-review.md`（B 編號）、`reports/architecture-improvements.md`（P 編號）。
- 起點：分支 `refactor/data-tunnel` 含未提交工作樹。基準 `.venv/bin/python -m pytest -q` → **358 passed, 9 subtests passed**。
- 性質：施工單。每階段一檔、可獨立 commit、完成後全套測試仍綠；不看對話也能照做。

## 原則（每階段都適用）

1. 動工前 `git status`；工作樹既有修改屬於使用者，不要混進階段 commit。
2. 預設 behavior-preserving；階段檔內標 **【改行為】** 的項目才允許改變可觀察行為，且必須列出新增測試。
3. 自動驗證不需要麥克風／喇叭／手機；需要真機的項目只進下方「WAIT_USER 候選」，不當作階段驗收。
4. topic 或 payload 一旦變動，同一個 commit 內同步：生產者、消費者、`app_wiring/topology.py`、接線測試、`docs/architecture/topics.md`、`protocol/`。
5. 每階段結束必跑：

```bash
.venv/bin/python -m pytest -q                         # 全綠；測試數 ≥ 上一階段 + 該階段新增數
python -m compileall -q -x '/(\.venv|\.git)/' .       # 無輸出
python workflows/common/code-map/codemap.py topics    # 與 protocol/topics.py、docs 一致（階段 1 起由測試機械比對）
bash wf/tools/wf-lint.sh .                            # broken=0（有改文件時）
```

6. 維護鏈：`程式碼／測試 → CODE_MAP → docs/architecture/* → README`；新增或刪除檔案必改 CODE_MAP。
7. 不可逆動作（刪目錄、刪 `output/`、改 `config.ini`）一律不做；刪程式檔只在決策點明示的階段做。

## 階段清單（依「風險低 → 解鎖後續 → 價值高」排序）

| # | 檔 | 一句話 | 行為 |
|---|---|---|---|
| 0 | [stage0-baseline.md](stage0-baseline.md) | 文件基準校正（測試數、runtime 停機敘述、ui_events 註解） | 保持 |
| 1 | [stage1-protocol.md](stage1-protocol.md) | 協定單一事實來源：`protocol/` 套件＋契約測試（wire／codemap／docs 三方比對） | 保持 |
| 2 | [stage2-io-tests.md](stage2-io-tests.md) | I/O 層測試安全網＋三個邊界 bug（B1、B9、B13） | 局部改 |
| 3 | [stage3-locks.md](stage3-locks.md) | 共享狀態加鎖、原子落盤、壞檔備份（B3、B4）＋同名對話不覆蓋（B5） | 局部改 |
| 4 | [stage4-error-loop.md](stage4-error-loop.md) | 錯誤與狀態閉環：`stt_event` topic、錄音靜音復位、摘要失敗 fallback、Kokoro 死亡偵測（B2、B7、B8、B14、P5） | 改 |
| 5 | [stage5-assembly.md](stage5-assembly.md) | 組裝與生命週期：`build_core()`、啟停註冊表、legacy `stop()` join、設定解讀共用 | 保持 |
| 6 | [stage6-dispatch.md](stage6-dispatch.md) | 指令集單一來源＋派發表＋小型死碼（P3-4、P8） | 保持（`/to_top 0` 例外） |
| 7a | [stage7a-mobile-testable.md](stage7a-mobile-testable.md) | 手機可測試化：lazy 組裝、`create_app()`、單一 pusher（B6）、TestClient 測試 | 保持 |
| 7b | [stage7b-mobile-tunnel.md](stage7b-mobile-tunnel.md) | 手機走 Data Tunnel：共用 `build_core`、WS 邊緣轉接；舊模組停用／移除（P1、P7） | 改（對齊桌面） |

階段 0–6 只需 `.venv` 現狀即可自動驗證；階段 7 依賴決策 D2。
階段 2、3、4 之間彼此獨立，可依需要調整先後；5 依賴 1；6 依賴 1；7a 依賴 5；7b 依賴 1、3、4、5、6、7a。

## 決策點（使用者未回覆時照「預設」推進）

| # | 問題 | 預設（不可逆的事一律不做） | 影響階段 |
|---|---|---|---|
| D1 | `ai_assist/`、`server_sample/` 是否刪除或搬移 | **不刪不搬**。只在 `INDEX.md` 加一行標註「非產品內容／測試對端」；codemap 已排除 | — |
| D2 | 是否在 `.venv` 安裝 `fastapi`、`uvicorn` 以測手機路徑 | **安裝**（`requirements.txt` 本來就列；`.venv/bin/pip install fastapi uvicorn`；可 `pip uninstall` 還原）。不裝則 7a/7b 停做 | 7a、7b |
| D3 | 手機對齊方式 | **A：共用 `build_core()`＋WS 邊緣轉接、單一全域 pusher**（不需 Exchange fan-out）。B「保留獨立實作只共用 handler」不選：仍是雙實作 | 7b |
| D4 | 是否刪 `text_accumulator.py`、`workspace_controller.py` 與其 79 個測試 | **先不刪**：7b 完成後產品碼零引用、CODE_MAP 標 deprecated、測試保留；使用者點頭後再以一個獨立 commit 刪除 | 7b |
| D5 | `new_session` 同名策略 | **拒絕並回報「對話已存在」，不覆蓋**；自動編號改找第一個未用的 `session_N` | 3 |
| D6 | STT 成功輸出文字後，狀態列是否回「待機」 | **是**（「處理中」指 STT 處理；完成即待機） | 4 |
| D7 | Kokoro worker 死亡後 | **清狀態＋自動重啟一次**（上限 1）；再死則放棄並 log error，之後任務記 log 丟棄 | 4 |
| D8 | 根層 17 個 `.py` 歸入套件的 layout | **本輪不做**（見下）。提案：`speech/`（record、voice_to_text、text_to_voice＋tts）、`ui/`（terminal_input、keyboard_listener、local_control、tui_renderer）、`llm/`、`domain/`（workspace、session_manager） | — |
| D9 | 手機與桌面文案不一致時以誰為準（`/list` 尾行、Error role、`/switch` 自動建 default…） | **以桌面為準**；手機差異表見 [entrypoints.md §4](../../wf/architecture/entrypoints.md) | 7b |
| D10 | 手機停機時是否仍自動匯出 buffer 到 `_buffer_temp.json` | **保留**（在 mobile lifespan 關閉段用 `WorkspaceManager` 的 buffer 匯出） | 7b |

## 本輪不做（與理由）

- **P4 Exchange fan-out／unregister／背壓**：D3 的單一全域 pusher 不需要 fan-out；`audio` 背壓參數要真機調；核心改動風險高。要「桌面＋手機同時呈現」時再開案。
- **P9 `outbound` 攜帶 history**：階段 3 的鎖已消除競態；屬 `outbound` 協定變更且影響兩條入口，留到 7b 之後。
- **B11 SttGate 與在途 STT 的順序競態**：產品語意裁示（audio 是否帶模式標記）且只能真機重現。列 WAIT_USER。
- **B10 Recorder 待機不讀 stream**：修法簡單（START 先清殘留）但效果只能真機聽；列 WAIT_USER。
- **結構化 `error` topic**（P5 完整版）：先以 ui_event 帶例外訊息（4a）；專用 topic 等有第二個消費者再加。
- **工作區變更全部走 topic（request/reply）**：鎖已解決正確性，工程量大。
- **D8 根層歸入套件**：layout 是使用者偏好，且 7b 會改變根層檔案集合。搬 `text_to_voice.py` 時 `Path(__file__)` 推 Kokoro 模型目錄會移位（`text_to_voice.py:58-60`），屆時改以專案根為基準。
- **`plans/mobile_improve.md` 的 UX 項目**：不是重構。

## WAIT_USER 候選（階段落地後請使用者真機驗證；寫進 `WAIT_USER.md` 時標「未驗證」）

- 階段 4：靜音錄音後狀態列回「待機」；STT 模型載入失敗時畫面有錯誤訊息；Kokoro worker 被殺後 TTS 是否恢復（D7）。
- 階段 4／5：legacy `stop()` 改 join 後關機是否仍有 ALSA 噪音或 traceback（B9 修後 LocalControl 不應印 AssertionError）。
- 階段 6：KDE Wayland（`local_control.py`）與 X11 `pynput` 熱鍵五個訊號在派發表改寫後仍可用。
- 階段 7b：手機 WS 協定（`tts`、`tts_control`、`clipboard_*`、`sessions`）、錄音上傳、剪貼簿往返、重連只保留最新連線（B6）。
- 本輪不做但可請使用者觀察：B10（首句夾帶舊音訊）、B11（F7/F8 快速連按時語音指令被當文字）。

## 收尾

- 全部完成：本資料夾移到 `plans/archive/`（檔頭加封存行、archive README 加列）；`docs/architecture/migration.md` 「待清理／待對齊」收斂；`workflows/feature-dev/landed/README.md` 加一行。
- 跨 session 中斷：`SESSION-LOG.md` 只記「做到階段 N 的哪一步」，完成即刪。
