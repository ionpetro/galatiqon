#!/usr/bin/env bash
# Install a Galatiqon on a Raspberry Pi (Raspberry Pi OS Bookworm 64-bit, Lite is fine).
#   sudo bash scripts/setup.sh
# Afterwards, sign the device in to the team's Grok Bot account (prints a URL to open on your phone):
#   sudo -u galatiqon -H gb login
set -euo pipefail

PREFIX=/opt/galatiqon
SVC_USER=galatiqon
VOSK_MODEL=vosk-model-small-en-us-0.15
PIPER_VOICE_URL=https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/low

[[ $EUID -eq 0 ]] || { echo "run with sudo" >&2; exit 1; }
[[ $(uname -m) == aarch64 ]] || echo "warning: not a 64-bit OS; the gb binary and piper-tts wheels need arm64" >&2

echo "== service user ($SVC_USER, no sudo: anything running as it can talk to your Grok Bot)"
id "$SVC_USER" >/dev/null 2>&1 || adduser --system --group --home "/home/$SVC_USER" --shell /usr/sbin/nologin "$SVC_USER"
mkdir -p "/home/$SVC_USER" && chown "$SVC_USER:$SVC_USER" "/home/$SVC_USER" && chmod 0750 "/home/$SVC_USER"
usermod -a -G audio,video,render,input,gpio "$SVC_USER" 2>/dev/null || true

echo "== apt packages"
apt-get update
apt-get install -y --no-install-recommends \
  python3-venv python3-gpiozero python3-lgpio python3-pygame \
  alsa-utils espeak-ng unzip curl ca-certificates

echo "== GrokBotCLI (gb)"
command -v gb >/dev/null || bash "$(dirname "$0")/install-gb.sh"

echo "== python env"
mkdir -p "$PREFIX/models" "$PREFIX/voices"
# system site packages so the apt-provided gpiozero/lgpio/pygame are visible
[[ -d $PREFIX/venv ]] || python3 -m venv --system-site-packages "$PREFIX/venv"
"$PREFIX/venv/bin/pip" install --upgrade pip
"$PREFIX/venv/bin/pip" install .
for cmd in galatiqon-say galatiqon-ask galatiqon-provision; do
  ln -sf "$PREFIX/venv/bin/$cmd" "/usr/local/bin/$cmd"
done

echo "== speech models"
if [[ ! -d $PREFIX/models/$VOSK_MODEL ]]; then
  curl -fL "https://alphacephei.com/vosk/models/$VOSK_MODEL.zip" -o /tmp/vosk.zip
  unzip -q /tmp/vosk.zip -d "$PREFIX/models" && rm /tmp/vosk.zip
fi
for f in en_US-lessac-low.onnx en_US-lessac-low.onnx.json; do
  [[ -f $PREFIX/voices/$f ]] || curl -fL "$PIPER_VOICE_URL/$f" -o "$PREFIX/voices/$f"
done

echo "== company context -> $PREFIX/context"
mkdir -p "$PREFIX/context"
cp -r context/. "$PREFIX/context/"

echo "== config"
mkdir -p /etc/galatiqon
[[ -f /etc/galatiqon/config.toml ]] || cp config.example.toml /etc/galatiqon/config.toml

echo "== services"
cp systemd/galatiqon-gbd.service systemd/galatiqon-output.service systemd/galatiqon-ptt.service \
   systemd/galatiqon-listen.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable --now galatiqon-output.service galatiqon-ptt.service galatiqon-listen.service
systemctl enable galatiqon-gbd.service   # started by hand after `gb login`

echo "== health dashboard (port 8080, runs as pi; the web app reads it)"
if id pi >/dev/null 2>&1; then
  install -m 0644 galatiqon/dashboard.py "$PREFIX/dashboard.py"
  cp systemd/galatiqon-dashboard.service /etc/systemd/system/
  systemctl daemon-reload
  systemctl enable galatiqon-dashboard.service
  systemctl restart galatiqon-dashboard.service
else
  echo "user 'pi' missing: skipping dashboard (edit User= in systemd/galatiqon-dashboard.service)" >&2
fi

cat <<MSG

Installed. Next:
  1. Sign in (prints a URL; open it on your phone or laptop):   sudo -u $SVC_USER -H gb login
  2. Start the Grok Bot daemon:                                  sudo systemctl start galatiqon-gbd
  3. Create this person's bot with the company context:          sudo -u $SVC_USER -H galatiqon-provision --owner "Scott" --team "Tom,Barric"
  4. Put the owner and bot name in /etc/galatiqon/config.toml, then:  sudo systemctl restart galatiqon-ptt
  5. Test:   sudo -u $SVC_USER galatiqon-say "Hello from the Galatiqon"
             sudo -u $SVC_USER galatiqon-ask "what does Galatiq do?"
Logs:        journalctl -u galatiqon-ptt -u galatiqon-listen -u galatiqon-output -u galatiqon-gbd -f
MSG
