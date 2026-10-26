#!/usr/bin/env bash
# Assembles the published site from the repo and a Godot web export:
#   site/index.html        the page (panels, chat, book; three.js fallback behind ?three=1)
#   site/godot/...         the Godot export, its wasm cut in parts under 25 MiB (Cloudflare's file limit)
#   site/godot/build.json  tells the page a Godot build is here
# Usage: godot/tools/build_site.sh <export dir> <site dir>
set -euo pipefail
EXPORT=$1
SITE=$2
ROOT=$(cd "$(dirname "$0")/../.." && pwd)
rm -rf "$SITE"
mkdir -p "$SITE/godot"
cp "$ROOT/index.html" "$SITE/"
find "$EXPORT" -maxdepth 1 -name "index.*" ! -name "*.import" -exec cp {} "$SITE/godot/" \;
rm "$SITE/godot/index.wasm"
( cd "$SITE/godot" && split -b 20m -d "$EXPORT/index.wasm" index.wasm.part )
python3 - "$SITE/godot" <<'PY'
import json, os, sys, subprocess
d = sys.argv[1]
parts = sorted(p for p in os.listdir(d) if p.startswith("index.wasm.part"))
json.dump({"parts": parts}, open(os.path.join(d, "index.wasm.parts.json"), "w"))
commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()
json.dump({"engine": "godot", "version": "4.7.2", "commit": commit}, open(os.path.join(d, "build.json"), "w"))
PY
du -sh "$SITE"/godot/* | sort -h | tail -5
