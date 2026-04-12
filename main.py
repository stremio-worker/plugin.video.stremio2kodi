"""Stremio2Kodi – Browse and stream content from Stremio add-ons in Kodi."""
import json
import re
import sys
import os
import time
import traceback
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FuturesTimeoutError

import xbmc
import xbmcaddon
import xbmcgui
import xbmcplugin
import xbmcvfs

ADDON = xbmcaddon.Addon()
ADDON_PATH = xbmcvfs.translatePath(ADDON.getAddonInfo('path'))
ADDON_NAME = ADDON.getAddonInfo('name')
_FALLBACK_ICON = os.path.join(
    xbmcvfs.translatePath(ADDON.getAddonInfo('path')), 'icon.png')
sys.path.insert(0, os.path.join(ADDON_PATH, 'resources', 'lib'))

from stremio import StremioClient           # noqa: E402
from addon_manager import AddonManager      # noqa: E402
from player_setup import install_player_file  # noqa: E402

HANDLE = int(sys.argv[1])
BASE_URL = sys.argv[0]


def L(string_id):
    """Localized string lookup. Falls back to empty string."""
    return ADDON.getLocalizedString(string_id)

addon_mgr = AddonManager()
stremio = StremioClient(
    timeout=ADDON.getSettingInt('request_timeout') or 15
)
_monitor = xbmc.Monitor()

# Pre-compiled regexes (avoid re-compiling on every call)
_RE_DURATION = re.compile(r'(?:(\d+)\s*h)?\s*(?:(\d+)\s*min)?')
_RE_QUALITY = re.compile(
    r'(8[Kk]|2160p|4[Kk]|1080p|720p|480p|DVDRip|BDRip|WEBRip|WEB-DL|HDTV)',
    re.IGNORECASE)
_RE_SIZE = re.compile(r'\U0001F4BE\s*([\d.]+)\s*(TB|GB|MB)', re.IGNORECASE)
_RE_LANG_FLAG = re.compile(r'[\U0001F1E0-\U0001F1FF]{2}')
_RE_VIDEO_CODEC = re.compile(
    r'\b(HEVC|H\.?265|x265|AVC|H\.?264|x264|AV1|VP9|MPEG-?2|XviD)\b',
    re.IGNORECASE)
_RE_AUDIO_CODEC = re.compile(
    r'\b(TrueHD|DTS[- ]?HD(?:\s*MA)?|DTS|Atmos|EAC3|E-AC-3|AC3|DD[P+]?|'
    r'DDP?\d?\.?\d?|AAC|FLAC|OPUS|MP3|PCM)\b',
    re.IGNORECASE)
_RE_AUDIO_CHANNELS = re.compile(r'\b([27])\.([01])\b')
_RE_HDR = re.compile(
    r'\b(Dolby\s*Vision|DV)\b|\b(HDR10\+)\b|\b(HDR10)\b|\b(HDR)\b|\b(SDR)\b',
    re.IGNORECASE)
_RE_REMUX = re.compile(r'\bRemux\b|\(R\)', re.IGNORECASE)
_RE_IMAX = re.compile(r'\bIMAX\b', re.IGNORECASE)
_RE_SEEDS = re.compile(r'\U0001F464\s*(\d+)')
_QUALITY_ORDER = ('8k', '2160p', '1080p', '720p', '480p', 'dvdrip', 'bdrip',
                  'webrip', 'web-dl', 'hdtv', 'other')
_QUALITY_RANK = {q: i for i, q in enumerate(_QUALITY_ORDER)}

# Flag emoji → ISO 639-1 mapping (common flags seen in Stremio addons)
_FLAG_TO_LANG = {
    '\U0001F1EA\U0001F1F8': 'es', '\U0001F1F2\U0001F1FD': 'es',  # 🇪🇸 🇲🇽
    '\U0001F1E6\U0001F1F7': 'es', '\U0001F1E8\U0001F1F4': 'es',  # 🇦🇷 🇨🇴
    '\U0001F1E8\U0001F1F1': 'es', '\U0001F1FB\U0001F1EA': 'es',  # 🇨🇱 🇻🇪
    '\U0001F1EC\U0001F1E7': 'en', '\U0001F1FA\U0001F1F8': 'en',  # 🇬🇧 🇺🇸
    '\U0001F1E6\U0001F1FA': 'en', '\U0001F1E8\U0001F1E6': 'en',  # 🇦🇺 🇨🇦
    '\U0001F1EB\U0001F1F7': 'fr', '\U0001F1E9\U0001F1EA': 'de',  # 🇫🇷 🇩🇪
    '\U0001F1EE\U0001F1F9': 'it', '\U0001F1F5\U0001F1F9': 'pt',  # 🇮🇹 🇵🇹
    '\U0001F1E7\U0001F1F7': 'pt', '\U0001F1F7\U0001F1FA': 'ru',  # 🇧🇷 🇷🇺
    '\U0001F1EF\U0001F1F5': 'ja', '\U0001F1F0\U0001F1F7': 'ko',  # 🇯🇵 🇰🇷
    '\U0001F1E8\U0001F1F3': 'zh',                                   # 🇨🇳
}

# Text-based language keywords → ISO 639-1 (case-insensitive)
_LANG_KEYWORDS = {
    'es': re.compile(
        r'\b(?:spanish|espa[ñn]ol|castellano|spa(?:nish)?|latino|lat|'
        r'es[_-](?:es|mx|ar|co|cl))\b', re.IGNORECASE),
    'en': re.compile(
        r'\b(?:english|eng(?:lish)?|en[_-](?:us|gb|au|ca))\b', re.IGNORECASE),
    'fr': re.compile(
        r'\b(?:french|fran[çc]ais|fre(?:nch)?|fr[_-](?:fr|ca))\b',
        re.IGNORECASE),
    'de': re.compile(
        r'\b(?:german|deutsch|ger(?:man)?|de[_-]de)\b', re.IGNORECASE),
    'it': re.compile(
        r'\b(?:italian|italiano|ita(?:lian)?)\b', re.IGNORECASE),
    'pt': re.compile(
        r'\b(?:portuguese|portugu[eê]s|por|pt[_-](?:br|pt))\b',
        re.IGNORECASE),
    'ru': re.compile(r'\b(?:russian|rus(?:sian)?)\b', re.IGNORECASE),
    'ja': re.compile(r'\b(?:japanese|jpn?)\b', re.IGNORECASE),
    'ko': re.compile(r'\b(?:korean|kor(?:ean)?)\b', re.IGNORECASE),
    'zh': re.compile(r'\b(?:chinese|chi(?:nese)?)\b', re.IGNORECASE),
}

_KODI_LANG = xbmc.getLanguage(xbmc.ISO_639_1)

# Settings enum index → ISO 639-1 for preferred language
_PREF_LANG_MAP = (
    None,   # 0 = Auto (Kodi language)
    'en',   # 1 = English
    'es',   # 2 = Español
    'fr',   # 3 = Français
    'de',   # 4 = Deutsch
    'it',   # 5 = Italiano
    'pt',   # 6 = Português
    'ru',   # 7 = Русский
    'ja',   # 8 = 日本語
    'ko',   # 9 = 한국어
    'zh',   # 10 = 中文
)

# Settings enum index → quality key
_PREF_QUALITY_MAP = (
    None,     # 0 = Best available
    '2160p',  # 1 = 4K / 2160p
    '1080p',  # 2 = 1080p
    '720p',   # 3 = 720p
)

# Max parallel workers – keep low for constrained devices (TVs, SBCs)
_MAX_WORKERS = ADDON.getSettingInt('max_workers') or 4


# ---------------------------------------------------------------------------
#  Helpers
# ---------------------------------------------------------------------------

