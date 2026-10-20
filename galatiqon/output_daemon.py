"""Output daemon: owns the screen and speaker, takes messages from galatiqon-say / ptt."""

from __future__ import annotations

import json
import logging
import os
import queue
import random
import socketserver
import threading
import time

from . import config, display
from .tts import Speaker

log = logging.getLogger("galatiqon.output")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    cfg = config.load()
    screen = display.make(cfg.display)
    speaker = Speaker(cfg.tts)
    bot_label = cfg.bot.split("·")[0].strip() or "Galatiqon"

    ui_q: queue.Queue[dict] = queue.Queue()
    speech_q: queue.Queue[str] = queue.Queue()

    class Handler(socketserver.StreamRequestHandler):
        def handle(self) -> None:
            for raw in self.rfile:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    log.warning("bad message: %r", raw[:200])
                    continue
                ui_q.put(msg)
                if msg.get("type") == "say" and msg.get("speak", True):
                    speech_q.put(msg["text"])

    def speech_worker() -> None:
        while True:
            speaker.speak(speech_q.get())

    sock = config.SOCKET_PATH
    sock.parent.mkdir(parents=True, exist_ok=True)
    if sock.exists():
        sock.unlink()
    server = socketserver.ThreadingUnixStreamServer(str(sock), Handler)
    os.chmod(sock, 0o660)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=speech_worker, daemon=True).start()
    log.info("listening on %s", sock)

    status, body = "Ready", "Hold the button and talk."
    shown_at = time.monotonic()
    reply_deadline: float | None = None  # set while waiting on the bot
    ack_at: float | None = None  # when to say "On it." if the bot is still thinking
    screen.show(status, body)

    g = cfg.grokbot
    # pygame must be driven from the main thread, so the UI loop lives here.
    while True:
        try:
            msg = ui_q.get(timeout=0.1)
        except queue.Empty:
            screen.pump()
            now = time.monotonic()
            if ack_at and now > ack_at:
                ack_at = None
                if g.ack_phrases:
                    speech_q.put(random.choice(g.ack_phrases))
            if reply_deadline and now > reply_deadline:
                reply_deadline = None
                status, body, shown_at = "No reply", "Your bot didn't answer. Try again?", now
                screen.show(status, body)
            elif not reply_deadline and body and now - shown_at > cfg.display.message_timeout_s:
                status, body = "Ready", ""
                screen.show(status, body)
            continue
        if msg.get("type") == "say":
            reply_deadline = ack_at = None
            status, body = bot_label, msg.get("text", "")
        elif msg.get("type") == "status":
            status = msg.get("text", "")
            body = msg.get("body", "")
            if status == "Thinking...":
                reply_deadline = time.monotonic() + g.reply_timeout_s + 5
                if g.ack_after_s > 0:
                    ack_at = time.monotonic() + g.ack_after_s
            elif status == "Working...":
                pass  # keep the deadline and the pending ack
            else:
                reply_deadline = ack_at = None
        shown_at = time.monotonic()
        screen.show(status, body)


if __name__ == "__main__":
    main()
