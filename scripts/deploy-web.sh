#!/usr/bin/env bash
# Build the site locally and deploy the static output to the Vercel project "galatiqon" (production).
# Building on Vercel from this repo layout tripped over pnpm/Node version detection, so the build
# happens here and only web/dist is uploaded. Needs: pnpm, the Vercel CLI, `vercel login` done once,
# and the repo root linked to the project (.vercel/project.json; `vercel link` if missing).
#   bash scripts/deploy-web.sh            # production
#   bash scripts/deploy-web.sh --preview  # preview URL only
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
[[ -f $ROOT/.vercel/project.json ]] || { echo "not linked: run 'vercel link' in $ROOT first" >&2; exit 1; }
pnpm --dir "$ROOT/web" install --frozen-lockfile
pnpm --dir "$ROOT/web" build
D="$(mktemp -d)"; trap 'rm -rf "$D"' EXIT
mkdir -p "$D/.vercel"
cp -R "$ROOT/web/dist/." "$D/"
cp "$ROOT/.vercel/project.json" "$D/.vercel/project.json"
cat > "$D/vercel.json" <<'JSON'
{
  "framework": null,
  "installCommand": "",
  "buildCommand": "",
  "cleanUrls": true,
  "headers": [
    { "source": "/models/(.*)", "headers": [{ "key": "Cache-Control", "value": "public, max-age=86400" }] },
    { "source": "/galatiqon-demo.mp4", "headers": [{ "key": "Cache-Control", "value": "public, max-age=86400" }] }
  ]
}
JSON
if [[ ${1:-} == --preview ]]; then
  vercel deploy --yes --cwd "$D"
else
  vercel deploy --prod --yes --cwd "$D"
fi
