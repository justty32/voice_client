"""
mobile_server.py — Mobile Web 版後端

FastAPI + WebSocket，讓手機瀏覽器連線使用語音客戶端。

保留：VoiceToText, TextAccumulator, SummaryGenerator, HttpClient, SessionManager
取代：Recorder → MediaRecorder (前端), TuiRenderer → HTML UI, pyttsx3 → SpeechSynthesis (前端)
"""

import asyncio
import io
import json
import logging
import os
import queue
import shutil
import socket
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from config import load_config
from http_client import HttpClient
from session_manager import SessionManager
from summary_generator import SummaryGenerator
from text_accumulator import TextAccumulator
from voice_to_text import VoiceToText

log = logging.getLogger("mobile_server")


# ── Setup ──────────────────────────────────────────────────────────────────

def _setup_logging(cfg):
    level_str = cfg.get("LOGGING", "level", fallback="INFO")
    level = getattr(logging, level_str.upper(), logging.INFO)
    log_file = cfg.get("WORKSPACE", "log_file", fallback="output/system.log")
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        handlers=[
            logging.FileHandler(log_file, encoding="utf-8"),
            logging.StreamHandler(),
        ],
    )


_FFMPEG_AVAILABLE: bool = False
_FFMPEG_MISSING_HINT = (
    "ffmpeg 未安裝。Linux: sudo apt install ffmpeg ｜ macOS: brew install ffmpeg "
    "｜ Windows: choco install ffmpeg"
)


def _check_ffmpeg() -> bool:
    """啟動前檢查 ffmpeg 是否可用；pydub 依賴它做音訊解碼。"""
    return shutil.which("ffmpeg") is not None or shutil.which("avconv") is not None


def _to_wav(data: bytes) -> tuple[io.BytesIO | None, str | None]:
    """瀏覽器 MediaRecorder 輸出（WebM/MP4）→ 16kHz mono WAV。需要 ffmpeg。
    回傳 (buffer, error_msg)；成功時 error_msg 為 None。
    """
    if not _FFMPEG_AVAILABLE:
        return None, _FFMPEG_MISSING_HINT
    try:
        from pydub import AudioSegment
        seg = AudioSegment.from_file(io.BytesIO(data))
        seg = seg.set_frame_rate(16000).set_channels(1).set_sample_width(2)
        buf = io.BytesIO()
        seg.export(buf, format="wav")
        buf.seek(0)
        return buf, None
    except FileNotFoundError as exc:
        # pydub 呼叫 ffmpeg 時找不到可執行檔
        log.error("Audio conversion: ffmpeg missing: %s", exc)
        return None, _FFMPEG_MISSING_HINT
    except Exception as exc:
        log.error("Audio conversion failed: %s", exc)
        return None, f"音訊解碼失敗：{exc}"


# ── Module-level state (single-user server) ────────────────────────────────

_cfg = load_config()
_setup_logging(_cfg)

_audio_queue          = queue.Queue()
_stt_output_queue     = queue.Queue()
_acc_input_queue      = queue.Queue()
_acc_cmd_queue        = queue.Queue()
_acc_output_queue     = queue.Queue()
_summary_queue        = queue.Queue()
_summary_output_queue = queue.Queue()
_send_queue           = queue.Queue()
_recv_queue           = queue.Queue()
_ui_event_queue       = queue.Queue()  # 事件 → WebSocket 推送

_session_manager = SessionManager(_cfg)
if not _session_manager.current_title:
    if not _session_manager.switch_session("default"):
        _session_manager.new_session("default")

_voice_to_text    = VoiceToText(_cfg, _audio_queue, _stt_output_queue)
_text_accumulator = TextAccumulator(_cfg, _acc_input_queue, _acc_cmd_queue, _acc_output_queue)
_summary_gen      = SummaryGenerator(_cfg, _summary_queue, _summary_output_queue)
_http_client      = HttpClient(_cfg, _send_queue, _recv_queue, _session_manager)

_summary_threshold = _cfg.getint("SLM", "summary_threshold", fallback=20)
_slm_enabled = _cfg.getboolean("SLM", "enabled", fallback=True)


