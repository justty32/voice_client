# 使用手冊：斜線指令與語音指令

[使用手冊入口](../user_manual.md)

## 6. 斜線指令

直接在終端機輸入框打就能用。

### 6.1 內容操作（作用於當前工作區）

| 指令 | 功能 |
|---|---|
| `/ws [名稱]` | 不帶名稱列出工作區（標示當前）；帶名稱切換當前工作區 |
| `/show` | 看當前工作區內容（有編號） |
| `/clear` | 清空當前工作區 |
| `/clear ui` | 清畫面顯示（不清工作區） |
| `/clear buffer`、`/clear stt`、`/clear chat` | 清指定工作區 |
| `/del <編號>` | 刪掉指定那一筆 |
| `/move <來源> <目標>` | 把某筆移到指定位置 |
| `/to_top [編號]` | 把那筆（預設最後一筆）移到最前面；編號從 1 起算，`0` 或負數只回報用法 |
| `/concat` | 把多筆壓成一筆 |
| `/copy` | 複製當前工作區到系統剪貼簿 |
| `/paste` | 從剪貼簿貼進來（每行一筆；chat 不支援） |
| `/export <檔名>` | 匯出工作區為 JSON |
| `/import <檔名>` | 從 JSON 匯入 |
| `/send` | 把 buffer 送給 LLM（只能在 buffer 用） |

### 6.2 對話管理

| 指令 | 功能 |
|---|---|
| `/new [名稱]` | 新建對話；省略名稱時用第一個未用的 `session_N`（N 從 1 起）；名稱已存在時回「對話已存在」且不覆蓋，請改用 `/switch` |
| `/switch [名稱]` | 切換對話（預設 default） |
| `/list` | 列出所有對話 |
| `/rename <舊> <新>` | 改名 |
| `/delete <名稱>` | 刪除對話 |
| `/history` | 看目前對話的歷史 |
| `/save [檔名]` | 存到檔案 |
| `/load <檔名>` | 從檔案載入 |

### 6.3 其他

| 指令 | 功能 |
|---|---|
| `/stop` | 停止 TTS 朗讀 |
| `/help` | 指令一覽 |
| `/exit` | 離開程式 |

以上三張表合起來就是完整的斜線指令集，與程式的單一來源 `protocol/commands.py` 一致（`tests/test_protocol_commands.py` 比對）。

不加斜線直接打文字按 Enter，就是把這段文字加入當前工作區（和 F8 錄音進來一樣）。

---

## 7. 語音指令模式（F7）

按 F7 開始錄音、再按 F7 停止，辨識到的文字不會進工作區，而是被解析成指令。

支援的關鍵字（說中文或英文都可以）：

| 說出來的話 | 對應指令 |
|---|---|
| 發送、傳送、send | `/send` |
| 清除、clear | `/clear` |
| 顯示、show | `/show` |
| 停止、stop | `/stop` |
| 工作區、workspace | `/ws` |
| 新建、開啟對話、new | `/new` |
| 切換、switch | `/switch` |
| 列表、list | `/list` |
| 刪除、delete | `/delete` |
| 保存、儲存、save | `/save` |
| 歷史、紀錄、history | `/history` |
| 複製、copy | `/copy` |
| 貼上、paste | `/paste` |
| 壓縮、連接、concat | `/concat` |
| 置頂、to top | `/to_top` |
| 匯出、export | `/export` |
| 匯入、import | `/import` |
| 幫助、說明、help | `/help` |
