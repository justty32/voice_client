# tidy／gotchas — 本專案工具的整理踩坑

通用踩坑正本在 `$AOS_HOME/knowledge/wf/knowledge/gotchas.md`；本檔只留 `wf-table/1` 與本 repo lint 的補充。資料檔契約見 [data-files](../common/data-files.md)。

## 拆檔與資料檔

<!-- wf-nav -->
- `link_columns` 只列**整格＝相對路徑或單一 md 連結**的欄。把散文欄（`body`、`理由`、`機制`）或機外路徑欄列進去，lint 會把整格當路徑驗、報大量假斷鏈；散文裡的 md 連結所有欄本來就會掃，不必標。
- 入口壓在 8192 邊緣時再改一個字就爆；改字前先 `wc -c`。`wc -c … | awk '$1>8192'` 會被 total 行騙，用 `find -size +8192c`。
- 用空行把清單切塊躲 BIGLIST 不算解；檢查器會把單一空行分隔的塊併起來。導航清單加 `<!-- wf-nav -->`，同質記錄抽資料檔。
