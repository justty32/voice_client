"""tts/kokoro_worker.py — 長駐 Kokoro worker（子 process）。

懶載入中／英文 ONNX 模型，合成中英片段後以 PyAudio 播放；
透過共享取消編號（cancel_through）中斷播放。
"""

from speech.tts.language import _split_language_runs


def _kokoro_worker(
    task_queue,
    result_queue,
    cancel_through,
    settings: dict,
):
    """長駐 Kokoro worker：懶載入模型、合成中英片段並以 PyAudio 播放。"""
    try:
        import numpy as np
        import pyaudio
        from kokoro_onnx import Kokoro
        from misaki import zh
    except Exception as exc:
        result_queue.put(("startup_error", 0, f"{type(exc).__name__}: {exc}"))
        return

    models: dict[str, object] = {}
    zh_g2p = None

    def load_model(lang: str):
        nonlocal zh_g2p
        if lang in models:
            return models[lang]
        if lang == "zh":
            zh_g2p = zh.ZHG2P(version="1.1")
            models[lang] = Kokoro(
                settings["zh_model"],
                settings["zh_voices"],
                vocab_config=settings["zh_config"],
            )
        else:
            models[lang] = Kokoro(settings["en_model"], settings["en_voices"])
        return models[lang]

    while True:
        task = task_queue.get()
        if task is None:
            break
        task_id, text = task
        try:
            chunks = []
            sample_rate = 24000
            for lang, chunk in _split_language_runs(text):
                if task_id <= cancel_through.value:
                    break
                kokoro = load_model(lang)
                if lang == "zh":
                    phonemes, _ = zh_g2p(chunk)
                    samples, sample_rate = kokoro.create(
                        phonemes,
                        voice=settings["zh_voice"],
                        speed=settings["speed"],
                        is_phonemes=True,
                    )
                else:
                    samples, sample_rate = kokoro.create(
                        chunk,
                        voice=settings["en_voice"],
                        speed=settings["speed"],
                        lang="en-us",
                    )
                chunks.append(samples)

            if chunks and task_id > cancel_through.value:
                audio = np.concatenate(chunks).astype(np.float32, copy=False)
                volume = settings["volume"]
                if volume != 1.0:
                    audio = np.clip(audio * volume, -1.0, 1.0)
                pa = pyaudio.PyAudio()
                stream = pa.open(
                    format=pyaudio.paFloat32,
                    channels=1,
                    rate=sample_rate,
                    output=True,
                )
                try:
                    frame_size = 2048
                    for offset in range(0, len(audio), frame_size):
                        if task_id <= cancel_through.value:
                            break
                        stream.write(audio[offset:offset + frame_size].tobytes())
                finally:
                    stream.stop_stream()
                    stream.close()
                    pa.terminate()
            result_queue.put(("done", task_id, None))
        except Exception as exc:
            result_queue.put(("error", task_id, f"{type(exc).__name__}: {exc}"))