# ── Push helpers ───────────────────────────────────────────────────────────

def _push(event: dict):
    _ui_event_queue.put(event)

def _push_msg(role: str, text: str):
    _push({"type": "message", "role": role, "text": text})

def _push_status(text: str):
    _push({"type": "status", "text": text})

def _push_tts(text: str, priority: str = "medium"):
    _push({"type": "tts", "text": text, "priority": priority})

def _push_system(text: str):
    _push_msg("system", text)


# ── FastAPI lifespan ───────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _FFMPEG_AVAILABLE
    _FFMPEG_AVAILABLE = _check_ffmpeg()
    if _FFMPEG_AVAILABLE:
        log.info("ffmpeg available — audio upload will work.")
    else:
        log.error("ffmpeg NOT found. %s", _FFMPEG_MISSING_HINT)

    _voice_to_text.start()
    _text_accumulator.start()
    _summary_gen.start()
    _http_client.start()
    log.info("Mobile server started. Session: %s", _session_manager.current_title)
    yield
    _voice_to_text.stop()
    _text_accumulator.stop()
    _summary_gen.stop()
    _http_client.stop()
    log.info("Mobile server stopped.")


app = FastAPI(lifespan=lifespan)

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def root():
    return FileResponse("static/index.html")


# ── WebSocket ──────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_handler(ws: WebSocket):
    await ws.accept()
    log.info("Client connected: %s", ws.client)

    # 連線後推送初始狀態
    _push_status("待機")
    _push({"type": "sessions_refresh"})

    pusher = asyncio.create_task(_output_pusher(ws))
    try:
        while True:
            msg = await ws.receive()
            if msg.get("bytes"):
                # 音訊 blob（binary frame）→ 轉換 → audio_queue
                await asyncio.to_thread(_handle_audio, msg["bytes"])
            elif msg.get("text"):
                _handle_text(msg["text"])
    except WebSocketDisconnect:
        log.info("Client disconnected")
    finally:
        pusher.cancel()
        try:
            await pusher
        except asyncio.CancelledError:
            pass


# ── Input handlers ─────────────────────────────────────────────────────────

def _handle_audio(data: bytes):
    """在 thread 中執行音訊轉換（pydub 為同步操作）。"""
    _push_status("處理中")
    wav, err = _to_wav(data)
    if wav:
        _audio_queue.put(wav)
        log.debug("Audio queued (%d bytes raw)", len(data))
    else:
        if err:
            _push_msg("error", f"[音訊錯誤] {err}")
        _push_status("待機")


def _handle_text(raw: str):
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return

    t = data.get("type")
    if t == "text":
        content = data.get("content", "").strip()
        if content:
            _push_msg("user", content)
            _acc_input_queue.put({"type": "text", "text": content, "msg_type": "TextChat"})
    elif t == "cmd":
        _route_cmd(data.get("cmd", ""), data.get("args", []))
    elif t == "signal":
        _route_signal(data.get("signal", ""))


def _route_signal(signal: str):
    if signal == "QUICK_SEND":
        _acc_cmd_queue.put({"cmd": "flush", "msg_type": "TextChat"})


