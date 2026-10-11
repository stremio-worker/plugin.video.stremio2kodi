#!/usr/bin/env python3
"""Package the Stremio2Kodi Kodi add-on into dist/.

Reads the add-on id and version from addon.xml and produces
``dist/<id>-<version>[-dev].zip`` containing ``<id>/`` as the top-level folder,
which is the layout Kodi expects for "Install from zip file".

Only runtime files are packaged (allowlist below); everything else in the repo
is dev tooling and is deliberately left out. If a new top-level entry appears
that is neither packaged nor a known dev-only entry, the script warns so it can
be classified instead of silently leaking into (or missing from) a release.

Run from anywhere:
    python3 scripts/package.py          # dist/plugin.video.stremio2kodi-1.1.1.zip
    python3 scripts/package.py --dev    # dist/plugin.video.stremio2kodi-1.1.1-dev.zip
"""
from __future__ import annotations

import argparse
import fnmatch
import os
import sys
import xml.etree.ElementTree as ET
import zipfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIST_DIR = os.path.join(ROOT, 'dist')

# --- Runtime content that belongs in the add-on zip (allowlist) -------------
# Top-level files to ship; missing ones are simply skipped.
INCLUDE_FILES = ('addon.xml', 'main.py', 'service.py', 'icon.png',
                 'fanart.jpg', 'LICENSE')
# Top-level directories to ship (recursively).
INCLUDE_DIRS = ('resources',)

# Never packaged, even inside an included directory.
EXCLUDE_DIRS = frozenset({'__pycache__'})
EXCLUDE_GLOBS = ('*.pyc', '*.pyo', '.DS_Store')

# Known top-level entries that are intentionally NOT packaged. Anything not in
# this set and not included above triggers a warning.
DEV_ONLY_ROOT = frozenset({
    '.git', '.github', '.gitignore', '.idea', '.vscode',
    'AGENTS.md', 'CHANGELOG.md', 'README.md', 'scripts', 'dist', 'build',
    '__pycache__',
})


def read_addon_info():
    """Return (addon_id, version) parsed from the root addon.xml."""
    root = ET.parse(os.path.join(ROOT, 'addon.xml')).getroot()
    return root.get('id'), root.get('version')


def _is_excluded_file(name):
    return any(fnmatch.fnmatch(name, pattern) for pattern in EXCLUDE_GLOBS)


def collect_files():
    """Yield (absolute_path, path_relative_to_repo) for files to package."""
    for name in INCLUDE_FILES:
        path = os.path.join(ROOT, name)
        if os.path.isfile(path):
            yield path, name

    for name in INCLUDE_DIRS:
        base = os.path.join(ROOT, name)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = sorted(
                d for d in dirnames if d not in EXCLUDE_DIRS)
            for filename in sorted(filenames):
                if _is_excluded_file(filename):
                    continue
                full = os.path.join(dirpath, filename)
                yield full, os.path.relpath(full, ROOT)


def unexpected_root_entries():
    """Top-level entries that are neither shipped nor known dev-only entries."""
    known = set(INCLUDE_FILES) | set(INCLUDE_DIRS) | DEV_ONLY_ROOT
    return sorted(name for name in os.listdir(ROOT) if name not in known)


def build_zip(addon_id, version, dev=False):
    """Write the add-on zip to dist/ and return (zip_path, file_count)."""
    suffix = '-dev' if dev else ''
    zip_name = '{}-{}{}.zip'.format(addon_id, version, suffix)
    os.makedirs(DIST_DIR, exist_ok=True)
    zip_path = os.path.join(DIST_DIR, zip_name)

    files = list(collect_files())
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for full, rel in files:
            archive.write(full, os.path.join(addon_id, rel))
    return zip_path, len(files)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description='Package the Kodi add-on into dist/.')
    parser.add_argument(
        '--dev', action='store_true',
        help='mark the archive as a dev build '
             '(<id>-<version>-dev.zip)')
    args = parser.parse_args(argv)

    addon_id, version = read_addon_info()
    if not addon_id or not version:
        parser.error('addon.xml is missing the "id" or "version" attribute')

    zip_path, count = build_zip(addon_id, version, dev=args.dev)
    print('Packaged {} files -> {}'.format(
        count, os.path.relpath(zip_path, ROOT)))

    for name in unexpected_root_entries():
        print('warning: top-level "{}" is neither packaged nor known '
              'dev-only; update INCLUDE_* or DEV_ONLY_ROOT '
              'in scripts/package.py'.format(name), file=sys.stderr)
    return 0


if __name__ == '__main__':
    sys.exit(main())
