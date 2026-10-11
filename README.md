# Stremio2Kodi

Browse and stream content from Stremio add-ons within Kodi.

## Features

- Browse catalogs from any Stremio add-on
- Stream movies and series with quality/language sorting
- HDR, Dolby Vision, IMAX, Remux detection and prioritization
- Subtitles support: fetch from Stremio add-ons, language filter, readable OSD track names
- TMDbHelper integration for metadata and search
- Multi-language support (English, Spanish)
- Parallel stream searching across multiple add-ons

## Installation

### From Repository (recommended)

1. Download the repository zip from [vseryi.github.io/kodi](https://vseryi.github.io/kodi/repository.vseryi4kodi-1.0.0.zip)
2. In Kodi: **Settings → Add-ons → Install from zip file**
3. Then: **Install from repository → VSeryi4Kodi → Video add-ons → Stremio2Kodi**

### Manual

1. Download the latest release from [Releases](https://github.com/VSeryi/plugin.video.stremio2kodi/releases)
2. In Kodi: **Settings → Add-ons → Install from zip file**

## Configuration

- **Fetch subtitles from addons** – Download subtitle tracks from Stremio add-ons (toggleable)
- **Subtitle languages** – Filter subtitles by comma-separated ISO codes (e.g. `eng, tur`); leave empty for all
- **Sort order** – Language → Quality → Size (default), or Quality/Size first
- **Preferred language** – Auto-detect from Kodi or manual selection
- **Preferred quality** – Best available, 4K, 1080p, or 720p

## Adding Stremio Add-ons

1. Open Stremio2Kodi → **Manage Add-ons** → **Add new add-on**
2. Paste the Stremio add-on configure/manifest URL
3. The add-on's catalogs and streams will be available immediately

## Requirements

- Kodi 21 (Omega) or later
- [TMDbHelper](https://github.com/jurialmunkey/plugin.video.themoviedb.helper) (optional, for metadata integration)

## License

GPL-3.0 – See [LICENSE](LICENSE)
