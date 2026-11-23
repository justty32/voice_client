# wf — 通用工作流 kernel 補充包（非侵入式導入）

[WORKFLOWS](../WORKFLOWS.md)｜[INDEX](../INDEX.md)

來源：`~/repo/workflows`（wf-kernel v0.6＋未發布，上游 commit `519a4ba`，dev flavor）。
上游自 2026-11-13 起已決定併入 aos 知識庫，之後幾乎不再更新（見上游 `wf/SESSION-LOG.md` 第一條）。

本專案根目錄已有自己的工作流（`WORKFLOWS.md`、`workflows/`、`SESSION-LOG.md`、`WAIT_USER.md`），所以只把**專案還沒有的**
kernel 資產收進這裡；根層既有檔案不被取代，這裡的連結一律指回根層對應檔。

## 內容

| 路徑 | 用途 |
|---|---|
| [STRUCTURE.md](STRUCTURE.md) | 膨脹即拆、雜亂即分類的客觀門檻|
| [workflows/tidy/](workflows/tidy/README.md) | 文件整理流程 |
| [workflows/decisions.md](workflows/decisions.md) | 決策記錄 |
| [workflows/analysis.md](workflows/analysis.md) | 分析外部 repo／系統 |
| [workflows/patch.md](workflows/patch.md) | 對不能直接改的 repo 交付 patch |
| [workflows/refactor/moving-things.md](workflows/refactor/moving-things.md) | 搬檔改名修連結 |
| [workflows/TEMPLATE.workflow.md](workflows/TEMPLATE.workflow.md) | 新增工作流的範本 |
| [workflows/common/data-files.md](workflows/common/data-files.md) | 同質記錄表 > 1 KB 抽成資料檔|
| [workflows/common/reply-style.md](workflows/common/reply-style.md) | 對話回覆文風（參考，非 always-on）|
| [architecture/](architecture/README.md) | 架構調查入口（重構前快照已封存）|
| `tools/` | `wf-lint.sh`、`tabledb.py`、`fix_moved_links.py` 等 |

tidy 原則 5「內容精簡」（檔內只留現行結論、使用者原文逐字留）見
[workflows/tidy/content-trim.md](workflows/tidy/content-trim.md)。

未搬入（根層已有對應）：planning（→ idea／roadmap／specs／plans 管線）、investigation、
feature-dev、testing、dev-env、conventions、code-map、gotchas、user。

## 檢查

可選，預設不跑；大量搬檔改連結後或使用者要求才跑：

```bash
bash wf/tools/wf-lint.sh .
```

Claude Code 可用 `/wf-lint`（`.claude/commands/wf-lint.md`，`.claude/` 被 git ignore，只在本機）。

## 升級

`STRUCTURE.md`、`workflows/TEMPLATE.workflow.md`、`workflows/common/data-files*.md`、
`workflows/common/reply-style.md`、`workflows/tidy/`、`tools/`（整包）可從新版整檔覆蓋，
覆蓋後重跑 wf-lint 修回指向根層的連結；其餘照來源 repo 的 CHANGELOG 手動套。
專案自訂檢查放 `tools/wf-lint-local.sh`（project-owned，wf-lint 有就自動跑，整包覆蓋不會清掉；目前沒有）。
