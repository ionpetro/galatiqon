"""Offline speech-to-text with Vosk. The small English model is about 40 MB
and runs faster than real time on a Pi."""

from __future__ import annotations

import json
import wave

from .config import SttConfig


class Transcriber:
    def __init__(self, cfg: SttConfig):
        from vosk import Model, SetLogLevel

        SetLogLevel(-1)
        self.model = Model(cfg.vosk_model)

    def transcribe(self, wav_path: str) -> str:
        from vosk import KaldiRecognizer

        with wave.open(wav_path, "rb") as wf:
            rec = KaldiRecognizer(self.model, wf.getframerate())
            while data := wf.readframes(4000):
                rec.AcceptWaveform(data)
        return json.loads(rec.FinalResult()).get("text", "").strip()