# Stremio type → localized string ID
_TYPE_LABELS = {
    'movie': 30115,
    'series': 30116,
    'channel': 30117,
    'tv': 30118,
}


def build_url(action, **params):
    params['action'] = action
    return '{}?{}'.format(BASE_URL, urllib.parse.urlencode(params))


def _parse_duration(value):
    """Convert a duration value to seconds (int). Handles int, '92',
    '1h32min', '2h', '45min', etc.  Returns None on failure."""
    if isinstance(value, (int, float)):
        return int(value)
    if not isinstance(value, str):
        return None
    value = value.strip()
    if value.isdigit():
        return int(value)
    m = _RE_DURATION.match(value)
    if m and (m.group(1) or m.group(2)):
        hours = int(m.group(1) or 0)
        mins = int(m.group(2) or 0)
        return hours * 3600 + mins * 60
    return None


def _names_summary(names, max_shown=3):
    """Join a list of names, truncating with '+N more' if needed."""
    if not names:
        return ''
    if len(names) <= max_shown:
        return ', '.join(names)
    return '{}, +{} more'.format(', '.join(names[:max_shown]),
                                 len(names) - max_shown)


def _quality_summary(streams):
    """Build a short quality summary like '2160p×2  1080p×5  720p×1'."""
    counts = {}
    for s in streams:
        text = '{} {}'.format(s.get('name', ''), s.get('title', ''))
        m = _RE_QUALITY.search(text)
        if m:
            q = m.group(1).lower()
            if q in ('4k',):
                q = '2160p'
            elif q in ('8k',):
                q = '8k'
            counts[q] = counts.get(q, 0) + 1
        else:
            counts['other'] = counts.get('other', 0) + 1
    return '  '.join('{}×{}'.format(q, counts[q])
                     for q in _QUALITY_ORDER if q in counts)


# Stremio meta → Kodi meta field mapping (module-level, allocated once)
_META_FIELD_MAP = (
    ('title', 'name'),
    ('plot', 'description'),
    ('poster', 'poster'),
    ('fanart', 'background'),
    ('clearlogo', 'logo'),
    ('imdbnumber', 'imdb_id'),
    ('tagline', 'tagline'),
    ('mpaa', 'mpaa'),
    ('duration', 'runtime'),
)


def _merge_stremio_meta(meta_info, meta):
    """Copy missing fields from a Stremio meta dict into meta_info."""
    for dst, src in _META_FIELD_MAP:
        if not meta_info.get(dst) and meta.get(src):
            meta_info[dst] = meta[src]
    if not meta_info.get('year') and meta.get('releaseInfo'):
        try:
            meta_info['year'] = str(int(meta['releaseInfo'][:4]))
        except (ValueError, TypeError):
            pass
    if not meta_info.get('genre') and meta.get('genres'):
        meta_info['genre'] = meta['genres']
    if not meta_info.get('rating') and meta.get('imdbRating'):
        try:
            meta_info['rating'] = str(float(meta['imdbRating']))
        except (ValueError, TypeError):
            pass


def set_video_info(li, info):
    """Set video info using InfoTagVideo (Kodi 21+) or fallback to setInfo."""
    try:
        tag = li.getVideoInfoTag()
        if info.get('mediatype'):
            tag.setMediaType(info['mediatype'])
        if info.get('plot'):
            tag.setPlot(info['plot'])
        if info.get('year'):
            tag.setYear(int(info['year']))
        if info.get('rating'):
            tag.setRating(float(info['rating']))
        if info.get('genre'):
            genres = info['genre']
            if isinstance(genres, str):
                genres = [genres]
            tag.setGenres(genres)
        if info.get('season'):
            tag.setSeason(int(info['season']))
        if info.get('episode'):
            tag.setEpisode(int(info['episode']))
        if info.get('title'):
            tag.setTitle(info['title'])
        if info.get('imdbnumber'):
            tag.setIMDBNumber(info['imdbnumber'])
            tag.setUniqueIDs({'imdb': info['imdbnumber']}, 'imdb')
        if info.get('tagline'):
            tag.setTagLine(info['tagline'])
        if info.get('mpaa'):
            tag.setMpaa(info['mpaa'])
        if info.get('duration'):
            tag.setDuration(int(info['duration']))
    except AttributeError:
        li.setInfo('video', info)


# Manifest cache via Window(10000) – survives across plugin invocations
_MANIFEST_CACHE_TTL = 300  # seconds
_MANIFEST_NEG_TTL = 60     # cache failures for 60s to avoid re-blocking
_META_CACHE_TTL = 300      # 5 min for meta (seasons/episodes)
_CATALOG_CACHE_TTL = 120   # 2 min for catalog listings

_win_home = xbmcgui.Window(10000)


def _cache_get(key):
    """Read a JSON value from the Window(10000) cache. Returns None on miss."""
    raw = _win_home.getProperty(key)
    if raw:
        try:
            data = json.loads(raw)
            if time.time() - data.get('_ts', 0) < data.get('_ttl', 0):
                return data['v']
        except (ValueError, KeyError):
            pass
    return None


def _cache_set(key, value, ttl):
    """Store a JSON value in the Window(10000) cache with a TTL."""
    _win_home.setProperty(key, json.dumps(
        {'v': value, '_ts': time.time(), '_ttl': ttl}))


def _get_manifest(base_url, timeout=None):
    """Fetch manifest with caching to avoid re-fetching on back-navigation."""
    norm_url = stremio.normalize_url(base_url)
    cache_key = 'stremio2kodi.manifest.{}'.format(norm_url)
    cached = _cache_get(cache_key)
    if cached is not None:
        # Negative cache: {'_neg': True} means previous fetch failed
        if isinstance(cached, dict) and cached.get('_neg'):
            return None
        return cached
    manifest = stremio.get_manifest(base_url, timeout=timeout)
    if manifest:
        _cache_set(cache_key, manifest, _MANIFEST_CACHE_TTL)
    else:
        # Cache failures so we don't block on slow addons every time
        _cache_set(cache_key, {'_neg': True}, _MANIFEST_NEG_TTL)
    return manifest


def _get_meta_cached(base_url, type_, id_):
    """Fetch Stremio meta with caching (seasons/episodes stay cached)."""
    cache_key = 'stremio2kodi.meta.{}.{}.{}'.format(
        stremio.normalize_url(base_url), type_, id_)
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    result = stremio.get_meta(base_url, type_, id_)
    if result:
        _cache_set(cache_key, result, _META_CACHE_TTL)
    return result


def _get_catalog_cached(base_url, type_, catalog_id, extra=None):
    """Fetch Stremio catalog with caching."""
    cache_key = 'stremio2kodi.catalog.{}.{}.{}.{}'.format(
        stremio.normalize_url(base_url), type_, catalog_id, extra or '')
    cached = _cache_get(cache_key)
    if cached is not None:
        return cached
    result = stremio.get_catalog(base_url, type_, catalog_id, extra=extra)
    if result:
        _cache_set(cache_key, result, _CATALOG_CACHE_TTL)
    return result


def add_dir(label, action, is_folder=True, art=None, info=None, **params):
    """Convenience wrapper for addDirectoryItem."""
    li = xbmcgui.ListItem(label)
    if art:
        li.setArt(art)
    if info:
        set_video_info(li, info)
    url = build_url(action, **params)
    xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=is_folder)
    return li


# ---------------------------------------------------------------------------
#  Main menu
# ---------------------------------------------------------------------------

def main_menu():
    add_dir(L(30000), 'catalogs',
            art={'icon': 'DefaultVideoPlaylists.png'})
    add_dir(L(30001), 'manage',
            art={'icon': 'DefaultAddonProgram.png'})
    add_dir(L(30002), 'install_player',
            is_folder=False,
            art={'icon': 'DefaultAddonService.png'})
    xbmcplugin.endOfDirectory(HANDLE)


