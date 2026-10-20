"""`galatiqon-ask`: send a typed question as if it were spoken. For testing without a mic or button."""

from __future__ import annotations

import argparse
import logging
import sys

from . import config, grokbot
from .ptt import Conversation


def main() -> None:
    p = argparse.ArgumentParser(prog="galatiqon-ask", description="Ask your Galatiqon bot by typing.")
    p.add_argument("text", nargs="+")
    p.add_argument("--bot", help="override the bot name from the config")
    p.add_argument("--raw", action="store_true", help="send the text without the voice-reply instructions")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

    cfg = config.load()
    if args.bot:
        cfg.grokbot.bot = args.bot
    if args.raw:
        cfg.grokbot.prompt_prefix = ""
    try:
        turn = Conversation(cfg).ask(" ".join(args.text))
    except grokbot.GrokBotError as e:
        sys.exit(f"galatiqon-ask: {e}")
    print(turn.reply)


if __name__ == "__main__":
    main()
