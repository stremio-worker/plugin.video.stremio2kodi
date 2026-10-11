#!/usr/bin/env bash
# Remove Stremio2Kodi build artifacts.
#
# Deletes dist/ and build/, plus __pycache__/ and compiled *.pyc/*.pyo files
# anywhere in the tree (except .git). Safe to run at any time.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

rm -rf "$ROOT/dist" "$ROOT/build"

find "$ROOT" -path "$ROOT/.git" -prune -o \
    -type d -name __pycache__ -print0 | xargs -0 -r rm -rf
find "$ROOT" -path "$ROOT/.git" -prune -o \
    -type f \( -name '*.pyc' -o -name '*.pyo' \) -print0 | xargs -0 -r rm -f

echo "Cleaned dist/, build/, __pycache__ and compiled Python files."