# ---------------------------------------------------------------------------
#  Catalog browsing
# ---------------------------------------------------------------------------

def catalogs_menu():
    """List Stremio add-ons that expose catalogs."""
    addons = addon_mgr.get_addons()
    if not addons:
        xbmcgui.Dialog().notification(
            ADDON_NAME, L(30010),
            xbmcgui.NOTIFICATION_WARNING)
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return

    # Parallel manifest fetch – avoids blocking on slow addons
    manifests = [None] * len(addons)
    workers = min(_MAX_WORKERS, len(addons))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_get_manifest, a['url']): i
                   for i, a in enumerate(addons)}
        for future in as_completed(futures):
            if _monitor.abortRequested():
                xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
                return
            manifests[futures[future]] = future.result()

    found = False
    for idx, manifest in enumerate(manifests):
        if not manifest or not manifest.get('catalogs'):
            continue
        found = True
        addon_info = addons[idx]
        name = manifest.get('name', addon_info.get('name', addon_info['url']))
        logo = manifest.get('logo', '')
        art = {
            'icon': logo or _FALLBACK_ICON,
            'thumb': logo or _FALLBACK_ICON,
        }
        desc = manifest.get('description', '')
        add_dir(name, 'addon_catalogs', art=art,
                info={'plot': desc} if desc else None, idx=str(idx))

    if not found:
        xbmcgui.Dialog().notification(
            ADDON_NAME, L(30011),
            xbmcgui.NOTIFICATION_INFO)
    xbmcplugin.endOfDirectory(HANDLE)


def addon_catalogs(idx):
    """List the individual catalogs of one Stremio add-on."""
    addons = addon_mgr.get_addons()
    if idx >= len(addons):
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return

    manifest = _get_manifest(addons[idx]['url'])
    if not manifest:
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return

    for cat in manifest.get('catalogs', []):
        name = cat.get('name', cat.get('id', 'Unknown'))
        cat_type = cat.get('type', 'unknown')
        type_str_id = _TYPE_LABELS.get(cat_type)
        type_label = (L(type_str_id) if type_str_id else '') or cat_type.capitalize()
        label = '{} - {}'.format(type_label, name)
        # If catalog has filterable extras (genre, year, etc.), show sub-menu
        has_filters = any(
            e.get('options') for e in cat.get('extra', [])
            if e.get('name') != 'skip'
        )
        if has_filters:
            add_dir(label, 'catalog_filters', idx=str(idx),
                    type=cat_type, id=cat['id'])
        else:
            add_dir(label, 'catalog', idx=str(idx),
                    type=cat_type, id=cat['id'])

    xbmcplugin.endOfDirectory(HANDLE)


def catalog_filters(idx, cat_type, cat_id):
    """Show filter options for a catalog that supports extras."""
    addons = addon_mgr.get_addons()
    if idx >= len(addons):
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return

    manifest = _get_manifest(addons[idx]['url'])
    if not manifest:
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return

    # Find this catalog in the manifest
    cat = None
    for c in manifest.get('catalogs', []):
        if c.get('id') == cat_id and c.get('type', 'unknown') == cat_type:
            cat = c
            break
    if not cat:
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return

    # "Browse All" entry (unfiltered)
    add_dir(L(30012), 'catalog', idx=str(idx),
            type=cat_type, id=cat_id)

    # One folder per filterable extra that has options
    for extra in cat.get('extra', []):
        extra_name = extra.get('name', '')
        if extra_name == 'skip' or not extra.get('options'):
            continue
        label = L(30013)
        add_dir(label, 'catalog_filter_values', idx=str(idx),
                type=cat_type, id=cat_id, extra_name=extra_name)

    xbmcplugin.endOfDirectory(HANDLE)


def catalog_filter_values(idx, cat_type, cat_id, extra_name):
    """Show selectable values for a specific catalog extra (e.g. genre list)."""
    addons = addon_mgr.get_addons()
    if idx >= len(addons):
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return

    manifest = _get_manifest(addons[idx]['url'])
    if not manifest:
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return

    # Find this catalog and the extra definition
    options = []
    for c in manifest.get('catalogs', []):
        if c.get('id') == cat_id and c.get('type', 'unknown') == cat_type:
            for extra in c.get('extra', []):
                if extra.get('name') == extra_name:
                    options = extra.get('options', [])
                    break
            break

    if not options:
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return

    for value in options:
        add_dir(str(value), 'catalog', idx=str(idx),
                type=cat_type, id=cat_id,
                extra_name=extra_name, extra_value=str(value))

    xbmcplugin.endOfDirectory(HANDLE)


def catalog_browse(idx, cat_type, cat_id, skip=None,
                   extra_name=None, extra_value=None):
    """Browse items inside one catalog, optionally filtered by an extra."""
    addons = addon_mgr.get_addons()
    if idx >= len(addons):
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return

    # Build Stremio extra path segment: e.g. "genre=Action&skip=100"
    parts = []
    if extra_name and extra_value:
        parts.append('{}={}'.format(extra_name, extra_value))
    if skip:
        parts.append('skip={}'.format(skip))
    extra = '&'.join(parts) if parts else None

    catalog = _get_catalog_cached(
        addons[idx]['url'], cat_type, cat_id, extra=extra)
    if not catalog:
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return

    metas = catalog.get('metas', [])
    for meta in metas:
        _add_meta_item(meta, cat_type, idx)

    # Simple pagination (Stremio convention: 100 items per page)
    if len(metas) >= 100:
        next_skip = int(skip or 0) + len(metas)
        page_params = dict(idx=str(idx), type=cat_type, id=cat_id,
                           skip=str(next_skip))
        if extra_name and extra_value:
            page_params['extra_name'] = extra_name
            page_params['extra_value'] = extra_value
        add_dir(L(30014), 'catalog', **page_params)

    xbmcplugin.addSortMethod(HANDLE, xbmcplugin.SORT_METHOD_UNSORTED)
    xbmcplugin.setContent(HANDLE, 'movies' if cat_type == 'movie' else 'tvshows')
    xbmcplugin.endOfDirectory(HANDLE)


def _add_meta_item(meta, fallback_type, addon_idx):
    """Add a single catalog meta item to the directory listing."""
    title = meta.get('name', 'Unknown')
    li = xbmcgui.ListItem(title)

    # Artwork
    art = {}
    if meta.get('poster'):
        art['poster'] = meta['poster']
        art['thumb'] = meta['poster']
    if meta.get('background'):
        art['fanart'] = meta['background']
    if meta.get('logo'):
        art['clearlogo'] = meta['logo']
    li.setArt(art)

    # Info labels
    info = {}
    if meta.get('description'):
        info['plot'] = meta['description']
    if meta.get('releaseInfo') or meta.get('year'):
        raw = str(meta.get('releaseInfo', meta.get('year', '')))
        if raw.isdigit():
            info['year'] = int(raw)
    if meta.get('imdbRating'):
        try:
            info['rating'] = float(meta['imdbRating'])
        except (ValueError, TypeError):
            pass
    if meta.get('genres'):
        info['genre'] = meta['genres']
    set_video_info(li, info)

    meta_type = meta.get('type', fallback_type)
    # Prefer imdb_id; fall back to id only if it looks like a valid IMDB ID
    raw_id = meta.get('imdb_id') or meta.get('id', '')
    has_imdb = raw_id.startswith('tt')

    if meta_type in ('series', 'tv'):
        url = build_url('seasons', idx=str(addon_idx),
                        type='series', id=raw_id)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=True)
    else:
        play_params = dict(imdb_id=raw_id, title=title)
        if info.get('year'):
            play_params['year'] = str(info['year'])
        if meta.get('poster'):
            play_params['poster'] = meta['poster']
        if meta.get('background'):
            play_params['fanart'] = meta['background']
        if has_imdb:
            url = build_url('play_movie', **play_params)
        else:
            play_params['stype'] = meta_type
            play_params['aidx'] = str(addon_idx)
            url = build_url('play_movie', **play_params)
        xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=False)


