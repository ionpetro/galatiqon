"""Text-to-speech via Piper (natural), espeak-ng (instant, robotic) or macOS `say` (laptop demos).

Loading the Piper voice takes ~15 s on a Pi, but synthesis after that is fast
(~0.6 s for a short sentence). So the voice is loaded once, in the background when
the output daemon starts, and kept in memory. Until it's ready, espeak-ng speaks.
"""

from __future__ import annotations

import logging
import re
import subprocess
import tempfile
import threading
import time
import wave

from .config import TtsConfig

log = logging.getLogger(__name__)


class Speaker:
    def __init__(self, cfg: TtsConfig):
        self.cfg = cfg
        self._voice = None
        self._ready = threading.Event()
        if cfg.engine == "piper":
            threading.Thread(target=self._load_piper, daemon=True).start()

    def _load_piper(self) -> None:
        t0 = time.monotonic()
        try:
            from piper import PiperVoice

            self._voice = PiperVoice.load(self.cfg.piper_voice)
            log.info("piper voice loaded in %.1fs", time.monotonic() - t0)
        except Exception as e:  # missing package or model: espeak-ng keeps working
            log.warning("piper unavailable (%s); using espeak-ng", e)
        finally:
            self._ready.set()

    def _respell(self, text: str) -> str:
        for word, sounds_like in self.cfg.pronunciations.items():
            text = re.sub(rf"\b{re.escape(word)}\b", sounds_like, text)
        return text

    def speak(self, text: str) -> None:
        text = self._respell(text)
        if self.cfg.engine == "piper" and self._voice is not None:
            try:
                self._piper(text)
                return
            except (OSError, subprocess.CalledProcessError) as e:
                log.warning("piper failed (%s), falling back to espeak-ng", e)
        elif self.cfg.engine == "piper" and not self._ready.is_set():
            log.info("piper voice still loading; using espeak-ng for this message")
        elif self.cfg.engine == "say":
            self._macos_say(text)
            return
        self._espeak(text)

    def _macos_say(self, text: str) -> None:
        t0 = time.monotonic()
        try:
            subprocess.run(["say", text], check=False)
        except OSError as e:
            log.error("`say` unavailable (%s); reply shown on screen only", e)
            return
        log.info("spoke say chars=%d synth=0.00s play=%.2fs", len(text), time.monotonic() - t0)

    def _piper(self, text: str) -> None:
        with tempfile.NamedTemporaryFile(suffix=".wav") as f:
            t0 = time.monotonic()
            with wave.open(f.name, "wb") as w:
                self._voice.synthesize_wav(text, w)
            t1 = time.monotonic()
            subprocess.run(["aplay", "-q", f.name], check=True)
            # parsed by scripts/latency_test.py
            log.info("spoke piper chars=%d synth=%.2fs play=%.2fs", len(text), t1 - t0, time.monotonic() - t1)

    def _espeak(self, text: str) -> None:
        t0 = time.monotonic()
        try:
            subprocess.run(["espeak-ng", "-v", self.cfg.espeak_voice, "-s", "165", text], check=False)
        except OSError as e:
            log.error("espeak-ng unavailable (%s); reply shown on screen only", e)
            return
        log.info("spoke espeak chars=%d synth=0.00s play=%.2fs", len(text), time.monotonic() - t0)
