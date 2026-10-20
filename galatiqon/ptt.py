"""Push-to-talk daemon: hold the button, speak, release.

Audio is transcribed locally (Vosk), sent to the owner's Grok Bot, and every message the bot writes
is spoken and shown as soon as it arrives.
"""

from __future__ import annotations

import logging
import signal
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path

from . import config, grokbot, ipc
from .stt import Transcriber

log = logging.getLogger("galatiqon.ptt")


class Conversation:
    """Owns the transport. `ask` is what both the button and `galatiqon-ask` call."""

    def __init__(self, cfg: config.Config):
        self.cfg = cfg
        self.bot = cfg.bot
        self.transport = grokbot.make(cfg.grokbot)
        if hasattr(self.transport, "on_wake"):
            self.transport.on_wake = lambda: ipc.try_say("Waking your bot up, one moment.")

    def ask(self, text: str) -> grokbot.Turn:
        g = self.cfg.grokbot
        prompt = f"{g.prompt_prefix}\n\n{text}" if g.prompt_prefix else text
        ipc.try_status("Thinking...", body=f"You: {text}")
        t0 = time.monotonic()

        def on_message(msg: str) -> None:
            log.info("reply after %.1fs: %r", time.monotonic() - t0, msg[:200])
            ipc.try_say(msg)

        def on_activity(running: bool) -> None:
            if running:
                ipc.try_status("Working...", body=f"You: {text}")

        try:
            turn = self.transport.ask_streaming(self.bot, prompt, on_message, on_activity, g.reply_timeout_s)
        except grokbot.GrokBotError as e:
            log.error("%s", e)
            ipc.try_say(e.spoken)
            raise
        if not turn.messages:
            ipc.try_say("Your bot finished without saying anything.")
        else:
            ipc.try_status("Ready", body=turn.messages[-1])
        return turn


class PushToTalk:
    def __init__(self, cfg: config.Config):
        self.cfg = cfg
        self.stt = Transcriber(cfg.stt)
        self.convo = Conversation(cfg)
        self.lock = threading.Lock()  # one utterance at a time
        self.recorder: subprocess.Popen | None = None
        self.wav = Path(tempfile.gettempdir()) / "galatiqon-utterance.wav"
        self.pressed_at = 0.0

    def on_press(self) -> None:
        if not self.lock.acquire(blocking=False):
            return  # still handling the previous utterance
        self.pressed_at = time.monotonic()
        a = self.cfg.audio
        try:
            self.recorder = subprocess.Popen(
                ["arecord", "-q", "-D", a.input_device, "-f", "S16_LE", "-r", "16000", "-c", "1",
                 "-d", str(int(a.max_record_s)), str(self.wav)]
            )
        except OSError:
            log.exception("could not start arecord")
            self.lock.release()
            return
        ipc.try_status("Listening...")

    def on_release(self) -> None:
        if self.recorder is None:
            return
        # SIGINT lets arecord finish the WAV header cleanly.
        self.recorder.send_signal(signal.SIGINT)
        self.recorder.wait(timeout=5)
        self.recorder = None
        held = time.monotonic() - self.pressed_at
        threading.Thread(target=self._process, args=(held,), daemon=True).start()

    def _process(self, held: float) -> None:
        try:
            if held < self.cfg.button.min_hold_s:
                ipc.try_status("Ready")
                return
            ipc.try_status("Transcribing...")
            text = self.stt.transcribe(str(self.wav))
            log.info("heard: %r", text)
            if not text:
                ipc.try_say("Sorry, I didn't catch that.")
                return
            self.convo.ask(text)
        except grokbot.GrokBotError:
            pass  # already spoken by Conversation.ask
        except Exception:
            log.exception("failed to process utterance")
            ipc.try_say("Something went wrong.")
        finally:
            self.lock.release()


def _run_gpio(ptt: PushToTalk, pin: int) -> None:
    from gpiozero import Button

    button = Button(pin, pull_up=True, bounce_time=0.05)
    button.when_pressed = ptt.on_press
    button.when_released = ptt.on_release
    log.info("ready, push-to-talk on GPIO%d", pin)
    ipc.try_status("Ready")
    signal.pause()


def _run_keyboard(ptt: PushToTalk) -> None:
    """No button wired yet: Enter starts recording, Enter again stops it. Works over SSH."""
    log.info("ready, keyboard mode: press Enter to talk, Enter to stop, Ctrl-D to quit")
    ipc.try_status("Ready")
    recording = False
    for _ in sys.stdin:
        if not recording:
            ptt.on_press()
            recording = ptt.recorder is not None
            print("recording... press Enter to stop", flush=True)
        else:
            ptt.on_release()
            recording = False


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = config.load()
    ptt = PushToTalk(cfg)
    log.info("talking to bot %r via %s", cfg.bot, cfg.grokbot.transport)
    if cfg.button.mode == "keyboard":
        _run_keyboard(ptt)
    else:
        _run_gpio(ptt, cfg.button.gpio_pin)


if __name__ == "__main__":
    main()