# ---------------------------------------------------------------------------
#  Series  →  seasons  →  episodes
# ---------------------------------------------------------------------------

def show_seasons(addon_idx, meta_type, meta_id):
    """Show the seasons of a series as a directory listing."""
    videos = _fetch_videos(addon_idx, meta_type, meta_id)
    if not videos:
        xbmcgui.Dialog().notification(
            ADDON_NAME, L(30022),
            xbmcgui.NOTIFICATION_WARNING)
        xbmcplugin.endOfDirectory(HANDLE)
        return

    seasons = sorted(set(
        v.get('season', 0) for v in videos if v.get('season') is not None
    ))

    for s in seasons:
        label = (L(30023) or 'Specials') if s == 0 else L(30020).format(s)
        add_dir(label, 'episodes',
                type=meta_type, id=meta_id, season=str(s))

    xbmcplugin.setContent(HANDLE, 'seasons')
    xbmcplugin.endOfDirectory(HANDLE)


def show_episodes(meta_type, meta_id, season):
    """Show episodes for a given season."""
    videos = _fetch_videos(None, meta_type, meta_id)
    if not videos:
        xbmcplugin.endOfDirectory(HANDLE)
        return

    season_int = int(season)
    eps = sorted(
        [v for v in videos if v.get('season') == season_int],
        key=lambda v: v.get('episode', 0)
    )

    for ep in eps:
        ep_num = ep.get('episode', 0)
        title = ep.get('title') or ep.get('name') or L(30021).format(ep_num)
        label = '{}x{:02d} - {}'.format(season, ep_num, title)
        li = xbmcgui.ListItem(label)
        info = {'season': season_int, 'episode': ep_num}
        if ep.get('overview'):
            info['plot'] = ep['overview']
        set_video_info(li, info)
        if ep.get('thumbnail'):
            li.setArt({'thumb': ep['thumbnail']})

        url = build_url('play_episode', imdb_id=meta_id,
                        season=str(season), episode=str(ep_num))
        xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=False)

    xbmcplugin.setContent(HANDLE, 'episodes')
    xbmcplugin.endOfDirectory(HANDLE)


def _fetch_videos(preferred_idx, meta_type, meta_id):
    """Try to get episode/video list from Stremio meta endpoints."""
    addons = addon_mgr.get_addons()
    order = list(range(len(addons)))
    if preferred_idx is not None and preferred_idx < len(addons):
        order.remove(preferred_idx)
        order.insert(0, preferred_idx)

    for i in order:
        if _monitor.abortRequested():
            return None
        manifest = _get_manifest(addons[i]['url'])
        if not manifest or not stremio.has_resource(manifest, 'meta'):
            continue
        result = _get_meta_cached(addons[i]['url'], meta_type, meta_id)
        if result and result.get('meta', {}).get('videos'):
            return result['meta']['videos']
    return None


# ---------------------------------------------------------------------------
#  Playback  (streams)
# ---------------------------------------------------------------------------

def play_movie(imdb_id, stream_type='movie', addon_idx=None, meta_info=None):
    # For non-IMDB IDs, try fetching meta with embedded streams first
    if not imdb_id.startswith('tt') and addon_idx is not None:
        if _play_from_meta(stream_type, imdb_id, addon_idx, meta_info=meta_info):
            return
    _play_streams(stream_type, imdb_id, addon_idx=addon_idx, meta_info=meta_info)


def play_episode(imdb_id, season, episode, meta_info=None):
    stream_id = '{}:{}:{}'.format(imdb_id, season, episode)
    _play_streams('series', stream_id, meta_info=meta_info)


def _play_from_meta(meta_type, meta_id, addon_idx, meta_info=None):
    """Try to play a non-IMDB item using embedded streams from its meta.

    Some Stremio add-ons (e.g. Peerflix/RealDebrid) expose catalog items
    of type 'other' whose meta contains videos with embedded stream URLs.
    Returns True if streams were found and handled, False otherwise.
    """
    addons = addon_mgr.get_addons()
    if addon_idx >= len(addons):
        return False

    result = _get_meta_cached(addons[addon_idx]['url'], meta_type, meta_id)
    if not result or not result.get('meta'):
        return False

    meta = result['meta']
    videos = meta.get('videos', [])

    # Enrich meta_info from the fetched meta
    if meta_info is None:
        meta_info = {}
    _merge_stremio_meta(meta_info, meta)

    # Collect all embedded streams from all videos
    all_streams = []
    for video in videos:
        for stream in video.get('streams', []):
            stream['_addon'] = meta.get('name', addons[addon_idx].get('name', ''))
            # Use video title as fallback stream name
            if not stream.get('name') and not stream.get('title'):
                stream['title'] = video.get('title') or video.get('id', '')
            all_streams.append(stream)

    if not all_streams:
        return False

    selected = _pick_stream(all_streams)
    if selected < 0:
        return True  # User cancelled, but we handled it

    if ADDON.getSettingBool('auto_play'):
        for i in range(selected, len(all_streams)):
            if _try_play(all_streams[i], meta_info=meta_info):
                return True
        return False  # All streams failed
    else:
        _resolve_and_play(all_streams[selected], meta_info=meta_info)
    return True


def _build_stream_listitem(stream):
    """Build a ListItem for a stream with label, label2, streamdetails and art."""
    label, name_line = _stream_label(stream)
    li = xbmcgui.ListItem(label)
    sd = _parse_stream_details(stream)
    li.setLabel2(_stream_details_label(sd, name_line))
    # Video/audio stream info via InfoTagVideo (Kodi 21+)
    tag = li.getVideoInfoTag()
    if 'width' in sd or 'vcodec' in sd:
        vs = xbmc.VideoStreamDetail(
            width=sd.get('width', 0),
            height=sd.get('height', 0),
            codec=sd.get('vcodec', ''),
        )
        tag.addVideoStream(vs)
    acodec = sd.get('acodec', '')
    channels = sd.get('channels', 0)
    if sd.get('languages'):
        for lang in sd['languages']:
            tag.addAudioStream(xbmc.AudioStreamDetail(
                codec=acodec, channels=channels, language=lang))
    elif acodec or channels:
        tag.addAudioStream(xbmc.AudioStreamDetail(
            codec=acodec, channels=channels))
    logo = stream.get('_logo', '') or _FALLBACK_ICON
    li.setArt({'thumb': logo})
    return li


def _pick_stream(streams):
    """Auto-play best stream or show selection dialog. Returns index or -1."""
    streams.sort(key=_stream_sort_key)
    if ADDON.getSettingBool('auto_play'):
        return 0
    items = [_build_stream_listitem(s) for s in streams]
    return xbmcgui.Dialog().select(L(30030), items, useDetails=True)


def _enrich_meta_info(meta_info, stream_type, stream_id, addons):
    """Try to fetch plot/fanart/poster from Stremio meta for IMDB items."""
    base_id = stream_id.split(':')[0]  # strip :season:episode
    for addon_info in addons:
        if _monitor.abortRequested():
            return
        manifest = _get_manifest(addon_info['url'])
        if not manifest or not stremio.has_resource(manifest, 'meta'):
            continue
        try:
            result = _get_meta_cached(addon_info['url'], stream_type, base_id)
        except Exception:
            continue
        if result and result.get('meta'):
            _merge_stremio_meta(meta_info, result['meta'])
            break  # Got meta from one addon, that's enough


