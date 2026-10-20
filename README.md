# Galatiqon

Live site: https://galatiqon.vercel.app · Repository: https://github.com/ionpetro/galatiqon · Demo video: `web/public/galatiqon-demo.mp4` (`video/` has the Remotion source)

A personal push-to-talk device for each member of the Galatiq team: a Raspberry Pi with a button,
a mic, a speaker and a small screen, wired to that person's own **Grok Bot**. Hold the button, ask,
and the bot's answer is spoken and shown. The bots carry the company context, are connected to the
team's apps, and can talk to each other, so one Galatiqon can ask another owner's bot a question.

```
 [button] ──► galatiqon-ptt ──(Vosk, offline STT)──► gbd ──► Grok Bot cloud box ──► "Galatiqon · Scott"
                  │ status                            ▲ SSE: message / turn.done        ▲
                  ▼                                   └──────────────────────────────────┤
          galatiqon-output ◄── every bot message, as it arrives                          │
            ├─ screen (pygame / KMS)                                                     │
            └─ speaker (Piper TTS, espeak-ng fallback)              typed in the Grok Bot app,
                  ▲                                                 a routine, a teammate's bot
          galatiqon-listen ◄── gbd event stream: everything the bot writes that the button didn't ask
```

It is a sibling of [muse-bike](../muse-bike), which does the same for Meta's Muse. The voice
pipeline (STT, TTS, screen, output daemon) is the same code; the transport is new.

## Is there a Grok Bot SDK for a Raspberry Pi? (research, Oct 19 2026)

