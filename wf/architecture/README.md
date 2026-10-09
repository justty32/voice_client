# 架構調查

[wf](../README.md)｜[WORKFLOWS](../../WORKFLOWS.md)

**現況架構的唯一事實來源**是 [docs/architecture.md](../../docs/architecture.md) 與
[CODE_MAP](../../workflows/common/code-map/CODE_MAP.md)；本資料夾不重述現況。

2026-10-09 重構前的現況調查（分層、資料流、兩條入口、legacy、測試覆蓋、報告查證、痛點排序）
已隨 refactor_next 落地封存，索引見 [archive/README.md](archive/README.md)。其結論已被重構吸收，
未修的殘留項目在 [roadmap](../../workflows/roadmap/README.md) 與 [ideas](../../workflows/idea/ideas.md)。

## 下一次架構調查怎麼做

1. 以 codemap 取得機器可讀的現況，不靠舊快照：

   ```bash
   python workflows/common/code-map/codemap.py big          # 大檔
   python workflows/common/code-map/codemap.py topics       # topic 生產者／消費者
   python workflows/common/code-map/codemap.py deps <模組>  # 依賴方向
   python workflows/common/code-map/codemap.py show <路徑>  # 單檔摘要
   python workflows/common/code-map/codemap.py json         # 全量
   ```

2. 逐檔讀程式碼查證，每個論點附 `path:line` 或可重跑的指令；記下基準 commit 與測試數。
3. 調查結果寫成本資料夾下的日期子資料夾 `YYYY-MM-DD-<主題>/`（附 README），只放問題與證據；
   解法交給 `plans/`。調查被重構吸收後，整包移入 `archive/` 並在其 README 加列。
4. 發現與 docs／CODE_MAP 衝突時，以程式碼為準，修正交給維護鏈（`程式碼 → CODE_MAP → docs → README`）。
