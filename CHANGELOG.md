# Changelog

All notable changes to this add-on are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [1.6.1] - 2026-10-11

### Added
- Subtitle support: subtitle tracks are fetched from add-ons declaring a
  `subtitles` resource (same manifest type/idPrefix filtering as streams) and
  attached to playback as selectable OSD tracks — standalone and TMDbHelper
  paths, toggleable via the new `fetch_subtitles` setting.
- Subtitle language filter: the `subtitle_langs` setting (e.g. `eng, tur`)
  keeps only subtitles whose `lang` matches; empty means all languages.
- Subtitles are downloaded to a local temp dir with descriptive names
  (`English (eng) - <file>.srt`) so the OSD shows readable track names
  instead of "Unknown N".
- `scripts/package.py` to build the installable add-on zip into `dist/`, plus
  `scripts/build.sh` and `scripts/clean.sh` wrappers.
- `AGENTS.md` with repository guidance for AI agents.

### Changed
- Release workflow now builds the zip via `scripts/package.py` instead of
  `rsync` + `zip`.
- Ignore the generated `dist/` directory.

## [1.1.1] - 2026-04-12

### Changed
- Improved the meta add-on selector dialog (preselects the saved add-on).

## [1.1.0] - 2026-04-12

### Added
- Catalog metadata enrichment: fill missing plot/poster/fanart from a chosen
  Stremio meta add-on (`enrich_metadata = 1`) or the TMDb API via TMDbHelper's
  API key (`enrich_metadata = 2`).
- Meta add-on selector UI and `meta_addon_url` setting.

### Changed
- Performance refactor: cache manifests, meta and catalogs in a `Window(10000)`
  property with TTLs, and fetch manifests/streams in parallel.

## [1.0.1] - 2026-04-12

### Added
- Initial release: browse catalogs from any Stremio add-on and stream movies
  and series, with quality/language sorting, HDR/Dolby Vision/IMAX/Remux
  detection, auto-play with next-best fallback, TMDbHelper integration for
  metadata and search, English and Spanish localization, and parallel stream
  searching across add-ons.
