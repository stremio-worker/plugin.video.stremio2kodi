#!/usr/bin/env bash
# Build the Stremio2Kodi Kodi add-on zip into dist/.
#
# Usage:
#   scripts/build.sh          # dist/plugin.video.stremio2kodi-<version>.zip
#   scripts/build.sh --dev    # dist/plugin.video.stremio2kodi-<version>-dev.zip
#
# All arguments are forwarded to scripts/package.py, which owns the packaging
# logic (allowlist, version from addon.xml).
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$SCRIPT_DIR/package.py" "$@"
