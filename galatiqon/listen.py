"""`galatiqon-listen`: speak whatever the bot writes, no matter who asked.

Push-to-talk already speaks the replies to what was said into the device. This daemon covers the
rest: something typed to the bot in the Grok Bot app (phone, desktop, X), a routine that fires, a
teammate's Galatiqon messaging in. It keeps gbd's event stream open for the owner's bot and hands
every bot message to the output daemon, or to a shell command when the speaker is somewhere else
(for example `ssh pi@musebike.local sudo -n -u muse bike-say`, with the bridge running on a laptop).

Observed gbd behaviour this relies on (v0.1.0):
  - a bot reply is a `message` event with `fromBot: true`, `text`, `entryId` and
    `entry.requestId`; the `prompt` event that started the turn (`author: "you"`, the typed text)
    carries the same `entry.requestId` and arrives first;
  - galatiqon-ptt prefixes every prompt with [grokbot] prompt_prefix, so a turn whose prompt starts
    with it is the button's. Its replies are skipped here by default ([listen] speak_device_turns)
    because ptt speaks them, and nothing is said twice. (The `refs` gbd attaches to events are not
    used for this: refs from earlier /v1/send calls linger on later, unrelated messages.)
  - `GET /v1/events?since=<event id>` replays what came after that id, so a dropped connection is
    reopened from the last event seen and nothing said in between is lost.
"""

from __future__ import annotations

import argparse
import http.client
import logging
import shlex
import socket
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path
from collections.abc import Callable

from . import config, grokbot, ipc

log = logging.getLogger("galatiqon.listen")

EVENT_TYPES = ["prompt", "message", "turn.done"]
Speak = Callable[[str], None]
Show = Callable[[str], None]


class Listener:
    def __init__(self, cfg: config.Config, client: grokbot.GbdClient, speak: Speak, show: Show | None = None):
        self.cfg = cfg
        self.bot = cfg.bot
        self.client = client
        self.speak = speak
        self.show = show
        self.last_id: int | None = None
        self._seen: deque[str] = deque(maxlen=500)
        self._device_turns: deque[str] = deque(maxlen=50)  # requestIds of prompts the button sent
        self._conn: http.client.HTTPConnection | None = None
        self._stop = threading.Event()

    # -- one event --

    def handle(self, etype: str, ev: dict) -> str | None:
        """Process one event. Returns the text that was spoken, if any."""
        if isinstance(ev.get("id"), int):
            self.last_id = ev["id"]
        name = ev.get("agentName")
        if name and name != self.bot:
            return None
        text = (ev.get("text") or "").strip()
        request_id = (ev.get("entry") or {}).get("requestId") or ""
        if etype == "prompt":
            prefix = self.cfg.grokbot.prompt_prefix
            if prefix and text.startswith(prefix):
                if request_id:
                    self._device_turns.append(request_id)
            elif text and self.show:
                self.show(text)
            return None
        if etype != "message" or not text:
            return None
        if ev.get("fromBot") is False:
            return None
        key = ev.get("entryId") or f"event:{ev.get('id')}"
        if key in self._seen:
            return None
        self._seen.append(key)
        if request_id in self._device_turns and not self.cfg.listen.speak_device_turns:
            log.debug("skipping %s: the button asked, ptt speaks it", key)
            return None
        log.info("%s: %r", self.bot, text[:200])
        self.speak(text)
        return text

    # -- the stream --

    def run_once(self) -> None:
        """Open the stream (from the last event seen) and process it until it ends."""
        conn, events = self.client.events([self.bot], EVENT_TYPES, timeout=self.cfg.listen.read_timeout_s,
                                          since=self.last_id)
        self._conn = conn
        try:
            log.info("listening to %r%s", self.bot, f" since event {self.last_id}" if self.last_id else "")
            for etype, ev in events:
                if self._stop.is_set():
                    return
                try:
                    self.handle(etype, ev)
                except Exception:
                    log.exception("could not handle %s event", etype)
        finally:
            self._conn = None
            conn.close()

    def run(self) -> None:
        """Keep the stream open until `stop()`; reconnect with backoff when it drops."""
        delay = 2.0
        while not self._stop.is_set():
            started = time.monotonic()
            try:
                self.run_once()
                if self._stop.is_set():
                    return
                log.warning("event stream ended")
            except grokbot.GrokBotError as e:
                if self._stop.is_set():
                    return
                log.warning("%s", e)
            except (socket.timeout, OSError, http.client.HTTPException) as e:
                if self._stop.is_set():
                    return
                log.warning("event stream failed: %s", e)
            if time.monotonic() - started > 60:
                delay = 2.0  # it was working; start the backoff over
            log.info("reconnecting in %.0fs", delay)
            if self._stop.wait(delay):
                return
            delay = min(delay * 2, 30.0)

    def stop(self) -> None:
        self._stop.set()
        conn = self._conn
        if conn is not None:
            try:
                conn.close()
            except OSError:
                pass


# -- where the words go --


def command_speaker(command: str) -> Speak:
    """Speak by running a shell command with the text as its last argument.

    When the command is ssh, the remote side re-parses the arguments with a shell, so the text is
    quoted for it (an apostrophe in "I'm here" would otherwise break the remote command line).
    """
    argv = shlex.split(command)
    if not argv:
        raise ValueError("[listen] say_command is empty")
    remote_shell = Path(argv[0]).name == "ssh"

    def speak(text: str) -> None:
        arg = shlex.quote(text) if remote_shell else text
        try:
            p = subprocess.run(argv + [arg], capture_output=True, text=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as e:
            log.error("say_command failed: %s", e)
            return
        if p.returncode != 0:
            log.error("say_command exited %d: %s", p.returncode, (p.stderr or p.stdout).strip()[:300])

    return speak


def local_speaker(text: str) -> None:
    ipc.try_say(text)


def local_show(text: str) -> None:
    ipc.try_status("Thinking...", body=f"You: {text}")


def main() -> None:
    p = argparse.ArgumentParser(prog="galatiqon-listen",
                                description="Speak every message the bot writes, whoever asked.")
    p.add_argument("--bot", help="override the bot name from the config")
    p.add_argument("--say-cmd", help="speak by running this command with the text appended "
                                    "(overrides [listen] say_command)")
    p.add_argument("--speak-device-turns", action="store_true",
                   help="also speak replies to the device's own push-to-talk prompts")
    p.add_argument("--since", type=int, help="replay from this gbd event id (debugging)")
    p.add_argument("--dry-run", action="store_true", help="print instead of speaking")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    cfg = config.load()
    if args.bot:
        cfg.grokbot.bot = args.bot
    if args.say_cmd:
        cfg.listen.say_command = args.say_cmd
    if args.speak_device_turns:
        cfg.listen.speak_device_turns = True

    client = grokbot.make(cfg.grokbot)
    if not isinstance(client, grokbot.GbdClient):
        sys.exit("galatiqon-listen needs the gbd transport ([grokbot] transport = \"gbd\")")

    if args.dry_run:
        speak, show = (lambda t: print(f"{cfg.bot}: {t}", flush=True)), (lambda t: print(f"You: {t}", flush=True))
    elif cfg.listen.say_command:
        speak, show = command_speaker(cfg.listen.say_command), None
    else:
        speak, show = local_speaker, local_show

    listener = Listener(cfg, client, speak, show)
    if args.since is not None:
        listener.last_id = args.since
    try:
        listener.run()
    except KeyboardInterrupt:
        listener.stop()


if __name__ == "__main__":
    main()
