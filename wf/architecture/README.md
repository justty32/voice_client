# 現況架構調查

[wf](../README.md)｜[WORKFLOWS](../../WORKFLOWS.md)

- 調查日期：2026-10-09
- 基準：`refactor/data-tunnel` 分支 commit `733e32c`，**加上未提交的工作樹**（拆檔：`app_wiring/`、`mobile/`、`tts/`、
  拆小的測試檔；文件整理）。行號以當時的工作樹為準。
- 測試：`.venv/bin/python -m pytest -q` → 358 passed, 9 subtests passed
- 方法：`python workflows/common/code-map/codemap.py [json|big|topics|deps|show]` 取得依賴與 topic 圖，再逐檔讀程式碼查證。
  所有論點都附 `path:line` 或可以重跑的指令。
- 性質：只調查，未改程式碼。是下一步「重構計畫」的事實基礎，搭配 `reports/` 一起讀。

## 目錄

<!-- wf-nav -->
- [layering.md](layering.md)：分層與依賴方向、規則檢查（core／app.py）、循環依賴、根層分類、共享可變物件
- [dataflow.md](dataflow.md)：桌面 topic 協定總表（生產者→消費者、payload）、legacy Adapter vs 原生模組、啟停順序、Exchange 能力邊界
- [entrypoints.md](entrypoints.md)：桌面與手機兩條入口的結構對照、手機依賴的舊元件、重複邏輯、行為差異
- [legacy.md](legacy.md)：`text_accumulator`／`workspace_controller` 的引用者、死碼、`ai_assist/`／`server_sample/` 的定位
- [tests.md](tests.md)：測試覆蓋地圖（有測試／淺層／沒有測試）、測在舊路徑上的比例
- [verification.md](verification.md)：`reports/bug-review.md`、`reports/architecture-improvements.md` 每一條在現況是否仍成立
- [pain-points.md](pain-points.md)：依影響排序的結構痛點（只列問題與證據，不含解法）

## 摘要

桌面主線的 Data Tunnel 骨架是健全的：`core/` 在 import 層面零業務依賴，非測試模組之間沒有循環依賴，
`wire()` 已抽到 `app_wiring/topology.py` 成為純接線。但有三點：隧道只覆蓋「佇列搬移」；
`SessionManager`／`Workspace` 仍被多條執行緒直接呼叫而且沒有鎖；9 個 legacy I/O 模組靠 Adapter 接入，
失敗時大多靜默，不會回報上游。

最大的結構債是**雙入口雙實作**。手機入口（`mobile_server.py`＋`mobile/`）完全沒用 `core/`、`modules/`，
靠 `text_accumulator.py`、`workspace_controller.py` 與內嵌的 if/elif 把聊天、對話、工作區、/send 邏輯
重寫了一份，至少已有 10 項可查證的行為差異；它在 `.venv` 中無法匯入（缺 fastapi／uvicorn），
而且匯入就會建立所有元件，所以 0 測試。另外，79 個測試（22%）保護的是只有手機在用的舊工作區實作。

其次，協定（topic 名稱、payload 鍵、指令集）沒有單一事實來源，文件已經漂移；`app.py:main()`
與 `mobile/state.py` 重複了組裝與設定解讀；Exchange 只支援一個 topic 一個消費者、沒有 unregister，
撐不起動態的 WebSocket 消費者。根層仍有 17 個 `.py` 扁平排放，而且 `text_to_voice`／`app`／`mobile_server`
都是「根層入口＋套件」的拆法。

兩份 2026-07-02 報告的 14 個 bug 與 P1–P10 在現況**全部仍成立**（多數只是路徑或行號改變）；
唯一已修的是測試文件改成 pytest（[verification.md](verification.md)）。
