"""mobile/audio.py — ffmpeg 可用性檢查與瀏覽器音訊（WebM/MP4）→ 16kHz mono WAV。

`_FFMPEG_AVAILABLE` 由 mobile_server 的 lifespan 於啟動時寫入本模組。
"""

import io
import logging
import shutil

log = logging.getLogger("mobile_server")


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
