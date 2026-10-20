"""Newline-delimited JSON over a Unix socket, from clients to the output daemon.

Messages:
  {"type": "say", "text": "...", "speak": true}   show on screen (+ speak)
  {"type": "status", "text": "Thinking...", "body": "..."}   status line (+ optional body), not spoken
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

from .config import SOCKET_PATH


def send(msg: dict, path: Path = SOCKET_PATH) -> None:
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(5)
        s.connect(str(path))
        s.sendall(json.dumps(msg).encode() + b"\n")


def say(text: str, speak: bool = True) -> None:
    send({"type": "say", "text": text, "speak": speak})


def status(text: str, body: str | None = None) -> None:
    msg = {"type": "status", "text": text}
    if body is not None:
        msg["body"] = body
    send(msg)


def try_status(text: str, body: str | None = None) -> None:
    """Status updates are best-effort; don't crash if the output daemon is down."""
    try:
        status(text, body)
    except OSError:
        pass


def try_say(text: str, speak: bool = True) -> None:
    try:
        say(text, speak)
    except OSError:
        print(f"[galatiqon] {text}")
