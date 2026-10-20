"""The bridge between this device and a Grok Bot.

Grok Bot has no public SDK. Its bots live on a cloud "box" that the desktop app talks to over an
internal gateway. GrokBotCLI (https://github.com/JiminLee-way/GrokBotCLI, unofficial, MIT) speaks that
gateway from Linux, ships a static arm64 binary that runs on a 64-bit Raspberry Pi, and has a daemon
(`gb daemon run`, "gbd") that serves a small local HTTP API on a Unix socket:

  POST /v1/send   {bot, text, ref}                 -> prompt delivered, bot starts its turn
  GET  /v1/events?bots=&types=&since=              -> Server-Sent Events: message, activity, turn.done, ...
  POST /v1/ask    {bot, text, timeoutSec}          -> blocks until the turn is done -> {reply, messages}

Two transports are implemented here:

  GbdClient  talks to gbd. `ask_streaming` opens the event stream first, then sends the prompt, and
             hands every bot message to a callback as it arrives, so a long answer starts being spoken
             while the bot is still writing the rest. Falls back to the blocking /v1/ask on failure.
  GbCli      runs `gb ask <bot> <text> --json` as a subprocess. No daemon needed, but nothing is spoken
             until the whole turn is finished.

Everything is stdlib so it runs on the Pi without extra wheels.
"""

from __future__ import annotations

import http.client
import json
import logging
import socket
import subprocess
import time
import uuid
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlencode, urlsplit

from .config import GrokBotConfig

log = logging.getLogger("galatiqon.grokbot")

OnMessage = Callable[[str], None]
OnActivity = Callable[[bool], None]


class GrokBotError(Exception):
    """The bridge could not get an answer. `spoken` is a short phrase safe to read aloud."""

    def __init__(self, message: str, spoken: str = "I couldn't reach your bot."):
        super().__init__(message)
        self.spoken = spoken


class ReplyTimeout(GrokBotError):
    def __init__(self, bot: str, seconds: float):
        super().__init__(f"{bot} did not finish within {seconds:.0f}s", "That's taking too long. Try again in a bit.")


@dataclass
class Turn:
    messages: list[str] = field(default_factory=list)
    done: bool = False

    @property
    def reply(self) -> str:
        return "\n\n".join(m for m in self.messages if m.strip())


# --- HTTP over a Unix socket -------------------------------------------------------------------


class _UnixHTTPConnection(http.client.HTTPConnection):
    def __init__(self, path: str, timeout: float | None = None):
        super().__init__("localhost", timeout=timeout)
        self.unix_path = path

    def connect(self) -> None:  # type: ignore[override]
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.settimeout(self.timeout)
        s.connect(self.unix_path)
        self.sock = s


