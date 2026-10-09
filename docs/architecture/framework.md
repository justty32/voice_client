# 架構文檔：資料隧道框架

[架構文檔入口](../architecture.md)

## 2. 資料隧道框架（`core/`）

框架本體不含任何業務邏輯，五個檔案各司其職：

| 檔案 | 職責 |
|---|---|
| `core/message.py` | `Message` 資料類別：`topic`、`payload`、`source`、`created_at` |
| `core/endpoint.py` | `Outbox`（模組→交換核心）／`Inbox`（交換核心→模組），模組與核心的唯一介接點 |
| `core/exchange.py` | `Exchange`：路由表（topic → 消費者 inbox）＋單執行緒交換迴圈；`routes()` 查詢已註冊 topic |
| `core/module.py` | `TunnelModule` 基底類別：`attach`／`emit`／消費迴圈／錯誤隔離 |
| `core/adapter.py` | `OutboxAdapter`／`InboxAdapter`：把既有模組的裸 queue 偽裝成 Outbox/Inbox，零改寫掛上 Exchange |

### 2.1 交換語意

- **一次一筆**：`Exchange.tick()` 每次最多搬移一筆訊息（Outbox → Inbox）。
  所有佇列之間的搬移只發生在 Exchange 的執行緒，單點可觀測、無競態。
- **工作佇列**：每個 topic 只允許註冊一個消費者（重複註冊拋 `ValueError`）；
  每筆訊息恰好被一個消費者取走。
- **round-robin**：多個生產者輪流被服務，不會餓死後註冊者。
- **無消費者即丟棄**：訊息的 topic 沒有路由時記 warning 後丟棄。
- **錯誤隔離**：壞掉的 outbox 跳過不擋路；`tick()` 例外不會中斷交換迴圈。

### 2.2 模組模型（`TunnelModule`）

- 每個模組同時擁有 `outbox`（生產）與 `inbox`（消費）。
- **純生產者**：不宣告 `consumes`、不呼叫 `start()`，自己的背景執行緒直接 `emit()`。
- **消費者**：宣告 `consumes` 並覆寫 `handle()`；`start()` 後基底迴圈逐筆處理。
- **身兼兩者**：在 `handle()` 內 `emit()` 即可（例：CommandRouter 收指令、發控制訊息）。
- `handle()` 例外不會中斷消費迴圈：記 log 後交給可覆寫的 `on_handle_error()`，預設發 `ui_event` 系統訊息（含例外文字）。
- 接線慣例：**所有模組先 `attach(exchange)`，再 `start()`**（註冊非執行緒安全）。