**No official one.** Grok Bot is closed source and has no public API, SDK, CLI or webhook surface
([overview](https://docs.x.ai/grok-bot/overview), [get started](https://docs.x.ai/grok-bot/get-started)).
Bots run on a cloud "box" (in Cursor's cloud; auth is Cursor's), and the only official clients are
the desktop app (macOS, Windows, **Linux x64 and arm64**: `.deb`, `.rpm`, AppImage from
[cursor.com/download/bot](https://cursor.com/download/bot)), the mobile apps, and `@bot` on X.
The Linux app is Electron, so it needs a display and a lot of RAM; not a fit for a headless Pi.

**Two unofficial projects fill the gap**, both reverse-engineered from the desktop app's protocol:

| Project | What it is | Pi |
|---|---|---|
| [GrokBotCLI](https://github.com/JiminLee-way/GrokBotCLI) (`gb`, MIT, v0.1.0, Oct 14 2026) | Headless client: login over SSH, `gb ask <bot> "..."`, bots, groups, files, routines, apps, plus a daemon (`gbd`) with a local HTTP API, SSE event stream and webhooks | **Static `gb-linux-arm64` binary**, runs on a 64-bit Pi |
| [grokbot-headless](https://github.com/andreanjos/grokbot-headless) | Runs the official package's *local-computer daemon* without Electron, so a bot can run commands on your Linux box (the Muse Gadget SDK analogue) | Needs the official arm64 `.deb` installed; Electron-sized |

Nobody has published a Pi voice device on either. So this project builds one on **GrokBotCLI's
daemon**: `galatiqon/grokbot.py` talks HTTP over `gbd`'s Unix socket, opens the SSE stream, sends
the prompt with a `ref`, and speaks every `message` event of that turn until `turn.done`. A
subprocess fallback (`gb ask --json`) works without the daemon. Both are verified against a fake
`gbd` in `tests/`.

Caveats: the protocol is internal and can change with a Grok Bot release; `gb` acts with the
signed-in account's full permissions (the device user has no sudo for that reason); Grok Bot
needs a SuperGrok or Cursor plan and has its own usage allowance.

## Web app, enclosure and dashboard

Like muse-bike, the project has three more pieces, now in one React site (`web/`):

| Piece | Where | What |
|---|---|---|
| 3D model | `enclosure/print/galatiqon_print.py` → `web/public/models/galatiqon-{body,face,button}.stl` + `galatiqon.glb`, guide in `enclosure/print/PRINT.md` | Print-simple puck (body, face cap, button cap) built with manifold3d + trimesh: flat chamfered back, 45° face chamfer, no supports, no screws. `enclosure/galatiqon.py` is the earlier fully rounded version |
| Live data | `galatiqon/dashboard.py` (stdlib, runs on the Pi, port 8080, CORS on) | Power flags, temperature, CPU, memory, Wi-Fi, services and the Grok Bot link as `/api/stats`, `/api/history` and an SSE stream at `/events`, plus its own phone-first page |
| Guide | `web/` Setup section | Parts, printing, wiring and the eight setup steps |

```bash
cd web && pnpm install && pnpm dev          # http://localhost:5173
bash scripts/deploy-web.sh                   # build locally, deploy to https://galatiqon.vercel.app
```

Branding follows galatiq.ai: their wordmark and G mark (extracted from the site's inline SVG into
`web/public/galatiq-logo.svg`, `galatiq-mark.svg` and `web/src/lib/brand.ts`), black with green `#009a6c`,
the dotted particle wave, white pill buttons. Their font is Aventa, which is not downloadable from the site; the
stack lists Aventa first and loads Albert Sans as the stand-in.

The hero is the GLB in react-three-fiber (orbit, explode, live screen line, the G mark as a decal). The Live section connects to
`http://galatiqon.local:8080` and falls back to a clearly labelled simulated feed when no device is reachable.
Rebuild the model with `python3 enclosure/galatiqon.py` (needs `manifold3d trimesh numpy matplotlib`).

## Hardware

Same as muse-bike: Raspberry Pi 3B+ or newer (64-bit Raspberry Pi OS Bookworm), USB mic, small
speaker (3.5 mm or USB), HDMI/DSI/SPI screen (optional), momentary button between GPIO17 and GND,
USB power. A Pi 4 or 5 makes STT and TTS noticeably faster.

## Setup (per device)

```bash
git clone <this repo> galatiqon && cd galatiqon
sudo bash scripts/setup.sh                 # apt, gb (checksum-verified), venv, Vosk + Piper models, services
sudo -u galatiqon -H gb login              # prints a URL: open it on your phone, approve
sudo systemctl start galatiqon-gbd         # the Grok Bot daemon
sudo -u galatiqon -H galatiqon-provision --owner "Scott" --team "Tom,Barric"
sudo nano /etc/galatiqon/config.toml       # [owner] name = "Scott"  (bot name defaults to "Galatiqon · Scott")
sudo systemctl restart galatiqon-ptt
```

Test without the mic:

```bash
sudo -u galatiqon galatiqon-say "Hello from the Galatiqon"
sudo -u galatiqon galatiqon-ask "what does Galatiq do?"
journalctl -u galatiqon-ptt -u galatiqon-listen -u galatiqon-output -u galatiqon-gbd -f
```

No button wired yet? Set `[button] mode = "keyboard"` and run `galatiqon-ptt` in a terminal:
Enter starts recording, Enter stops.

All bots live in one Grok Bot account (the team's), so `gb login` once per device with that
account, or copy `~galatiqon/.config/gb/default/credentials.json` from a provisioned device.

## Typing to the bot instead of talking

`galatiqon-listen` keeps the bot's event stream open and speaks every message the bot writes
that did not come from the button: something typed to it in the Grok Bot app on your phone or
laptop, a routine firing, a teammate's Galatiqon messaging in. What you typed is shown on the
screen as "You: ...", then the answer is spoken. Replies to push-to-talk are skipped, since
`galatiqon-ptt` already speaks them (gbd tags those with the `ref` ptt sends; messages from the
app carry none). If the stream drops it reconnects from the last event id, so nothing is lost.

It runs as a service on the device (`galatiqon-listen.service`, installed by `setup.sh`).
It can also run anywhere `gb` is signed in and speak through another machine, which is how the
muse-bike Pi gets a Grok Bot voice from a laptop:

```bash
# on the Pi, once: let `pi` run bike-say as the muse user without a password
echo 'pi ALL=(muse) NOPASSWD: /usr/local/bin/bike-say' | sudo tee /etc/sudoers.d/bike-say-bridge
# on the laptop (dev.toml has this say_command already)
GALATIQON_CONFIG=./dev.toml python3 -m galatiqon.listen
```

`galatiqon-listen --dry-run` prints instead of speaking; `--speak-device-turns` also speaks the
button's replies (for a device without ptt); `--since <id>` replays from a gbd event id.

## What `galatiqon-provision` sets up

- A bot named `Galatiqon · <owner>` with `context/BOT_INSTRUCTIONS.md` as its instructions:
  two spoken sentences, answer first, confirm before sending or changing anything, and how to
  reach the other Galatiqons.
- `context/COMPANY.md`, the company brief, sent to the bot as a file it keeps. Edit it, re-run.
- `context/skills/galatiqon/SKILL.md`, a skill for voice-style replies (shared by the account).
- With `--team`, the group chat "Galatiq team" containing every Galatiqon bot, so "ask Tom if he's
  free at three" becomes a bot-to-bot message and a spoken answer.

Connect the company's apps once in the Grok Bot desktop app or with `gb apps connect slack`
(also `gmail`, `google-calendar`, `notion`, your CRM); every bot in the account can then use them.

## Config

`/etc/galatiqon/config.toml`, see `config.example.toml`. Notable keys:

| Key | Meaning |
|---|---|
| `[owner] name` | Whose device this is; the bot name defaults to `Galatiqon · <name>` |
| `[grokbot] transport` | `gbd` (daemon, streams replies) or `cli` (`gb ask`, no daemon) |
| `[grokbot] reply_timeout_s`, `ack_after_s` | When to give up, and when to say "On it." while the bot works |
| `[grokbot] prompt_prefix` | The bracketed instruction sent with every utterance |
| `[button] mode` | `gpio` or `keyboard` |
| `[listen] say_command` | Empty = this device's speaker; or a command the text is appended to, e.g. `ssh pi@musebike.local sudo -n -u muse bike-say` |
| `[listen] speak_device_turns` | Also speak push-to-talk replies (default off: ptt speaks them) |
| `[tts] pronunciations` | e.g. `Galatiq = "Galatick"` so the voice says the name right |

## Development

```bash
python3 -m unittest discover -s tests -t . -v     # Python 3.11+, stdlib only
```

`tests/fake_gbd.py` is a small fake of the `gbd` API on a Unix socket. On a laptop (the console
scripts only exist after `pip install -e .`; otherwise use the `python3 -m galatiqon.<cmd>` form):

```bash
gb login && gb daemon run &                         # once; the box is woken automatically when asleep
python3 -m galatiqon.provision --owner Ion
export GALATIQON_CONFIG=./dev.toml GALATIQON_SOCKET=/tmp/galatiqon.sock
python3 -m galatiqon.output_daemon &                # speaks with macOS `say`
python3 -m galatiqon.ask "what does Galatiq do?"
```

## Layout

```
galatiqon/grokbot.py      the Grok Bot bridge (GbdClient over Unix socket + SSE, GbCli fallback)
galatiqon/ptt.py          button → arecord → Vosk → Conversation.ask → spoken replies
galatiqon/listen.py       gbd event stream → everything the bot writes that the button didn't ask → spoken
galatiqon/output_daemon.py, display.py, tts.py, stt.py, ipc.py    the muse-bike voice pipeline
galatiqon/provision.py    creates the bot, sends the brief, adds the skill, links the team group
context/                  COMPANY.md, BOT_INSTRUCTIONS.md, skills/galatiqon/SKILL.md
scripts/setup.sh, scripts/install-gb.sh, systemd/*.service
```
