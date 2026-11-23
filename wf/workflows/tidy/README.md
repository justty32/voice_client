# tidy — 本 repo 的文件整理補充

通用流程與原則正本在 `$AOS_HOME/knowledge/wf/workflows/tidy.md` 與 `$AOS_HOME/knowledge/wf/workflows/tidy/principles.md`；本檔只保留本地工具與硬驗收。

## 資料檔與盤點

格式契約、A／B 拆法與讀寫規則見 [data-files](../common/data-files.md)，整理門檻見 [STRUCTURE](../../STRUCTURE.md)，本地踩坑見 [gotchas](gotchas.md)。盤點時從 repo 根執行：

```bash
python3 wf/tools/find_big_lists.py --min 1024 <dir>
python3 wf/tools/find_big_lists.py --links-only <dir>
find <dir> -name '*.md' -not -path '*/archive/*' -size +8192c
```

搬檔後用每批的 `moves.tsv` 跑 `wf/tools/fix_moved_links.py`，先 dry-run 再 `--apply`；資料檔契約與原始碼的目標判定以本 repo 工具為準。

## 本地驗收

- 交接書要求連結檢查時，從 repo 根跑 `bash wf/tools/wf-lint.sh --strict .`，TOTAL 各項為 0；預設可不跑，大量搬檔後或使用者要求才跑。`BIGLIST-LINKS` 只警告，不計入失敗。
- 整理範圍內 `find <dir> -name '*.md' -not -path '*/archive/*' -size +8192c` 無輸出。
- 子資料夾 `README.md` ≤ 300 行、入口 `README.md` ≤ 100 行；名冊／登記表 ≤ 8192 bytes；`SESSION-LOG.md` ≤ 4096 bytes 且只列 open。

內容精簡的判準與原文檢查見 `$AOS_HOME/knowledge/wf/knowledge/content-trim.md` 與 `$AOS_HOME/knowledge/wf/workflows/tidy/content-trim.md`。要派管理線時，另附 [manager-brief](manager-brief.md) 的本地補充；要使用者裁示的事交窗口記入根層 `WAIT_USER.md`。
