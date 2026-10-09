# patch — 獨立 patch 小專案入口

[WORKFLOWS](../../WORKFLOWS.md)｜[INDEX](../../INDEX.md)

建立一包可被 agent 套用到原專案的獨立 patch，交給沒有聊天上下文的接手者套用與驗證。

**何時用**：修改需跨 repo 交付、原專案無法直接推送，或要交給冷啟動 agent 套用。
**何時不用**：能在同一 repo 直接改碼、跑測試、commit → [feature-dev](../../workflows/feature-dev/README.md)；只交付設計方案 → [planning](../../workflows/specs/README.md)；原專案有正常 PR 流程且會直接開 PR → 使用該 repo 的既有流程。

## Done when

- `patches/<patch>/PATCH.md`、`APPLY.md`、`session_log.md`、`src/` 與 `tests/` 存在。
- `PATCH.md` 的必答表格與 `APPLY.md` 的套用對照表已填滿。
- `APPLY.md` 指定的構建與功能驗證指令回傳 0。

## 流程

1. 確認下方前置條件，建立 `patches/<patch>/` 產物骨架。
2. 在 `PATCH.md` 填清目標、範圍、預期結果與分析依據。
3. 依 `src/` 策略放入可套用檔案，並在 `tests/` 放驗證腳本或說明。
4. 寫完 `APPLY.md`，依其中步驟實際套用並跑構建與功能驗證。

## 前置條件

- 已有 [analysis](analysis.md) 產出的 `analysis/<source>/` Level 1–2 以上分析，或等價的原專案結構理解。
- 已明確 patch 目標、影響範圍、驗證方式。

## 產物結構

建議放在 `patches/<patch>/`：

| 路徑 | 內容 |
|------|------|
| `PATCH.md` | 目標、修改類型、影響範圍、分析依據 |
| `APPLY.md` | 冷啟動 agent 套用操作手冊 |
| `session_log.md` | 一句話操作日誌，建議上限 50 行 |
| `src/` | 最終要套用的完整檔案，模擬原專案相對路徑 |
| `tests/` | 驗證腳本或驗證說明 |

## PATCH.md 必答

| 項目 | 必填內容 |
|------|----------|
| 目標專案 | 名稱、路徑或 URL |
| 修改類型 | 功能增強、bug 修正、重構或實驗 |
| 影響範圍 | 受影響的模組或檔案 |
| 預期結果 | 可量測或可觀察的變化 |
| 分析依據 | 主要參考的 analysis／research 文件 |

## src/ 策略

- 新增檔案：放完整新檔案。
- 修改檔案：優先放修改後完整檔案，而不是 diff。
- 刪除檔案：在 `APPLY.md` 清楚列步驟。
- 配置變更：放修改後完整配置檔，或在 `APPLY.md` 說明局部修改。

## APPLY.md 標準結構

```md
# APPLY.md — <Patch 名稱>

## 摘要
<一句話說明做了什麼、為什麼>

## 前置條件
- 目標專案路徑或 URL
- 依賴的分析文件
- 套用前需確認事項

## 套用步驟
1. 備份或確認 git 狀態。
2. 複製新增／修改檔案，提供對照表。
3. 列出需手動修改的部分。
4. 跑構建驗證。
5. 跑功能驗證。

## 回退方式
<如何還原>

## 已知限制
<平台、版本、未驗證項>
```

`APPLY.md` 必須讓沒有聊天上下文的 agent 也能獨立完成。

## 交接

- 套用後仍能在同一 repo 內繼續修改與驗證 → [feature-dev](../../workflows/feature-dev/README.md)。
- 發現結構理解不足 → [analysis](analysis.md)；只剩方案缺口 → [planning](../../workflows/specs/README.md)。