class GbdClient:
    def __init__(self, socket_path: Path | str | None = None, url: str = "", token: str = "",
                 gb_binary: str = "gb", on_wake: Callable[[], None] | None = None):
        if not url and not socket_path:
            raise ValueError("GbdClient needs a socket path or a URL")
        self.socket_path = str(socket_path) if socket_path else ""
        self.url = url.rstrip("/")
        self.token = token
        self.gb_binary = gb_binary
        self.on_wake = on_wake  # called once when the box has to be woken (so the device can say so)

    # The cloud box hibernates when idle; gbd then answers "box not ready ... try `gb box wake`".
    def _asleep(self, err: Exception) -> bool:
        return "box not ready" in str(err).lower() or "hibernat" in str(err).lower()

    def wake(self) -> None:
        if self.on_wake:
            self.on_wake()
        log.info("box asleep; running `%s box wake`", self.gb_binary)
        try:
            p = subprocess.run([self.gb_binary, "box", "wake"], capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.TimeoutExpired) as e:
            raise GrokBotError(f"could not wake the box: {e}", "I couldn't wake your bot up.") from e
        if p.returncode != 0:
            raise GrokBotError(f"gb box wake failed: {p.stderr.strip() or p.stdout.strip()}", "I couldn't wake your bot up.")

    def _connection(self, timeout: float | None) -> http.client.HTTPConnection:
        if self.url:
            u = urlsplit(self.url)
            if u.scheme == "https":
                return http.client.HTTPSConnection(u.hostname or "127.0.0.1", u.port or 443, timeout=timeout)
            return http.client.HTTPConnection(u.hostname or "127.0.0.1", u.port or 80, timeout=timeout)
        return _UnixHTTPConnection(self.socket_path, timeout=timeout)

    def _headers(self, extra: dict | None = None) -> dict:
        h = {"Accept": "application/json"}
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        if extra:
            h.update(extra)
        return h

    def request(self, method: str, path: str, body: dict | None = None, timeout: float = 30) -> tuple[int, dict]:
        conn = self._connection(timeout)
        try:
            payload = json.dumps(body).encode() if body is not None else None
            headers = self._headers({"Content-Type": "application/json"} if payload else None)
            conn.request(method, path, body=payload, headers=headers)
            resp = conn.getresponse()
            raw = resp.read()
        except (OSError, http.client.HTTPException) as e:
            raise GrokBotError(f"gbd unreachable at {self.socket_path or self.url}: {e}") from e
        finally:
            conn.close()
        try:
            data = json.loads(raw) if raw else {}
        except json.JSONDecodeError:
            data = {"error": raw.decode(errors="replace")[:300]}
        return resp.status, data

    # -- simple calls --

    def health(self) -> dict:
        status, data = self.request("GET", "/v1/health", timeout=10)
        if status != 200:
            raise GrokBotError(f"gbd health {status}: {data.get('error', data)}")
        return data

    def agents(self) -> list[dict]:
        status, data = self.request("GET", "/v1/agents", timeout=20)
        if status != 200:
            raise GrokBotError(f"gbd agents {status}: {data.get('error', data)}")
        return data if isinstance(data, list) else data.get("agents", [])

    def send(self, bot: str, text: str, ref: str = "") -> dict:
        body = {"bot": bot, "text": text}
        if ref:
            body["ref"] = ref
        status, data = self.request("POST", "/v1/send", body, timeout=60)
        if status != 200:
            raise GrokBotError(f"send to {bot!r} failed ({status}): {data.get('error', data)}",
                               _spoken_for(status, data))
        return data

    def ask(self, bot: str, text: str, timeout_s: float = 90, _retry: bool = True) -> Turn:
        """Blocking: returns when the bot's turn is done (gbd's own /v1/ask)."""
        body = {"bot": bot, "text": text, "timeoutSec": int(timeout_s)}
        status, data = self.request("POST", "/v1/ask", body, timeout=timeout_s + 15)
        if _retry and status != 200 and self._asleep(data.get("error", "")):
            self.wake()
            return self.ask(bot, text, timeout_s, _retry=False)
        if status == 504:
            raise ReplyTimeout(bot, timeout_s)
        if status != 200:
            raise GrokBotError(f"ask {bot!r} failed ({status}): {data.get('error', data)}", _spoken_for(status, data))
        msgs = [m.get("text", "") for m in data.get("messages", []) if m.get("type") == "message"]
        if not msgs and data.get("reply"):
            msgs = [data["reply"]]
        return Turn(messages=msgs, done=bool(data.get("done", True)))

    # -- streaming --

    def events(self, bots: list[str] | None = None, types: list[str] | None = None,
               timeout: float = 120, since: int | None = None,
               ) -> tuple[http.client.HTTPConnection, Iterator[tuple[str, dict]]]:
        """Open the SSE stream. Returns the connection (close it to stop) and an iterator of (type, event).

        `since` is a gbd event id: everything after it is replayed first (for reconnects).
        """
        q = {}
        if bots:
            q["bots"] = ",".join(bots)
        if types:
            q["types"] = ",".join(types)
        if since is not None:
            q["since"] = str(since)
        path = "/v1/events" + (f"?{urlencode(q)}" if q else "")
        conn = self._connection(timeout)
        try:
            conn.request("GET", path, headers=self._headers({"Accept": "text/event-stream"}))
            resp = conn.getresponse()
        except (OSError, http.client.HTTPException) as e:
            conn.close()
            raise GrokBotError(f"gbd events unreachable: {e}") from e
        if resp.status != 200:
            raw = resp.read(300)
            conn.close()
            raise GrokBotError(f"gbd events {resp.status}: {raw.decode(errors='replace')}")
        return conn, _sse(resp)

    def ask_streaming(self, bot: str, text: str, on_message: OnMessage,
                      on_activity: OnActivity | None = None, timeout_s: float = 90) -> Turn:
        """Send `text` and call `on_message` for every bot message of the resulting turn, as it arrives.

        The event stream is opened before the prompt is sent so nothing is missed. If the stream cannot
        be opened the blocking `ask` is used instead (messages then arrive all at once).
        """
        ref = uuid.uuid4().hex
        deadline = time.monotonic() + timeout_s
        types = ["prompt", "message", "activity", "turn.done"]
        try:
            try:
                conn, events = self.events([bot], types, timeout=timeout_s + 5)
            except GrokBotError as e:
                if not self._asleep(e):
                    raise
                self.wake()
                conn, events = self.events([bot], types, timeout=timeout_s + 5)
        except GrokBotError as e:
            log.warning("event stream unavailable (%s); falling back to blocking ask", e)
            turn = self.ask(bot, text, timeout_s)
            for m in turn.messages:
                on_message(m)
            return turn

        turn = Turn()
        try:
            self.send(bot, text, ref=ref)
            for etype, ev in events:
                if time.monotonic() > deadline:
                    raise ReplyTimeout(bot, timeout_s)
                refs = ev.get("refs") or []
                mine = not refs or ref in refs
                if etype == "message":
                    if ev.get("fromBot", True) and mine and ev.get("text", "").strip():
                        turn.messages.append(ev["text"])
                        on_message(ev["text"])
                elif etype == "activity":
                    if on_activity and ev.get("running") is not None:
                        on_activity(bool(ev["running"]))
                elif etype == "turn.done" and mine:
                    turn.done = True
                    return turn
            raise GrokBotError("event stream ended before the turn finished", "I lost the connection to your bot.")
        except socket.timeout as e:
            raise ReplyTimeout(bot, timeout_s) from e
        except (OSError, http.client.HTTPException) as e:
            raise GrokBotError(f"event stream failed: {e}", "I lost the connection to your bot.") from e
        finally:
            conn.close()


