# wf — voice_client 的工作文件補充

本夾保留本 repo 的組織與 aos 座位設定、架構調查、決策記錄、資料檔契約與檢查工具；既有文件維持 `.md`、原名與原位置，導航骨架在 `_index.json`。

通用規則正本在 `$AOS_HOME/knowledge/wf/`，不在本 repo 複製維護。工具不展開 `$AOS_HOME` 時，先用 shell `echo $AOS_HOME` 取得完整路徑。專案功能開發與測試仍從 [WORKFLOWS](../WORKFLOWS.md) 進入。

## 本專案內容

<!-- wf-nav -->
- [STRUCTURE](STRUCTURE.md)：本 repo 的整理門檻、狀態檔落點與資料檔工具補充。
- [組織](org/README.md)、[aos](aos/README.md)：座位分工、交接與執行定義。
- [架構調查](architecture/README.md)：現況來源與調查方法。
- [決策記錄](workflows/decisions.md)、[資料檔契約](workflows/common/data-files.md)、[回覆風格](workflows/common/reply-style.md)：本地記錄與尚未由 aos 收錄的規則。
- `tools/`：連結、資料檔與 index 等檢查；`bash wf/tools/wf-lint.sh --strict .` 依任務指定執行。

## 工具升級

`wf/tools/index_check_local.py`、`wf-lint-local.sh`、`test_index_check_local.py` 與 `_index.json` 是 project-owned，升級工具時保留。local hook 隨 `wf-lint.sh` 執行，只驗已有 index 的覆蓋與檔案目標，不強制每夾新增；略過 archive 內容、隱藏項、`__pycache__` 與 gitignore 項，但父索引仍列 archive 目錄。`index`／`$ref` 只驗 `#` 左側檔案存在，不驗片段。

## 舊路徑與正本

下表是來源對照，不是本地檔案的存在清單。`TEMPLATE.workflow.md`、`analysis.md`、`patch.md`、`refactor/moving-things.md`、`tidy/content-trim.md` 已移除，改讀 aos 正本；其餘同名檔只保留本地補充或記錄。空的 `workflows/refactor/` 與其 index 一併移除，沒有搬移或改名既有文件。

<!-- wf-nav -->
| 舊路徑（從 wf/ 算） | aos 正本 |
|---|---|
| `STRUCTURE.md` 的通用原則 | `$AOS_HOME/knowledge/wf/layers.md`、`$AOS_HOME/knowledge/wf/nodes.md`、`$AOS_HOME/knowledge/wf/tidying.md` |
| `workflows/TEMPLATE.workflow.md` | `$AOS_HOME/knowledge/wf/knowledge/workflow-template.md` |
| `workflows/analysis.md` | `$AOS_HOME/knowledge/wf/workflows/analysis.md`；產物骨架 `$AOS_HOME/knowledge/wf/skeletons/analysis.md` |
| `workflows/patch.md` | `$AOS_HOME/knowledge/wf/workflows/patch.md` |
| `workflows/refactor/moving-things.md` | `$AOS_HOME/knowledge/wf/workflows/moving-things.md` |
| `workflows/tidy/README.md` | `$AOS_HOME/knowledge/wf/workflows/tidy.md`、`$AOS_HOME/knowledge/wf/workflows/tidy/principles.md` |
| `workflows/tidy/content-trim.md` | `$AOS_HOME/knowledge/wf/workflows/tidy/content-trim.md`、`$AOS_HOME/knowledge/wf/knowledge/content-trim.md` |
| `workflows/tidy/manager-brief.md` | `$AOS_HOME/knowledge/wf/workflows/tidy-manager-brief.md` |
| `workflows/decisions.md` 的流程 | `$AOS_HOME/knowledge/wf/workflows/decisions.md` |
| `workflows/tidy/gotchas.md` 的通用條目 | `$AOS_HOME/knowledge/wf/knowledge/gotchas.md` |
