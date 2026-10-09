"""
mobile_server.py — Mobile Web 版後端

FastAPI + WebSocket，讓手機瀏覽器連線使用語音客戶端。

與桌面共用 Data Tunnel：`build_core()` 的 Exchange＋原生模組（WorkspaceManager、SttGate、
CommandRouter、ChatFlow、CliTextBridge）＋VoiceToText、SummaryGenerator、HttpClient。
只替換邊緣：Recorder → MediaRecorder（前端）、TuiRenderer → HTML UI、
AudioPriorityPlayer → SpeechSynthesis（前端），見 mobile/edge.py。

本檔提供 `create_app(state)`（lifespan、static 掛載、`/`、`/ws`）與啟動入口；
狀態組裝在 `mobile.state.build_mobile_state()`，其餘細節在 mobile/ 套件。
匯入本模組沒有副作用：`__main__` 才載入 config、建立元件與 app。

連線語意（B6）：同時只服務最新的一條 WebSocket 連線；新連線到來時關閉舊連線。
整個 app 只有一個輸出 pusher（lifespan 建立），推送對象是 `state.current_ws`。
"""

import asyncio
import logging
import os
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import load_config
from mobile import audio as _mobile_audio
from mobile.audio import _FFMPEG_MISSING_HINT, _check_ffmpeg
from mobile.inputs import _handle_audio, _handle_text
from mobile.net import _get_lan_ip
from mobile.outputs import _output_pusher
from mobile.push import _push_sessions_refresh, _push_status
from mobile.ssl_cert import _ensure_self_signed_cert
from mobile.state import MobileState, autosave_buffer, build_mobile_state

log = logging.getLogger("mobile_server")


def create_app(state: MobileState, *, static_dir: str = "static") -> FastAPI:
    """建立手機 FastAPI app；所有元件與 queue 取自 `state`。"""

    # ── FastAPI lifespan ───────────────────────────────────────────────────

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        # ffmpeg 旗標存放於 mobile.audio（_to_wav 讀取處）
        _mobile_audio._FFMPEG_AVAILABLE = _check_ffmpeg()
        if _mobile_audio._FFMPEG_AVAILABLE:
            log.info("ffmpeg available — audio upload will work.")
        else:
            log.error("ffmpeg NOT found. %s", _FFMPEG_MISSING_HINT)

        state.lifecycle.start_all()
        # B6：全域唯一的輸出 pusher，推送對象為 state.current_ws
        pusher = asyncio.create_task(_output_pusher(state))
        log.info("Mobile server started. Session: %s", state.session_manager.current_title)
        try:
            yield
        finally:
            pusher.cancel()
            try:
                await pusher
            except asyncio.CancelledError:
                pass
            state.lifecycle.stop_all()
            # D10：停機時 buffer 非空則匯出 _buffer_temp.json（桌面不做）
            autosave_buffer(state)
            log.info("Mobile server stopped.")

    app = FastAPI(lifespan=lifespan)

    if os.path.exists(static_dir):
        app.mount("/static", StaticFiles(directory=static_dir), name="static")

    @app.get("/")
    async def root():
        return FileResponse(os.path.join(static_dir, "index.html"))

    # ── WebSocket ──────────────────────────────────────────────────────────

    @app.websocket("/ws")
    async def websocket_handler(ws: WebSocket):
        await ws.accept()
        log.info("Client connected: %s", ws.client)

        # B6：只服務最新連線——先改指向，再關閉舊連線
        old = state.current_ws
        state.current_ws = ws
        if old is not None:
            try:
                await old.close()
                log.info("Previous client closed (replaced by new connection)")
            except Exception as exc:
                log.debug("Closing previous client failed: %s", exc)

        # 連線後推送初始狀態
        _push_status(state, "待機")
        _push_sessions_refresh(state)

        try:
            while True:
                msg = await ws.receive()
                if msg.get("type") == "websocket.disconnect":
                    log.info("Client disconnected")
                    break
                if msg.get("bytes"):
                    # 音訊 blob（binary frame）→ 轉換 → audio_out（同 Recorder 輸出）
                    await asyncio.to_thread(_handle_audio, state, msg["bytes"])
                elif msg.get("text"):
                    _handle_text(state, msg["text"])
        except WebSocketDisconnect:
            log.info("Client disconnected")
        finally:
            if state.current_ws is ws:
                state.current_ws = None

    return app


# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
    state = build_mobile_state(load_config())
    _cfg = state.cfg
    app = create_app(state)

    host = _cfg.get("MOBILE", "host", fallback="0.0.0.0")
    port = _cfg.getint("MOBILE", "port", fallback=8080)
    use_ssl = _cfg.getboolean("MOBILE", "ssl", fallback=True)

    ssl_kwargs = {}
    if use_ssl:
        cert_path = _cfg.get("MOBILE", "ssl_cert", fallback="output/ssl/cert.pem")
        key_path  = _cfg.get("MOBILE", "ssl_key",  fallback="output/ssl/key.pem")
        if _ensure_self_signed_cert(cert_path, key_path):
            ssl_kwargs = {"ssl_certfile": cert_path, "ssl_keyfile": key_path}
            scheme = "https"
        else:
            log.warning("HTTPS disabled — falling back to HTTP (microphone may not work on Chrome)")
            scheme = "http"
    else:
        scheme = "http"

    # 印出本機 IP 方便手機連線
    local_ip = _get_lan_ip()

    log.info("=" * 50)
    log.info("Mobile server ready!")
    log.info("  Local :  %s://localhost:%d", scheme, port)
    log.info("  Mobile:  %s://%s:%d", scheme, local_ip, port)
    if scheme == "https":
        log.info("  (手機第一次連線需接受憑證警告)")
    log.info("=" * 50)

    uvicorn.run(app, host=host, port=port, reload=False, **ssl_kwargs)
