# STRUCTURE — 本專案的結構整理補充

只在重構／整理結構時讀。通用組織原則正本在 `$AOS_HOME/knowledge/wf/`（layers.md、nodes.md、tidying.md）；本檔只保留本 repo 的落點、門檻與工具契約，不另複製通用流程。

## 本專案的落點

- 根層 `WORKFLOWS.md` 與 `INDEX.md`、既有 `workflows/` 繼續負責專案派發與導航；既有檔案維持 `.md`，不因套用通用規則改名或搬家。
- 活進度記 `SESSION-LOG.md`，等使用者的記 `WAIT_USER.md`；兩者只列 open、完成即刪。膨脹時分別拆到 `session_logs/`／`wait-user/`，hub 只留導航表；決定記 `wf/workflows/decisions.md`。
- archive 的既有 md 索引維持 `README.md`，只追加列。依交接協議使用的 `done/`、`superseded/`，以及放寄件原文的 `inbox/` 也視為封存、不套門檻、lint 不下鑽；`workflows/inbox/` 是工作流文件，仍照掃。

## 日誌寫法

本 repo 的每日檔用 `session_logs/<月>/<日期>.md`、總目錄用 `session_logs/README.md`、月摘要用 `session_logs/<月>.md`；通用寫法見 `$AOS_HOME/knowledge/wf/layers.md` 的「日誌寫法」。

## 本專案的整理門檻

門檻是觸發檢視的訊號，不是所有檔案的硬上限；不可分的單體可保留並說明理由。

- `workflows/` 流程文檔單檔超過 8192 bytes，由 `wf-lint` 掃描。
- 使用手冊／產品文檔單檔超過 300 行、程式碼單檔超過 300 行，檢視是否按職責拆分。
- 同質條列區塊（表格／清單，每列同一組欄位）超過 1024 bytes，抽成資料檔。連結表不看 bytes，超過十條才考慮：給人導航的留 md、依一般 8 KB 門檻分層；給 AI 消化的才抽資料檔。

## 資料檔與驗證

資料檔契約 `wf-table/1`、A／B 拆法與讀寫工具在 [data-files](workflows/common/data-files.md)；跨層路徑代號 `$fmt` 見 [data-files-fmt](workflows/common/data-files-fmt.md)。

通用整理流程見 `$AOS_HOME/knowledge/wf/workflows/tidy.md`。本 repo 有 `wf/tools/wf-lint.sh`、`find_big_lists.py`、`tabledb.py`、`fix_moved_links.py`；交接書要求連結與資料檔檢查時使用這些工具，驗收指令與範圍以交接書為準。
