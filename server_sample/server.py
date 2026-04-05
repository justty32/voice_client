import logging
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import requests
import uvicorn

# 設置日誌
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("VoiceClientServer")

app = FastAPI(title="Voice Client Sample Server")

# Ollama 設定
OLLAMA_BASE_URL = "http://localhost:11434"
DEFAULT_MODEL = "gemma3:12b"

class ChatRequest(BaseModel):
    Content: str
    Title: str = "default"
    Metadata: dict = {}

@app.post("/chat")
async def chat_endpoint(request: ChatRequest):
    """
    接收 Voice Client 的請求，轉發給本地 Ollama 並回傳相容格式。
    """
    logger.info(f"Received request from session: {request.Title}")
    
    # 這裡可以根據需要載入系統提示詞
    # 簡單起見，我們直接透傳 User Message
    ollama_payload = {
        "model": DEFAULT_MODEL,
        "messages": [
            {"role": "user", "content": request.Content}
        ],
        "stream": False
    }

    try:
        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=ollama_payload,
            timeout=60
        )
        response.raise_for_status()
        result = response.json()
        
        reply_text = result.get("message", {}).get("content", "")
        
        # 回傳 Voice Client 預期的格式
        return {
            "type": "ChatReply",
            "Title": request.Title,
            "Content": {
                "full_response": reply_text
            },
            "model": DEFAULT_MODEL
        }
        
    except requests.exceptions.RequestException as e:
        logger.error(f"Ollama call failed: {e}")
        raise HTTPException(status_code=500, detail=f"Ollama error: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
