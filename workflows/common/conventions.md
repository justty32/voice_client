# 程式碼慣例與維護鏈

## 修改前

1. 讀 [CODE_MAP](code-map/CODE_MAP.md)，只展開相關領域。
2. 檢查 `git status`，保留使用者既有修改。
3. 找到現有測試與公開協定，再改實作。

## Python 慣例

- `app.py` 保持接線層，不放業務決策。
- `core/` 不依賴 Voice Client 業務模組。
- topic payload 是模組間協定；改格式時同步更新生產者、消費者、接線測試與架構文件。
- 長駐 worker 必須可停止，例外不可讓交換核心或其他 worker 一起退出。
- 硬體、網路與模型依賴應可替換或 mock，核心測試不可要求實際麥克風、喇叭或 LLM。
- 新依賴同步更新 `requirements.txt` 與 [tooling](../tooling/README.md)。

## 維護鏈

`程式碼／測試 → CODE_MAP → docs → README`

- 新增、刪除檔案或顯著改變職責時，更新 [CODE_MAP](code-map/CODE_MAP.md)。
- 改 topic、資料流、啟停順序時，更新 `docs/architecture.md`。
- 改使用者操作、指令或設定時，更新 `docs/user_manual.md` 與必要的 README。
- CODE_MAP 與程式碼衝突時，以程式碼為準並立即修正 CODE_MAP。
