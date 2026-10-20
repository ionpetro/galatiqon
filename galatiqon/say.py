"""`galatiqon-say`: speak and show text on the device. For scripts, routines and testing the speaker."""

from __future__ import annotations

import argparse
import sys

from . import ipc


def main() -> None:
    p = argparse.ArgumentParser(prog="galatiqon-say", description="Show and speak text on the Galatiqon.")
    p.add_argument("text", nargs="+", help="what to say")
    p.add_argument("--screen-only", action="store_true", help="show on screen without speaking")
    args = p.parse_args()

    try:
        ipc.say(" ".join(args.text), speak=not args.screen_only)
    except OSError as e:
        sys.exit(f"galatiqon-say: output daemon not reachable ({e}). Is galatiqon-output running?")
    print("delivered")


if __name__ == "__main__":
    main()
