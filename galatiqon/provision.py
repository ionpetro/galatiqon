"""`galatiqon-provision`: create (or update) the Grok Bot behind a Galatiqon, with the company context.

What it does, using the `gb` CLI (GrokBotCLI):
  1. `gb bots create "Galatiqon · <owner>" -d <instructions>`   (or `gb bots update` if it exists)
  2. `gb skills add context/skills/galatiqon`                    the voice-reply skill (once per account)
  3. `gb send <bot> --file context/COMPANY.md "..."`             the company brief, kept in the bot's files
  4. optionally `gb groups create "Galatiq team" --member ...`   so the galatiqons can talk to each other

Run it on any machine where `gb login` has been done for the team's Grok Bot account (the Pi, or your
laptop). Bots live in the cloud, so the device only needs the bot's name afterwards.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

DEFAULT_CONTEXT = Path(os.environ.get("GALATIQON_CONTEXT", "/opt/galatiqon/context"))
REPO_CONTEXT = Path(__file__).resolve().parent.parent / "context"


def gb(binary: str, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    cmd = [binary, *args]
    print("$", " ".join(_q(a) for a in cmd))
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.stdout.strip():
        print(p.stdout.rstrip())
    if p.returncode != 0 and check:
        sys.exit(f"galatiqon-provision: `{binary} {args[0]}` failed: {p.stderr.strip() or p.stdout.strip()}")
    return p


def _q(s: str) -> str:
    return s if " " not in s and "\n" not in s else json.dumps(s if len(s) < 80 else s[:77] + "...")


def bot_exists(binary: str, name: str) -> bool:
    p = gb(binary, "bots", "list", "--json", check=False)
    if p.returncode != 0:
        return False
    try:
        bots = json.loads(p.stdout)
    except json.JSONDecodeError:
        return False
    if isinstance(bots, dict):
        bots = bots.get("bots") or bots.get("agents") or []
    return any(b.get("name") == name for b in bots if isinstance(b, dict))


def render(template: str, **vars: str) -> str:
    out = template
    for k, v in vars.items():
        out = out.replace("{" + k + "}", v)
    return out


def main() -> None:
    p = argparse.ArgumentParser(prog="galatiqon-provision", description="Create the Grok Bot behind a Galatiqon.")
    p.add_argument("--owner", required=True, help='first name of the person this device is for, e.g. "Scott"')
    p.add_argument("--bot", help='bot name (default "Galatiqon · <owner>")')
    p.add_argument("--context", type=Path, default=None, help="directory with COMPANY.md, BOT_INSTRUCTIONS.md, skills/")
    p.add_argument("--team", default="", help='comma-separated owners of the other galatiqons, e.g. "Tom,Barric"')
    p.add_argument("--group", default="Galatiq team", help="name of the group chat that links all galatiqons")
    p.add_argument("--gb", default=os.environ.get("GB_BINARY", "gb"), help="GrokBotCLI binary")
    p.add_argument("--no-skill", action="store_true")
    p.add_argument("--no-brief", action="store_true", help="don't send COMPANY.md")
    args = p.parse_args()

    ctx = args.context or (DEFAULT_CONTEXT if DEFAULT_CONTEXT.exists() else REPO_CONTEXT)
    instr_path, brief_path, skill_dir = ctx / "BOT_INSTRUCTIONS.md", ctx / "COMPANY.md", ctx / "skills" / "galatiqon"
    for f in (instr_path, brief_path):
        if not f.exists():
            sys.exit(f"galatiqon-provision: missing {f}")

    owner = args.owner.strip()
    bot = args.bot or f"Galatiqon · {owner}"
    team = [t.strip() for t in args.team.split(",") if t.strip() and t.strip() != owner]
    teammates = ", ".join(f"{t} (bot \"Galatiqon · {t}\")" for t in team) or "none configured yet"
    instructions = render(instr_path.read_text(), owner=owner, bot=bot, teammates=teammates, group=args.group)

    gb(args.gb, "whoami")
    if bot_exists(args.gb, bot):
        gb(args.gb, "bots", "update", bot, "-d", instructions, "--title", f"{owner}'s Galatiqon")
    else:
        gb(args.gb, "bots", "create", bot, "-d", instructions, "--title", f"{owner}'s Galatiqon",
           "--avatar-shape", "circle", "--avatar-color", "orange")

    if not args.no_skill and skill_dir.exists():
        gb(args.gb, "skills", "add", str(skill_dir), check=False)

    if not args.no_brief:
        gb(args.gb, "send", bot, "--file", str(brief_path),
           "This is the Galatiq company brief. Read it now, keep it in your files, and use it as your "
           "reference for everything about the company. Reply with one sentence confirming what Galatiq does.")

    if team:
        members = [bot] + [f"Galatiqon · {t}" for t in team]
        gl = gb(args.gb, "groups", "create", args.group, *sum([["--member", m] for m in members], []), check=False)
        if gl.returncode != 0:
            print(f"(group not created: {gl.stderr.strip()}; create it once every teammate's bot exists: "
                  f"gb groups create \"{args.group}\" --member ...)")

    print(f"\nDone. Put this in /etc/galatiqon/config.toml:\n\n[owner]\nname = \"{owner}\"\n\n"
          f"[grokbot]\nbot = \"{bot}\"\n\nThen: galatiqon-ask \"what does Galatiq do?\"")


if __name__ == "__main__":
    main()