def _spoken_for(status: int, data: dict) -> str:
    err = str(data.get("error", "")).lower()
    if status == 404 or "no such" in err or "not found" in err:
        return "I can't find your bot. Run galatiqon provision first."
    if status in (401, 403):
        return "I'm not signed in to Grok Bot."
    if "rejected" in err or "limit" in err:
        return "Grok Bot turned that down. Maybe the usage limit."
    return "Grok Bot had a problem."


def _sse(resp: http.client.HTTPResponse) -> Iterator[tuple[str, dict]]:
    """Minimal Server-Sent Events parser: yields (event type, parsed JSON data)."""
    etype, data = "message", []
    for raw in resp:
        line = raw.decode("utf-8", errors="replace").rstrip("\r\n")
        if line == "":
            if data:
                try:
                    payload = json.loads("\n".join(data))
                except json.JSONDecodeError:
                    payload = {"text": "\n".join(data)}
                yield etype, payload
            etype, data = "message", []
            continue
        if line.startswith(":"):
            continue
        key, _, value = line.partition(":")
        value = value[1:] if value.startswith(" ") else value
        if key == "event":
            etype = value
        elif key == "data":
            data.append(value)


# --- subprocess transport ------------------------------------------------------------------------


class GbCli:
    """`gb ask` as a subprocess. Works without the daemon; the reply arrives all at once."""

    def __init__(self, binary: str = "gb"):
        self.binary = binary

    def ask(self, bot: str, text: str, timeout_s: float = 90) -> Turn:
        cmd = [self.binary, "ask", bot, text, "--json", "--timeout", f"{int(timeout_s)}s"]
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s + 20)
        except FileNotFoundError as e:
            raise GrokBotError(f"{self.binary} not found: install GrokBotCLI", "The Grok Bot client isn't installed.") from e
        except subprocess.TimeoutExpired as e:
            raise ReplyTimeout(bot, timeout_s) from e
        data: dict = {}
        for line in reversed(p.stdout.splitlines()):  # the JSON object is the last thing printed
            line = line.strip()
            if line.startswith("{"):
                try:
                    data = json.loads(line)
                    break
                except json.JSONDecodeError:
                    continue
        if p.returncode == 124:
            raise ReplyTimeout(bot, timeout_s)
        if p.returncode != 0:
            err = p.stderr.strip().splitlines()[-1] if p.stderr.strip() else f"exit {p.returncode}"
            raise GrokBotError(f"gb ask failed: {err}", _spoken_for(0, {"error": err}))
        msgs = [e.get("text") or _entry_text(e) for e in data.get("entries", []) if e.get("kind") != "tool-call"]
        msgs = [m for m in msgs if m]
        if not msgs and data.get("reply"):
            msgs = [data["reply"]]
        return Turn(messages=msgs, done=bool(data.get("done", True)))

    def ask_streaming(self, bot: str, text: str, on_message: OnMessage,
                      on_activity: OnActivity | None = None, timeout_s: float = 90) -> Turn:
        if on_activity:
            on_activity(True)
        turn = self.ask(bot, text, timeout_s)
        for m in turn.messages:
            on_message(m)
        return turn


def _entry_text(entry: dict) -> str:
    for key in ("text", "body", "content"):
        v = entry.get(key)
        if isinstance(v, str) and v.strip():
            return v
    return ""


# --- factory -------------------------------------------------------------------------------------


def make(cfg: GrokBotConfig):
    if cfg.transport == "cli":
        return GbCli(cfg.gb_binary)
    if cfg.transport != "gbd":
        raise ValueError(f"unknown [grokbot] transport {cfg.transport!r} (use 'gbd' or 'cli')")
    if cfg.gbd_url:
        return GbdClient(url=cfg.gbd_url, token=cfg.gbd_token, gb_binary=cfg.gb_binary)
    return GbdClient(socket_path=cfg.socket_path(), gb_binary=cfg.gb_binary)
