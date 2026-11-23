# manager-brief — 管理線的本地補充

管理線通用流程正本在 `$AOS_HOME/knowledge/wf/workflows/tidy-manager-brief.md`；本檔只補本 repo 的資料檔與驗收要求。

- 盤點與 A／B 分類前讀 [data-files](../common/data-files.md)；每個工人的交接書附本地資料檔規則。
- 每批由管理線自己驗：`wc -c` 確認入口 ≤ 8192 bytes，資料檔列數與原表對帳；其餘本地門檻見 [tidy](README.md)。
- 大量搬檔後或使用者要求時，從 repo 根跑 `bash wf/tools/wf-lint.sh --strict .`；預設可不跑，執行時 TOTAL 各項為 0。

下屬配額、可用模型與 commit 權限照本次交接書及座位卡，不從通用簡報擴大權限。
