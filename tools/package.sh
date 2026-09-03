#!/usr/bin/env bash
# 重新產生索引與圖示，並把 chrome-extension/ 打包成可上傳 Chrome Web Store 的 ZIP。
# manifest.json 會位於 ZIP 根目錄（商店要求）。
# 用法：bash tools/package.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EXT="$ROOT/chrome-extension"
DIST="$ROOT/dist"

node "$ROOT/tools/build-index.mjs"
python3 "$ROOT/tools/make_icons.py"

VERSION="$(node -p "require('$EXT/manifest.json').version")"
mkdir -p "$DIST"
OUT="$DIST/xs-blocks-extension-v$VERSION.zip"
rm -f "$OUT"
(cd "$EXT" && zip -qr "$OUT" . -x '.DS_Store' '*/.DS_Store')
echo "packaged: ${OUT#$ROOT/} ($(du -h "$OUT" | cut -f1))"
unzip -l "$OUT" | head -n 20
