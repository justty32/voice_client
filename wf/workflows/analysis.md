# analysis — 陌生專案分析入口

[WORKFLOWS](../../WORKFLOWS.md)｜[INDEX](../../INDEX.md)

用於初次接觸外部 repo、開源專案、舊系統或大型資料夾時，建立可延續、可搬移、可被後續 patch／planning 使用的分析產物。

**何時用**：初次接觸陌生專案，需要建立可供後續工作延續的架構與能力分析。
**何時不用**：只回答一個窄問題 → [investigation](../../workflows/investigation/README.md)；只是閱讀論文／規格／文章 → research 包（若有導入）；已在目標 repo 內實作功能 → [feature-dev](../../workflows/feature-dev/README.md)。

## Done when

- `analysis/<project>/session_log.md` 與指定 Level 的分析檔存在。
- 主要入口、核心模組與測試方式的表格已填滿。
- README 指定的 build／run／test 指令回傳 0。

## 流程

1. 初始化 `analysis/<project>/` 與 `session_log.md`。
2. Level 1 初始探索：README、頂層結構、依賴、入口點、build／run／test 指令。
3. Level 2 核心模組職責：主要模組、權責劃分、耦合點、資料流。
4. Level 3+ 依專案類型選模板深入。
5. 將可行功能或缺口導向 [planning](../../workflows/specs/README.md)；將可套用修改導向 [patch](patch.md)。

## 產物結構

建議放在 `analysis/<project>/`：

| 路徑 | 內容 |
|------|------|
| `architecture/` | Level 1–6 架構分析 |
| `tutorial/` | 「如何做到 X」的目標導向教學 |
| `answers/` | 一次性具體問答 |
| `details/` | 單點深入剖析 |
| `others/` | 雜項與反向連結 |
| `session_log.md` | 一句話操作日誌，建議上限 50 行 |
| `html/` | 選用導覽層 |

## Level 3+ 模板

| 類型 | 關注點 |
|------|--------|
| 遊戲／引擎 | game loop、資源、渲染、AI、玩法、存檔 |
| 嵌入式／IoT | 控制迴圈、ISR、通訊、硬體抽象、即時性 |
| Web／API | routing、middleware、domain／service、DB、auth、queue |
| 前端／桌面 | routes、components、state、API client、style、build |
| CLI／SDK／library | command／API surface、config、I/O、plugin、release |
| 資料／ML | connector、schema、pipeline、training、serving、monitoring |
| DevOps／IaC | module、environment、CI/CD、secret、observability |

## 寫作規則

- 技術結論附來源位置：`path:line`、函式名、URL、論文 id 或命令摘要。
- 教學文件要包含：前置知識、原始碼導航、實作步驟、驗證方式。
- 圖表用 Mermaid、表格、列點；不要用 ASCII 框線圖。

## 交接

- 可行功能或缺口 → [planning](../../workflows/specs/README.md)；可獨立套用的修改 → [patch](patch.md)。
- 窄問題 → [investigation](../../workflows/investigation/README.md)；需使用者驗證 → [WAIT_USER](../../WAIT_USER.md)。
