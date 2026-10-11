import gzip
import json
import urllib.error
import urllib.parse
import urllib.request
import zlib

import xbmc

# Realistic desktop Google Chrome (Windows) request headers so add-on servers
# see the requests as coming from a normal browser instead of a bare client.
# Accept-Encoding is intentionally limited to gzip/deflate: brotli (br) and
# zstd are not guaranteed to be available in Kodi's bundled Python, so we only
# advertise what decode_body() can transparently decompress.
CHROME_USER_AGENT = (
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
    '(KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36'
)

BROWSER_HEADERS = {
    'User-Agent': CHROME_USER_AGENT,
    'Accept': 'application/json, text/plain, */*',
    'Accept-Language': 'en-US,en;q=0.9',
    'Accept-Encoding': 'gzip, deflate',
    'sec-ch-ua': '"Chromium";v="156", "Not_A Brand";v="24"',
    'sec-ch-ua-mobile': '?0',
    'sec-ch-ua-platform': '"Windows"',
    'Sec-Fetch-Dest': 'empty',
    'Sec-Fetch-Mode': 'cors',
    'Sec-Fetch-Site': 'cross-site',
}


def decode_body(response):
    """Return the raw response body, decompressing gzip/deflate when needed."""
    body = response.read()
    encoding = (response.headers.get('Content-Encoding') or '').lower()
    if encoding == 'gzip':
        return gzip.decompress(body)
    if encoding == 'deflate':
        try:
            return zlib.decompress(body)
        except zlib.error:
            return zlib.decompress(body, -zlib.MAX_WBITS)
    return body


def open_json(url, timeout=15):
    """GET a URL with browser-like headers and return the parsed JSON body."""
    req = urllib.request.Request(url, headers=BROWSER_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(decode_body(response).decode('utf-8'))


class StremioClient:
    """Client for the Stremio Add-on Protocol."""

    def __init__(self, timeout=15):
        self.timeout = timeout

    @staticmethod
    def normalize_url(url):
        """Normalize a Stremio add-on URL to its base URL."""
        url = url.strip()
        if url.startswith('stremio://'):
            url = 'https://' + url[len('stremio://'):]
        url = url.rstrip('/')
        if url.endswith('/manifest.json'):
            url = url[:-len('/manifest.json')]
        return url

    def _request(self, url, timeout=None):
        """Make an HTTP GET request and return parsed JSON."""
        if xbmc.Monitor().abortRequested():
            return None
        try:
            return open_json(url, timeout=timeout or self.timeout)
        except urllib.error.HTTPError as e:
            xbmc.log(
                'Stremio2Kodi: HTTP {} for {}'.format(e.code, url),
                xbmc.LOGERROR
            )
        except urllib.error.URLError as e:
            xbmc.log(
                'Stremio2Kodi: URL error for {}: {}'.format(url, e.reason),
                xbmc.LOGERROR
            )
        except Exception as e:
            xbmc.log(
                'Stremio2Kodi: Request failed for {}: {}'.format(url, e),
                xbmc.LOGERROR
            )
        return None

    # Manifests are tiny; use a short default timeout
    _MANIFEST_TIMEOUT = 5

    def get_manifest(self, base_url, timeout=None):
        """Fetch the manifest.json of a Stremio add-on."""
        base_url = self.normalize_url(base_url)
        return self._request('{}/manifest.json'.format(base_url),
                             timeout=timeout or self._MANIFEST_TIMEOUT)

    def get_catalog(self, base_url, type_, catalog_id, extra=None):
        """Fetch a catalog listing from a Stremio add-on.

        Args:
            base_url: The add-on base URL.
            type_: Content type (movie, series, etc.).
            catalog_id: The catalog ID from the manifest.
            extra: Optional extra parameters as a URL path segment
                   (e.g. 'skip=100' or 'genre=Action&skip=100').
        """
        base_url = self.normalize_url(base_url)
        cat_id_enc = urllib.parse.quote(catalog_id, safe='')
        type_enc = urllib.parse.quote(type_, safe='')
        if extra:
            url = '{}/catalog/{}/{}/{}.json'.format(
                base_url, type_enc, cat_id_enc,
                urllib.parse.quote(extra, safe='=&')
            )
        else:
            url = '{}/catalog/{}/{}.json'.format(
                base_url, type_enc, cat_id_enc
            )
        return self._request(url)

    def get_streams(self, base_url, type_, id_):
        """Fetch available streams for an item.

        Args:
            base_url: The add-on base URL.
            type_: Content type ('movie' or 'series').
            id_: The content ID. For movies: IMDB ID (e.g. 'tt1234567').
                 For episodes: 'imdb_id:season:episode' (e.g. 'tt1234567:1:1').
        """
        base_url = self.normalize_url(base_url)
        return self._request('{}/stream/{}/{}.json'.format(
            base_url,
            urllib.parse.quote(type_, safe=''),
            urllib.parse.quote(id_, safe=':'),
        ))

    def get_meta(self, base_url, type_, id_):
        """Fetch metadata for an item."""
        base_url = self.normalize_url(base_url)
        return self._request('{}/meta/{}/{}.json'.format(
            base_url,
            urllib.parse.quote(type_, safe=''),
            urllib.parse.quote(id_, safe=':'),
        ))

    def has_resource(self, manifest, resource_name):
        """Check if a manifest declares support for a resource."""
        for r in manifest.get('resources', []):
            if isinstance(r, str) and r == resource_name:
                return True
            if isinstance(r, dict) and r.get('name') == resource_name:
                return True
        return False
