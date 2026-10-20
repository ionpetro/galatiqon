"""Config loading. Values come from a TOML file layered over these defaults."""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field, fields
from pathlib import Path

CONFIG_PATH = Path(os.environ.get("GALATIQON_CONFIG", "/etc/galatiqon/config.toml"))
SOCKET_PATH = Path(os.environ.get("GALATIQON_SOCKET", "/run/galatiqon/out.sock"))

DEFAULT_PROMPT = (
    "[Voice message from my Galatiqon device. I'm speaking, not typing, and I will hear your "
    "answer read aloud. Answer in at most 2 short sentences of plain words: no markdown, no "
    "emoji, no lists, no links. If I ask you to reach a teammate, message their Galatiqon bot "
    "and tell me when it's done.]"
)


@dataclass
class OwnerConfig:
    name: str = ""


@dataclass
class GrokBotConfig:
    bot: str = ""  # empty = "Galatiqon · <owner>"
    transport: str = "gbd"  # "gbd" or "cli"
    gbd_socket: str = ""  # empty = ~/.config/gb/default/gbd.sock
    gbd_url: str = ""  # TCP alternative, e.g. http://127.0.0.1:8787
    gbd_token: str = ""
    gb_binary: str = "gb"
    prompt_prefix: str = DEFAULT_PROMPT
    reply_timeout_s: float = 90.0
    ack_after_s: float = 4.0
    ack_phrases: list[str] = field(
        default_factory=lambda: ["On it.", "One sec.", "Checking.", "Let me look."]
    )

    def bot_name(self, owner: str) -> str:
        if self.bot:
            return self.bot
        return f"Galatiqon · {owner}" if owner else "Galatiqon"

    def socket_path(self) -> Path:
        if self.gbd_socket:
            return Path(self.gbd_socket)
        home = Path(os.environ.get("GB_HOME") or (Path.home() / ".config" / "gb"))
        return home / os.environ.get("GB_PROFILE", "default") / "gbd.sock"


@dataclass
class ButtonConfig:
    mode: str = "gpio"  # "gpio" or "keyboard"
    gpio_pin: int = 17  # BCM numbering; wire button between this pin and GND
    min_hold_s: float = 0.3  # ignore taps shorter than this


@dataclass
class AudioConfig:
    input_device: str = "default"  # ALSA name, see `arecord -L`
    max_record_s: float = 20.0


@dataclass
class SttConfig:
    vosk_model: str = "/opt/galatiqon/models/vosk-model-small-en-us-0.15"


@dataclass
class TtsConfig:
    engine: str = "piper"  # "piper", "espeak-ng", or "say" (macOS, for laptop demos)
    piper_voice: str = "/opt/galatiqon/voices/en_US-lessac-low.onnx"
    espeak_voice: str = "en-us"
    # Whole-word respellings applied only to what's spoken, not what's shown.
    pronunciations: dict[str, str] = field(default_factory=lambda: {"Galatiq": "Galatick"})


@dataclass
class DisplayConfig:
    backend: str = "pygame"  # "pygame" or "none"
    font_size: int = 28
    message_timeout_s: float = 30.0  # clear the screen after this


@dataclass
class ListenConfig:
    """galatiqon-listen: speaking what the bot writes when it wasn't the button that asked."""

    speak_device_turns: bool = False  # replies to push-to-talk prompts are spoken by ptt already
    say_command: str = ""  # empty = the local output daemon; else a command, text appended as last arg
    read_timeout_s: float = 90.0  # gbd pings every ~20s; reconnect if nothing arrives for this long


@dataclass
class Config:
    owner: OwnerConfig = field(default_factory=OwnerConfig)
    grokbot: GrokBotConfig = field(default_factory=GrokBotConfig)
    listen: ListenConfig = field(default_factory=ListenConfig)
    button: ButtonConfig = field(default_factory=ButtonConfig)
    audio: AudioConfig = field(default_factory=AudioConfig)
    stt: SttConfig = field(default_factory=SttConfig)
    tts: TtsConfig = field(default_factory=TtsConfig)
    display: DisplayConfig = field(default_factory=DisplayConfig)

    @property
    def bot(self) -> str:
        return self.grokbot.bot_name(self.owner.name)


def load(path: Path = CONFIG_PATH) -> Config:
    cfg = Config()
    if not path.exists():
        return cfg
    with path.open("rb") as f:
        data = tomllib.load(f)
    for section in fields(cfg):
        values = data.get(section.name, {})
        target = getattr(cfg, section.name)
        for key, value in values.items():
            if not hasattr(target, key):
                raise ValueError(f"unknown config key [{section.name}] {key}")
            setattr(target, key, value)
    return cfg
