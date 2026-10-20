#!/usr/bin/env bash
# Install GrokBotCLI (`gb`): the unofficial headless Grok Bot client that this device talks through.
# Verifies the release checksum before installing. Usage: sudo bash scripts/install-gb.sh [version]
set -euo pipefail

VERSION="${1:-v0.1.0}"
BASE="https://github.com/JiminLee-way/GrokBotCLI/releases/download/$VERSION"
case "$(uname -s)-$(uname -m)" in
  Linux-aarch64)  ASSET=gb-linux-arm64 ;;
  Linux-x86_64)   ASSET=gb-linux-amd64 ;;
  Darwin-arm64)   ASSET=gb-darwin-arm64 ;;
  Darwin-x86_64)  ASSET=gb-darwin-amd64 ;;
  *) echo "unsupported platform $(uname -s)-$(uname -m)" >&2; exit 1 ;;
esac

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
echo "== downloading $ASSET $VERSION"
curl -fsSL "$BASE/$ASSET" -o "$tmp/$ASSET"
curl -fsSL "$BASE/SHA256SUMS" -o "$tmp/SHA256SUMS"
(cd "$tmp" && grep " $ASSET\$" SHA256SUMS | sha256sum -c - 2>/dev/null || shasum -a 256 -c <(grep " $ASSET\$" SHA256SUMS))

install -m 0755 "$tmp/$ASSET" /usr/local/bin/gb
echo "== installed: $(gb version)"
