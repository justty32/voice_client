from fastapi import FastAPI, BackgroundTasks
from pydantic import BaseModel
import uvicorn
import sys
from pathlib import Path

# 加入之前的非同步系統路徑
sys.path.append(str(Path(__file__).parent.parent / "07-async-orchestration"))
from async_system import AsyncSessionManager, AsyncOrchestrator

app = FastAPI(title="AI 助手輸入介面 API")

# 初始化核心組件 (設定 5 個工作執行緒)
orchestrator = AsyncOrchestrator(max_workers=5)
sm = AsyncSessionManager(orchestrator, storage_dir="./api_sessions")

class AppendRequest(BaseModel):
    content: str
    trigger: bool = True

@app.post("/session/{session_id}/append")
async def append_string(session_id: str, request: AppendRequest):
    """
    透過 API 向指定的 Session 加入新字串，並選擇是否觸發處理。
    範例: POST /session/user_input/append {"content": "hello", "trigger": true}
    """
    success = sm.append(session_id, request.content, trigger=request.trigger)
    return {
        "status": "success" if success else "backpressure_limit",
        "session_id": session_id,
        "current_history_count": len(sm.get_session(session_id))
    }

@app.get("/session/{session_id}")
async def get_history(session_id: str):
    """讀取特定 Session 的完整歷史紀錄"""
    return {
        "session_id": session_id,
        "history": sm.get_session(session_id)
    }

if __name__ == "__main__":
    print("=== [實驗] AI 助手 REST API 伺服器啟動 ===")
    print("可以使用 curl 測試: curl -X POST http://127.0.0.1:8000/session/web_input/append -H \"Content-Type: application/json\" -d '{\"content\": \"來自 API 的指令\", \"trigger\": true}'")
    uvicorn.run(app, host="127.0.0.1", port=8000)
