# AGENTS.md

Kodi video add-on that browses and streams Stremio add-ons. Pure Python 3, no
compile step, no test suite, no linter config. `addon.xml` targets Kodi 21 (Omega)
via `xbmc.python 3.0.0`.

## Cannot be run/tested outside Kodi

Every module imports `xbmc`, `xbmcaddon`, `xbmcgui`, `xbmcplugin`, or `xbmcvfs`.
There is no CI test job, no `pytest`, no lint/typecheck command. Verification is
manual, inside Kodi 21+, by installing the add-on. Do not try to `python main.py`
to check a change; import errors are expected.

## Entrypoint and routing

- `main.py` is the plugin entrypoint. `sys.argv[1]` = plugin handle, `sys.argv[2]`
  = `?query` string.
- Dispatch is a single chain: `route()` parses `action` from the query and calls
  `_dispatch(action, params)`. A new view/command needs a new `elif action == ...`
  branch there. Unknown actions silently do nothing.
- `main.py` injects `resources/lib` into `sys.path`, so `resources/lib` modules are
  imported flat: `from stremio import StremioClient`, `from addon_manager import
  AddonManager`, `from player_setup import install_player_file`. Keep that style;
  do not add package-qualified imports.
- `resources/lib/stremio.py` is the Stremio Add-on Protocol HTTP client
  (manifest/catalog/stream/meta + `normalize_url`). `addon_manager.py` persists the
  configured add-on list to `stremio_addons.json` in the add-on profile dir.

## Two playback paths (do not break the contract)

1. **Standalone** (catalog browsing): `_play_streams` finds streams and plays via
   `xbmc.Player().play()`; auto-play iterates the sorted list as fallback.
2. **TMDbHelper**: `action=list_streams` emits a directory of streams and stashes
   them in Window(10000) property `stremio2kodi_streams_cache` (JSON, trimmed
   fields); `action=resolve` reads that index back and calls `setResolvedUrl`.
   The installed player JSON (`resources/player/stremio2kodi.json`) points
   TMDbHelper at these actions. Edit the JSON in `resources/player/`, not the copy
   installed under `addon_data/plugin.video.themoviedb.helper/players/`.

## Caching

Fetches are cached as JSON in `xbmcgui.Window(10000)` properties with TTLs
(`_MANIFEST_*`, `_META_CACHE_TTL`, `_CATALOG_CACHE_TTL`) and a negative cache for
failed manifests. Use the existing `_get_manifest` / `_get_meta_cached` /
`_get_catalog_cached` helpers rather than calling `StremioClient` directly, or you
bypass caching and back-navigation will re-fetch.

## Localization

All UI text goes through `L(id)` (`ADDON.getLocalizedString`). Any new string ID
must be added to the same numeric `msgctxt` in **both**
`resources/language/resource.language.en_gb/strings.po` and
`resources/language/resource.language.es_es/strings.po` (they are kept in sync).
`resources/settings.xml` labels reuse these same IDs.

## Packaging

`scripts/package.py` builds the installable zip into `dist/` from an allowlist of
runtime files (`addon.xml`, `main.py`, `service.py`, `icon.png`, `fanart.jpg`,
`LICENSE`, `resources/`); id/version come from `addon.xml`, and a warning is
printed for any unclassified top-level entry. Wrappers: `scripts/build.sh
[--dev]` and `scripts/clean.sh`. These are plain Python/bash and run outside
Kodi; they are the single source of truth for archive naming.

## Release is automatic on push

`.github/workflows/release.yml` runs on push to `main` or `dev`: it calls
`scripts/package.py` (`--dev` on the `dev` branch) to build the zip, creates a
GitHub release (`dev` becomes a prerelease), then dispatches an `addon_updated`
event to the `VSeryi/kodi` repository. To ship a change, bump `version` in
`addon.xml`; do not push unfinished work to `main`/`dev`.

## Optional integrations

- Torrent streams (`infoHash`) play through `plugin.video.elementum` if installed,
  otherwise fall back to a raw magnet URL.
- `ytId` streams play through `plugin.video.youtube`.
- `enrich_metadata` setting: `0` off, `1` fetch missing plot/art from a chosen
  Stremio meta add-on, `2` use the TMDB API via TMDbHelper's stored API key.
  TMDbHelper is optional; when absent, enrichment degrades gracefully.