def _play_streams(stream_type, stream_id, addon_idx=None, meta_info=None):
    """Search add-ons for streams, let the user pick one, and play it.

    This is the standalone path (catalog browsing). The TMDbHelper path
    uses list_streams + resolve instead.
    """
    if meta_info is None:
        meta_info = {}

    addons = addon_mgr.get_addons()
    if stream_id.startswith('tt') and not meta_info.get('plot') and addons:
        _enrich_meta_info(meta_info, stream_type, stream_id, addons)

    all_streams = _search_streams(stream_type, stream_id, addon_idx=addon_idx)
    if not all_streams:
        return

    selected = _pick_stream(all_streams)
    if selected < 0:
        return

    if ADDON.getSettingBool('auto_play'):
        # Try each stream in sorted order, fall back on failure
        for i in range(selected, len(all_streams)):
            if _try_play(all_streams[i], meta_info=meta_info):
                return
        xbmcgui.Dialog().notification(
            ADDON_NAME, L(30033),
            xbmcgui.NOTIFICATION_ERROR)
    else:
        _resolve_and_play(all_streams[selected], meta_info=meta_info)


def _try_play(stream, meta_info=None):
    """Attempt to play a stream. Returns True if playback started, False otherwise."""
    if stream.get('externalUrl'):
        xbmc.executebuiltin(
            'RunPlugin({})'.format(stream['externalUrl']))
        return True

    url = _stream_to_url(stream)
    if not url:
        return False

    li = xbmcgui.ListItem(path=url)
    _set_li_metadata(li, meta_info)
    player = xbmc.Player()
    player.play(url, li)

    # Wait up to 10 seconds for playback to start
    for _ in range(100):
        if _monitor.waitForAbort(0.1):
            return False
        if player.isPlaying():
            return True
    return False


def _resolve_and_play(stream, meta_info=None):
    """Standalone play path: resolve stream URL and play via xbmc.Player()."""
    if stream.get('externalUrl'):
        xbmc.executebuiltin(
            'RunPlugin({})'.format(stream['externalUrl']))
        return

    url = _stream_to_url(stream)
    if not url:
        xbmcgui.Dialog().notification(
            ADDON_NAME, L(30033),
            xbmcgui.NOTIFICATION_ERROR)
        return

    li = xbmcgui.ListItem(path=url)
    _set_li_metadata(li, meta_info)
    xbmc.Player().play(url, li)


def _stream_sort_key(stream):
    """Sort key built from user settings: sort_order, preferred_lang, preferred_quality."""
    text = '{}\n{}'.format(stream.get('name', ''), stream.get('title', ''))

    # --- Preferred language from settings (enum index) or Kodi ---
    lang_idx = ADDON.getSettingInt('preferred_lang')
    pref_lang = (_PREF_LANG_MAP[lang_idx]
                 if lang_idx < len(_PREF_LANG_MAP) else None) or _KODI_LANG

    # --- Language rank: preferred = 0, other known = 1, unknown = 2 ---
    detected_langs = set()
    for flag_m in _RE_LANG_FLAG.finditer(text):
        lang = _FLAG_TO_LANG.get(flag_m.group())
        if lang:
            detected_langs.add(lang)
    for lang_code, pattern in _LANG_KEYWORDS.items():
        if pattern.search(text):
            detected_langs.add(lang_code)
    if detected_langs:
        lang_rank = 0 if pref_lang in detected_langs else 1
    else:
        lang_rank = 2

    # --- Quality rank ---
    q_m = _RE_QUALITY.search(text)
    if q_m:
        q = q_m.group(1).lower()
        if q in ('4k',):
            q = '2160p'
        elif q in ('8k',):
            q = '8k'
        quality_rank = _QUALITY_RANK.get(q, len(_QUALITY_ORDER))
    else:
        quality_rank = _QUALITY_RANK.get('other', len(_QUALITY_ORDER))

    # --- Preferred quality: boost matching streams ---
    q_idx = ADDON.getSettingInt('preferred_quality')
    pref_q = (_PREF_QUALITY_MAP[q_idx]
              if q_idx < len(_PREF_QUALITY_MAP) else None)
    if pref_q:
        pref_q_rank = _QUALITY_RANK.get(pref_q, 0)
        if quality_rank == pref_q_rank:
            quality_pref = 0
        elif quality_rank < pref_q_rank:
            quality_pref = 1  # better than preferred
        else:
            quality_pref = 2  # worse than preferred
    else:
        quality_pref = 0  # "Best available" — no preference penalty

    # --- HDR rank: DV best (0), then IMAX (1), HDR10+ (2), HDR10 (3), HDR (4), SDR (5), none (6) ---
    _HDR_RANK = {'DV': 0, 'IMAX': 1, 'HDR10+': 2, 'HDR10': 3, 'HDR': 4, 'SDR': 5}
    hdr_rank = 6  # no HDR info
    for hdr_m in _RE_HDR.finditer(text):
        if hdr_m.group(1):
            tag = 'DV'
        elif hdr_m.group(2):
            tag = 'HDR10+'
        elif hdr_m.group(3):
            tag = 'HDR10'
        elif hdr_m.group(4):
            tag = 'HDR'
        else:
            tag = 'SDR'
        r = _HDR_RANK[tag]
        if r < hdr_rank:
            hdr_rank = r
    if _RE_IMAX.search(text):
        r = _HDR_RANK['IMAX']
        if r < hdr_rank:
            hdr_rank = r

    # Infer 2160p quality when DV or IMAX present but no explicit resolution
    if quality_rank == _QUALITY_RANK.get('other', len(_QUALITY_ORDER)) and hdr_rank <= 1:
        quality_rank = _QUALITY_RANK.get('2160p', quality_rank)

    # --- Remux rank: remux (0) > non-remux (1) ---
    remux_rank = 0 if _RE_REMUX.search(text) else 1

    # --- Size: bigger first (negative for descending) ---
    size_m = _RE_SIZE.search(text)
    if size_m:
        size_gb = float(size_m.group(1))
        unit = size_m.group(2).upper()
        if unit == 'TB':
            size_gb *= 1024
        elif unit == 'MB':
            size_gb /= 1024
        size_rank = -size_gb
    else:
        size_rank = 0

    # --- Build sort tuple from user's chosen order (enum index) ---
    sort_idx = ADDON.getSettingInt('sort_order')
    if sort_idx == 1:    # Quality, Language, Size
        return (quality_pref, quality_rank, hdr_rank, remux_rank, lang_rank, size_rank)
    elif sort_idx == 2:  # Size, Quality, Language
        return (size_rank, quality_pref, quality_rank, hdr_rank, remux_rank, lang_rank)
    else:                # 0 = Language, Quality, Size (default)
        return (lang_rank, quality_pref, quality_rank, hdr_rank, remux_rank, size_rank)


def _stream_label(stream):
    """Return (main_label, name_line) from stream name/title.

    main_label  = title first line (shown as line 1 in dialog).
    name_line   = name first line (prepended to label2 / line 2).
    """
    name = stream.get('name', '')
    name_line = name.split('\n')[0].strip() if name else ''
    title = stream.get('title', '')
    title_line = title.split('\n')[0].strip() if title else ''
    main = title_line or name_line or 'Unknown Source'
    return main, name_line if title_line else ''


_CHANNELS_DISPLAY = {8: '7.1', 7: '7.0', 6: '5.1', 3: '2.1', 2: '2.0', 1: '1.0'}