def _route_cmd(cmd: str, args: list):
    if cmd == "/new":
        title = " ".join(args) if args else f"session_{len(_session_manager.list_sessions()) + 1}"
        _session_manager.new_session(title)
        _push_system(f"新建對話: {title}")
        _push({"type": "sessions_refresh"})

    elif cmd == "/switch":
        title = " ".join(args) if args else "default"
        if _session_manager.switch_session(title):
            _push_system(f"切換至: {title}")
        else:
            _push_system(f"找不到對話: {title}")
        _push({"type": "sessions_refresh"})

    elif cmd == "/list":
        sessions = _session_manager.list_sessions()
        text = "對話列表:\n" + "\n".join(f"  - {s}" for s in sessions)
        text += f"\n\n當前 session：{_session_manager.current_title or '無'}"
        _push_system(text)

    elif cmd == "/delete":
        _, msg = _session_manager.delete_session(" ".join(args))
        _push_system(msg)
        _push({"type": "sessions_refresh"})

    elif cmd == "/save":
        _, msg = _session_manager.save_session_to_file(" ".join(args) if args else None)
        _push_system(msg)

    elif cmd == "/load":
        if not args:
            _push_system("請指定要載入的檔名。")
        else:
            _, msg = _session_manager.load_session_from_file(args[0])
            _push_system(msg)
            _push({"type": "sessions_refresh"})

    elif cmd == "/rename":
        if len(args) < 2:
            _push_system("用法: /rename [舊名稱] [新名稱]")
        else:
            _, msg = _session_manager.rename_session(args[0], args[1])
            _push_system(msg)
            _push({"type": "sessions_refresh"})

    elif cmd == "/history":
        _push_system(_session_manager.get_history())

    elif cmd == "/clear":
        arg = args[0].lower() if args else None
        if arg == "buffer":
            _acc_cmd_queue.put({"cmd": "clear"})
        else:
            _push({"type": "clear"})
            _push_status("待機")

    elif cmd == "/concat":
        _acc_cmd_queue.put({"cmd": "concat"})

    elif cmd == "/to_top":
        _acc_cmd_queue.put({"cmd": "to_top"})

    elif cmd == "/send":
        _acc_cmd_queue.put({"cmd": "flush", "msg_type": "TextChat"})

    elif cmd == "/show":
        _acc_cmd_queue.put({"cmd": "peek"})

    elif cmd == "/export":
        _acc_cmd_queue.put({"cmd": "export", "args": args})

    elif cmd == "/import":
        _acc_cmd_queue.put({"cmd": "import", "args": args})

    elif cmd == "/help":
        _push_system(
            "/new /switch /list /delete /save /load /rename /history "
            "/concat /to_top /send /export /import /show /clear /help"
        )

    else:
        _push_system(f"未知指令: {cmd}")


# ── Response handler ───────────────────────────────────────────────────────

def _handle_response(response: dict):
    resp_type = response.get("type", "ChatReply")

    if resp_type == "ChatReply":
        full = response.get("Content", {}).get("full_response", "")
        if full:
            _session_manager.add_message("assistant", full)
            _push_msg("assistant", full)
            # SLM 停用時不走摘要流程；短回覆也直接播原文
            if not _slm_enabled or len(full) < _summary_threshold:
                _push_tts(full, "medium")
            else:
                _summary_queue.put({"cmd": "summary", "text": full,
                                    "title": _session_manager.current_title})
        _push_status("待機")

    elif resp_type == "StatusUpdate":
        text = response.get("text", "")
        _push_status(text)
        _push_tts(text, "low")

    elif resp_type == "Error":
        msg = response.get("message", "Unknown error")
        _push_msg("error", f"[錯誤] {msg}")
        _push_tts(f"發生錯誤：{msg}", "high")
        _push_status("待機")


# ── Output pusher (async task) ─────────────────────────────────────────────

async def _output_pusher(ws: WebSocket):
    """每 50ms 輪詢所有 output queue，將事件推送至 WebSocket 前端。"""
    while True:
        try:
            # 1. STT output → voice 訊息 + 加入 accumulator
            while not _stt_output_queue.empty():
                text = _stt_output_queue.get_nowait()
                if text.strip():
                    _push_msg("voice", text)
                    _acc_input_queue.put({"type": "text", "text": text, "msg_type": "VoiceChat"})

            # 2. Accumulator output → HTTP send
            while not _acc_output_queue.empty():
                item = _acc_output_queue.get_nowait()
                if item.get("type") == "payload":
                    payload = item["payload"]
                    payload["Title"] = _session_manager.current_title or "default"
                    payload.setdefault("Metadata", {})["ClientTime"] = (
                        datetime.now(timezone.utc).isoformat()
                    )
                    _session_manager.add_message("user", payload["Content"])
                    _push_msg("sending", f"[傳送內容] {payload['Content']}")
                    _send_queue.put(payload)
                    _push_status("傳送中")
                elif item.get("type") == "buffer_peek":
                    _push_system(item["text"])

            # 3. Summary output → 摘要訊息 + TTS
            while not _summary_output_queue.empty():
                item = _summary_output_queue.get_nowait()
                if item.get("type") == "status":
                    _push_status(item["text"])
                elif item.get("type") == "summary":
                    display = f"回覆摘要：{item['text']}"
                    _push_msg("summary", display)
                    _push_tts(display, "medium")

            # 4. HTTP response
            while not _recv_queue.empty():
                _handle_response(_recv_queue.get_nowait())

            # 5. 送出所有 UI events（含上面各步驟新產生的）
            while not _ui_event_queue.empty():
                event = _ui_event_queue.get_nowait()
                if event["type"] == "sessions_refresh":
                    sessions = _session_manager.list_sessions()
                    current = _session_manager.current_title or ""
                    await ws.send_json({"type": "sessions", "list": sessions, "current": current})
                else:
                    await ws.send_json(event)

        except Exception as exc:
            log.error("Output pusher error: %s", exc)

        await asyncio.sleep(0.05)