def _stream_details_label(sd, name_line=''):
    """Build a formatted label2 string matching TMDbHelper style (pipe-separated)."""
    parts = []
    if name_line:
        parts.append(name_line)
    if 'width' in sd:
        parts.append('{}x{}'.format(sd['width'], sd['height']))
    if sd.get('hdr'):
        parts.append(' '.join(sd['hdr']))
    if sd.get('remux'):
        parts.append('Remux')
    if sd.get('vcodec'):
        parts.append(sd['vcodec'].upper())
    if sd.get('acodec'):
        parts.append(sd['acodec'].upper())
    if sd.get('channels'):
        parts.append('{} CH'.format(sd['channels']))
    if sd.get('languages'):
        parts.extend(lang.upper() for lang in sd['languages'])
    if sd.get('size'):
        sz = sd['size']
        if sz >= 1024 ** 4:
            parts.append('{:.1f} TB'.format(sz / 1024 ** 4))
        elif sz >= 1024 ** 3:
            parts.append('{:.1f} GB'.format(sz / 1024 ** 3))
        else:
            parts.append('{:.0f} MB'.format(sz / 1024 ** 2))
    return ' | '.join(parts)


# Resolution label → (width, height)
_RESOLUTION_MAP = {
    '8k': (7680, 4320), '2160p': (3840, 2160), '4k': (3840, 2160),
    '1080p': (1920, 1080), '720p': (1280, 720), '480p': (720, 480),
}
# Normalise codec names for display
_VIDEO_CODEC_NORM = {
    'hevc': 'HEVC', 'h265': 'HEVC', 'h.265': 'HEVC', 'x265': 'HEVC',
    'avc': 'H.264', 'h264': 'H.264', 'h.264': 'H.264', 'x264': 'H.264',
    'av1': 'AV1', 'vp9': 'VP9', 'xvid': 'XviD',
}
_AUDIO_CODEC_NORM = {
    'truehd': 'TrueHD', 'atmos': 'Atmos', 'dts-hd ma': 'DTS-HD MA',
    'dts-hd': 'DTS-HD', 'dts hd ma': 'DTS-HD MA', 'dts hd': 'DTS-HD',
    'dtshd': 'DTS-HD', 'dtshdma': 'DTS-HD MA', 'dts': 'DTS',
    'eac3': 'EAC3', 'e-ac-3': 'EAC3', 'ac3': 'AC3',
    'ddp': 'EAC3', 'dd+': 'EAC3', 'dd': 'AC3',
    'aac': 'AAC', 'flac': 'FLAC', 'opus': 'Opus', 'mp3': 'MP3', 'pcm': 'PCM',
}


def _parse_stream_details(stream):
    """Extract video/audio/size details from stream name+title for TMDbHelper."""
    text = '{}\n{}'.format(stream.get('name', ''), stream.get('title', ''))

    details = {}

    # --- Resolution ---
    q_m = _RE_QUALITY.search(text)
    if q_m:
        q = q_m.group(1).lower()
        if q in ('4k',):
            q = '2160p'
        elif q in ('8k',):
            q = '8k'
        details['quality'] = '8K' if q == '8k' else ('4K' if q == '2160p' else q)
        res = _RESOLUTION_MAP.get(q)
        if res:
            details['width'], details['height'] = res

    # --- HDR tags (DV, HDR10+, HDR10, HDR, SDR) ---
    hdr_tags = []
    for hdr_m in _RE_HDR.finditer(text):
        # Groups: 1=DV/Dolby Vision, 2=HDR10+, 3=HDR10, 4=HDR, 5=SDR
        if hdr_m.group(1):
            tag = 'DV'
        elif hdr_m.group(2):
            tag = 'HDR10+'
        elif hdr_m.group(3):
            tag = 'HDR10'
        elif hdr_m.group(4):
            tag = 'HDR'
        else:
            tag = 'SDR'
        if tag not in hdr_tags:
            hdr_tags.append(tag)
    # --- IMAX ---
    if _RE_IMAX.search(text):
        if 'IMAX' not in hdr_tags:
            hdr_tags.append('IMAX')
    if hdr_tags:
        details['hdr'] = hdr_tags

    # --- Infer 2160p when DV or IMAX present but no explicit resolution ---
    if 'width' not in details and hdr_tags:
        has_premium = any(t in hdr_tags for t in ('DV', 'IMAX'))
        if has_premium:
            details['quality'] = '4K'
            details['width'], details['height'] = 3840, 2160

    # --- Remux ---
    if _RE_REMUX.search(text):
        details['remux'] = True

    # --- Video codec ---
    vc_m = _RE_VIDEO_CODEC.search(text)
    if vc_m:
        details['vcodec'] = _VIDEO_CODEC_NORM.get(
            vc_m.group(1).lower().replace('.', '').replace('-', ''),
            vc_m.group(1).upper())

    # --- Audio codec ---
    ac_m = _RE_AUDIO_CODEC.search(text)
    if ac_m:
        raw = ac_m.group(1).lower().replace(' ', '').replace('-', '')
        details['acodec'] = _AUDIO_CODEC_NORM.get(raw, ac_m.group(1).upper())

    # --- Audio channels ---
    ch_m = _RE_AUDIO_CHANNELS.search(text)
    if ch_m:
        details['channels'] = int(ch_m.group(1)) + int(ch_m.group(2))

    # --- Languages from flags ---
    langs = []
    for flag_m in _RE_LANG_FLAG.finditer(text):
        lang = _FLAG_TO_LANG.get(flag_m.group())
        if lang and lang not in langs:
            langs.append(lang)
    # Also check text-based language keywords
    for lang_code, pattern in _LANG_KEYWORDS.items():
        if pattern.search(text) and lang_code not in langs:
            langs.append(lang_code)
    if langs:
        details['languages'] = langs

    # --- File size in bytes ---
    size_m = _RE_SIZE.search(text)
    if size_m:
        size_val = float(size_m.group(1))
        unit = size_m.group(2).upper()
        if unit == 'TB':
            details['size'] = int(size_val * 1024 * 1024 * 1024 * 1024)
        elif unit == 'GB':
            details['size'] = int(size_val * 1024 * 1024 * 1024)
        elif unit == 'MB':
            details['size'] = int(size_val * 1024 * 1024)

    return details


def _stream_to_url(stream):
    """Convert a Stremio stream object to a playable URL string.
    Returns None for unsupported/external streams."""
    if stream.get('url'):
        return stream['url']

    if stream.get('infoHash'):
        magnet = 'magnet:?xt=urn:btih:{}'.format(stream['infoHash'])
        if stream.get('name'):
            magnet += '&dn={}'.format(urllib.parse.quote(stream['name']))
        for src in stream.get('sources', []):
            if src.startswith('tracker:'):
                magnet += '&tr={}'.format(urllib.parse.quote(src[8:]))
        try:
            xbmcaddon.Addon('plugin.video.elementum')
            file_idx = stream.get('fileIdx', 0)
            return ('plugin://plugin.video.elementum/play'
                    '?uri={}&file={}'.format(
                        urllib.parse.quote(magnet, safe=''), file_idx))
        except Exception:
            return magnet

    if stream.get('ytId'):
        return ('plugin://plugin.video.youtube'
                '/play/?video_id={}'.format(stream['ytId']))

    return None


def _set_li_metadata(li, meta_info):
    """Apply artwork and video info to a ListItem from meta_info dict."""
    if not meta_info:
        return
    art = {}
    if meta_info.get('poster'):
        art['poster'] = meta_info['poster']
        art['thumb'] = meta_info['poster']
    if meta_info.get('fanart'):
        art['fanart'] = meta_info['fanart']
    if meta_info.get('clearlogo'):
        art['clearlogo'] = meta_info['clearlogo']
    if art:
        li.setArt(art)

    info = {}
    for key in ('title', 'tagline', 'mpaa', 'plot'):
        if meta_info.get(key):
            info[key] = meta_info[key]
    for key in ('year', 'season', 'episode'):
        if meta_info.get(key):
            info[key] = int(meta_info[key])
    if meta_info.get('imdbnumber'):
        info['imdbnumber'] = meta_info['imdbnumber']
    if meta_info.get('mediatype'):
        info['mediatype'] = meta_info['mediatype']
    if meta_info.get('genre'):
        info['genre'] = meta_info['genre']
    if meta_info.get('duration'):
        dur = _parse_duration(meta_info['duration'])
        if dur:
            info['duration'] = dur
    if meta_info.get('rating'):
        info['rating'] = float(meta_info['rating'])
    if info:
        set_video_info(li, info)


# Window property key for caching streams between list_streams → resolve
_STREAMS_CACHE_KEY = 'stremio2kodi_streams_cache'


def _cache_streams(streams):
    """Store stream list in a window property for resolve to pick up."""
    slim = []
    for s in streams:
        slim.append({
            k: s[k] for k in ('url', 'infoHash', 'name', 'title',
                               'sources', 'fileIdx', 'ytId',
                               'externalUrl', '_addon')
            if k in s
        })
    _win_home.setProperty(
        _STREAMS_CACHE_KEY, json.dumps(slim, ensure_ascii=False))


def _get_cached_streams():
    """Retrieve cached streams from window property."""
    raw = _win_home.getProperty(_STREAMS_CACHE_KEY)
    if raw:
        return json.loads(raw)
    return []


def list_streams(stream_type, stream_id):
    """Search addons for streams and return them as a Kodi directory listing.

    Used by TMDbHelper's dialog step — returns items for TMDbHelper to
    present in its own selection dialog.
    """
    all_streams = _search_streams(stream_type, stream_id)
    if not all_streams:
        xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        return

    all_streams.sort(key=_stream_sort_key)
    _cache_streams(all_streams)

    for idx, stream in enumerate(all_streams):
        url = build_url('resolve', idx=str(idx))
        li = _build_stream_listitem(stream)
        li.setProperty('IsPlayable', 'true')
        xbmcplugin.addDirectoryItem(HANDLE, url, li, isFolder=False)

    xbmcplugin.endOfDirectory(HANDLE)


def resolve_stream(idx):
    """Resolve a cached stream by index and hand it to Kodi via setResolvedUrl."""
    streams = _get_cached_streams()
    if idx < 0 or idx >= len(streams):
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
        return

    stream = streams[idx]

    # Handle external URLs (can't use setResolvedUrl)
    if stream.get('externalUrl'):
        xbmc.executebuiltin(
            'RunPlugin({})'.format(stream['externalUrl']))
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
        return

    url = _stream_to_url(stream)
    if not url:
        xbmcplugin.setResolvedUrl(HANDLE, False, xbmcgui.ListItem())
        return

    li = xbmcgui.ListItem(path=url)
    xbmcplugin.setResolvedUrl(HANDLE, True, li)


def _search_streams(stream_type, stream_id, addon_idx=None):
    """Run the parallel manifest check + stream search, return stream list.

    Shared by both the standalone play path and the TMDbHelper list path.
    """
    addons = addon_mgr.get_addons()
    if not addons:
        xbmcgui.Dialog().notification(
            ADDON_NAME, L(30010),
            xbmcgui.NOTIFICATION_ERROR)
        return []

    if addon_idx is not None and 0 <= addon_idx < len(addons):
        indices = [addon_idx]
    else:
        indices = list(range(len(addons)))

    timeout = ADDON.getSettingInt('request_timeout') or 15
    workers = min(_MAX_WORKERS, len(indices))

    labels = {}
    for i in indices:
        labels[i] = addons[i].get('name', addons[i]['url'].split('/')[2][:30])

    progress = xbmcgui.DialogProgress()
    progress.create(ADDON_NAME, L(30035))

    # --- Phase 1: parallel manifest check (cached = instant) ----------------
    def _check_manifest(i):
        manifest = _get_manifest(addons[i]['url'])
        if manifest and stremio.has_resource(manifest, 'stream'):
            return i, manifest
        return i, None

    filtered = []
    cancelled = False
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(_check_manifest, i): i for i in indices}
        try:
            for future in as_completed(futures,
                                       timeout=stremio._MANIFEST_TIMEOUT + 3):
                if progress.iscanceled():
                    cancelled = True
                    break
                try:
                    i, manifest = future.result(timeout=0)
                    if manifest:
                        labels[i] = manifest.get('name', labels[i])
                        filtered.append((i, manifest))
                except Exception:
                    pass
        except (FuturesTimeoutError, TimeoutError):
            xbmc.log('Stremio2Kodi: manifest check timed out',
                     xbmc.LOGWARNING)

    if cancelled or not filtered:
        progress.close()
        if not cancelled:
            xbmcgui.Dialog().notification(
                ADDON_NAME, L(30032),
                xbmcgui.NOTIFICATION_WARNING)
        return []

    # --- Phase 2: parallel stream fetch -------------------------------------
    searching_line = _names_summary([labels[i] for i, _ in filtered])
    progress.update(0, '{}\n{}'.format(L(30036), searching_line))

    def _fetch_streams(i, manifest):
        name = manifest.get('name', labels[i])
        logo = manifest.get('logo', '')
        result = stremio.get_streams(addons[i]['url'],
                                     stream_type, stream_id)
        streams = []
        if result and result.get('streams'):
            for s in result['streams']:
                s['_addon'] = name
                s['_logo'] = logo
                streams.append(s)
        return name, streams

    all_streams = []
    done = set()
    name_map = {i: labels[i] for i, _ in filtered}

    with ThreadPoolExecutor(max_workers=min(_MAX_WORKERS, len(filtered))) as pool:
        fmap = {pool.submit(_fetch_streams, i, m): i for i, m in filtered}

        try:
            for future in as_completed(fmap, timeout=timeout + 5):
                if progress.iscanceled():
                    cancelled = True
                    break
                done.add(future)
                try:
                    _, streams = future.result(timeout=0)
                    all_streams.extend(streams)
                except Exception as e:
                    xbmc.log('Stremio2Kodi: stream fetch error: {}'.format(e),
                             xbmc.LOGWARNING)
                pending = [name_map[fmap[f]] for f in fmap if f not in done]
                quality = _quality_summary(all_streams)
                still_searching = len(done) < len(filtered)
                line1 = L(30040).format(
                    len(all_streams),
                    's' if len(all_streams) != 1 else '') if still_searching else L(30041).format(
                    len(all_streams),
                    's' if len(all_streams) != 1 else '')
                parts = []
                if quality:
                    parts.append(quality)
                if pending:
                    parts.append(L(30039).format(_names_summary(pending)))
                line2 = '  |  '.join(parts) if parts else searching_line
                progress.update(int(len(done) / len(filtered) * 100),
                                '{}\n{}'.format(line1, line2))
        except (FuturesTimeoutError, TimeoutError):
            xbmc.log('Stremio2Kodi: stream search timed out, '
                     '{} streams found'.format(len(all_streams)),
                     xbmc.LOGWARNING)

    progress.close()

    if not all_streams and not cancelled:
        xbmcgui.Dialog().notification(
            ADDON_NAME, L(30031),
            xbmcgui.NOTIFICATION_WARNING)

    return all_streams


# ---------------------------------------------------------------------------
#  Add-on management
# ---------------------------------------------------------------------------