# ── Network helpers ────────────────────────────────────────────────────────

def _get_lan_ip() -> str:
    """用 UDP socket 取得本機對外 LAN IP（不實際送封包）。
    避開 `gethostbyname(gethostname())` 在 Linux 上被 `/etc/hosts` 的
    `127.0.1.1 hostname` 欺騙成 loopback 的問題。
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.settimeout(0.5)
        # 8.8.8.8:80 只是路由選擇用的目的，不會真的送封包
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    finally:
        try:
            s.close()
        except Exception:
            pass
    # fallback
    try:
        ip = socket.gethostbyname(socket.gethostname())
        if ip and not ip.startswith("127."):
            return ip
    except Exception:
        pass
    return "127.0.0.1"


# ── SSL cert generation ────────────────────────────────────────────────────

def _ensure_self_signed_cert(cert_path: str, key_path: str) -> bool:
    """生成自簽 SSL 憑證（如果尚未存在）。需要 cryptography 套件。
    憑證包含本機 IP 的 SAN，讓手機瀏覽器可接受（需手動信任一次）。
    """
    if os.path.exists(cert_path) and os.path.exists(key_path):
        log.info("Using existing SSL cert: %s", cert_path)
        return True
    try:
        import datetime
        import ipaddress

        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        log.info("Generating self-signed SSL certificate...")

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

        # 取得本機 IP，加入 SAN 讓手機可以用 IP 連線
        local_ip = _get_lan_ip()

        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "VoiceClient"),
        ])

        san_entries = [
            x509.DNSName("localhost"),
            x509.IPAddress(ipaddress.IPv4Address("127.0.0.1")),
        ]
        if local_ip != "127.0.0.1":
            try:
                san_entries.append(x509.IPAddress(ipaddress.IPv4Address(local_ip)))
            except Exception:
                pass

        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(datetime.datetime.now(datetime.timezone.utc))
            .not_valid_after(
                datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=3650)
            )
            .add_extension(
                x509.SubjectAlternativeName(san_entries),
                critical=False,
            )
            .sign(key, hashes.SHA256())
        )

        os.makedirs(os.path.dirname(cert_path) or ".", exist_ok=True)
        with open(key_path, "wb") as f:
            f.write(key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            ))
        # 私鑰僅限擁有者讀寫（POSIX）。Windows 上 chmod 幾乎 no-op 但不會壞。
        try:
            os.chmod(key_path, 0o600)
        except OSError as exc:
            log.warning("chmod 600 on %s failed: %s", key_path, exc)
        with open(cert_path, "wb") as f:
            f.write(cert.public_bytes(serialization.Encoding.PEM))

        log.info("SSL cert generated: %s (valid 10 years, IP: %s)", cert_path, local_ip)
        return True

    except ImportError:
        log.error("SSL cert generation requires the 'cryptography' package: pip install cryptography")
        return False
    except Exception as exc:
        log.error("SSL cert generation failed: %s", exc)
        return False


# ── Entry point ────────────────────────────────────────────────────────────

if __name__ == "__main__":
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

    uvicorn.run("mobile_server:app", host=host, port=port, reload=False, **ssl_kwargs)