def manage_menu():
    """UI to add / remove Stremio add-ons."""
    li = xbmcgui.ListItem(L(30050))
    li.setArt({'icon': 'DefaultAddSource.png'})
    xbmcplugin.addDirectoryItem(
        HANDLE, build_url('add_addon'), li, isFolder=False)

    addons = addon_mgr.get_addons()
    for idx, addon_info in enumerate(addons):
        manifest = _get_manifest(addon_info['url'])
        if manifest:
            name = manifest.get('name', addon_info.get('name'))
            desc = manifest.get('description', '')
            logo = manifest.get('logo', '')
        else:
            name = addon_info.get('name', addon_info['url'])
            desc = 'Could not fetch manifest'
            logo = ''

        li = xbmcgui.ListItem(name)
        art = {
            'icon': logo or _FALLBACK_ICON,
            'thumb': logo or _FALLBACK_ICON,
        }
        li.setArt(art)
        if desc:
            set_video_info(li, {'plot': desc})

        ctx = [(L(30061),
                'RunPlugin({})'.format(
                    build_url('remove_addon', idx=str(idx))))]
        li.addContextMenuItems(ctx)

        xbmcplugin.addDirectoryItem(
            HANDLE,
            build_url('addon_info', idx=str(idx)),
            li, isFolder=False)

    xbmcplugin.endOfDirectory(HANDLE)


def add_addon():
    """Prompt the user for a Stremio add-on URL and validate it."""
    dialog = xbmcgui.Dialog()
    url = dialog.input(
        L(30051),
        type=xbmcgui.INPUT_ALPHANUM)
    if not url:
        return

    progress = xbmcgui.DialogProgress()
    progress.create(ADDON_NAME, L(30052))
    manifest = _get_manifest(url)
    progress.close()

    if not manifest:
        dialog.notification(
            ADDON_NAME,
            L(30053),
            xbmcgui.NOTIFICATION_ERROR)
        return

    name = manifest.get('name', url)
    types = ', '.join(manifest.get('types', []))
    resources = []
    for r in manifest.get('resources', []):
        resources.append(r if isinstance(r, str) else r.get('name', ''))

    if not dialog.yesno(
        ADDON_NAME,
        L(30054) + '\n\n'
        'Name: {}\nTypes: {}\nResources: {}'.format(
            name, types, ', '.join(resources))):
        return

    if addon_mgr.add_addon(url, name):
        dialog.notification(
            ADDON_NAME, L(30055).format(name),
            xbmcgui.NOTIFICATION_INFO)
        xbmc.executebuiltin('Container.Refresh')
    else:
        dialog.notification(
            ADDON_NAME, L(30056),
            xbmcgui.NOTIFICATION_WARNING)


def remove_addon(idx):
    addons = addon_mgr.get_addons()
    if idx >= len(addons):
        return
    name = addons[idx].get('name', addons[idx]['url'])
    if xbmcgui.Dialog().yesno(ADDON_NAME,
                               L(30057).format(name)):
        addon_mgr.remove_addon(idx)
        xbmcgui.Dialog().notification(
            ADDON_NAME, L(30058).format(name),
            xbmcgui.NOTIFICATION_INFO)
        xbmc.executebuiltin('Container.Refresh')


def addon_info_dialog(idx):
    """Show a dialog with info and actions for a configured Stremio add-on."""
    addons = addon_mgr.get_addons()
    if idx >= len(addons):
        return
    addon_info = addons[idx]
    manifest = _get_manifest(addon_info['url'])

    if manifest:
        name = manifest.get('name', addon_info.get('name', ''))
        desc = manifest.get('description', 'No description')
        types = ', '.join(manifest.get('types', []))
        resources = []
        for r in manifest.get('resources', []):
            resources.append(r if isinstance(r, str) else r.get('name', ''))
        catalogs = len(manifest.get('catalogs', []))
        version = manifest.get('version', '?')
        info_text = (
            'Name: {}\nVersion: {}\n'
            'Types: {}\nResources: {}\n'
            'Catalogs: {}\n\n{}'
        ).format(name, version, types, ', '.join(resources), catalogs, desc)
    else:
        name = addon_info.get('name', addon_info['url'])
        info_text = 'URL: {}\n\nCould not fetch manifest.'.format(
            addon_info['url'])

    dialog = xbmcgui.Dialog()
    choice = dialog.contextmenu([
        L(30059),
        L(30060),
    ])
    if choice == 0:
        dialog.textviewer('{} - {}'.format(ADDON_NAME, name), info_text)
    elif choice == 1:
        remove_addon(idx)


# ---------------------------------------------------------------------------
#  Router
# ---------------------------------------------------------------------------

def route():
    query = sys.argv[2].lstrip('?') if len(sys.argv) > 2 else ''
    params = dict(urllib.parse.parse_qsl(query))
    action = params.get('action', '')

    xbmc.log('Stremio2Kodi: action={} params={}'.format(action, params),
             xbmc.LOGINFO)

    try:
        _dispatch(action, params)
    except Exception:
        xbmc.log('Stremio2Kodi: unhandled error: {}'.format(
            traceback.format_exc()), xbmc.LOGERROR)
        try:
            xbmcplugin.endOfDirectory(HANDLE, succeeded=False)
        except Exception:
            pass


def _dispatch(action, params):
    if not action:
        main_menu()
    elif action == 'catalogs':
        catalogs_menu()
    elif action == 'addon_catalogs':
        addon_catalogs(int(params['idx']))
    elif action == 'catalog_filters':
        catalog_filters(int(params['idx']),
                        params['type'], params['id'])
    elif action == 'catalog_filter_values':
        catalog_filter_values(int(params['idx']),
                              params['type'], params['id'],
                              params['extra_name'])
    elif action == 'catalog':
        catalog_browse(int(params['idx']),
                       params['type'], params['id'],
                       skip=params.get('skip'),
                       extra_name=params.get('extra_name'),
                       extra_value=params.get('extra_value'))
    elif action == 'seasons':
        show_seasons(int(params.get('idx', 0)),
                     params['type'], params['id'])
    elif action == 'episodes':
        show_episodes(params['type'], params['id'], params['season'])
    elif action == 'play_movie':
        meta_info = {k: params[k] for k in ('title', 'year', 'poster', 'fanart')
                     if k in params}
        imdb_id = params['imdb_id']
        if imdb_id.startswith('tt'):
            meta_info['imdbnumber'] = imdb_id
        meta_info['mediatype'] = 'movie'
        play_movie(imdb_id, params.get('stype', 'movie'),
                   addon_idx=int(params['aidx']) if 'aidx' in params else None,
                   meta_info=meta_info or None)
    elif action == 'play_episode':
        meta_info = {k: params[k] for k in ('title', 'season', 'episode')
                     if k in params}
        imdb_id = params['imdb_id']
        if imdb_id.startswith('tt'):
            meta_info['imdbnumber'] = imdb_id
        meta_info['mediatype'] = 'episode'
        play_episode(imdb_id, params['season'], params['episode'],
                     meta_info=meta_info or None)
    elif action == 'list_streams':
        # TMDbHelper dialog-step path
        stream_type = params.get('type', 'movie')
        imdb_id = params['imdb_id']
        if 'season' in params and 'episode' in params:
            stream_id = '{}:{}:{}'.format(
                imdb_id, params['season'], params['episode'])
        else:
            stream_id = imdb_id
        list_streams(stream_type, stream_id)
    elif action == 'resolve':
        resolve_stream(int(params['idx']))
    elif action == 'manage':
        manage_menu()
    elif action == 'add_addon':
        add_addon()
    elif action == 'remove_addon':
        remove_addon(int(params['idx']))
    elif action == 'install_player':
        install_player_file()
    elif action == 'addon_info':
        addon_info_dialog(int(params['idx']))


if __name__ == '__main__':
    route()
