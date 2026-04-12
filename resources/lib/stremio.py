import json
import urllib.parse
import urllib.request
import urllib.error
import xbmc


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
            req = urllib.request.Request(url)
            req.add_header('User-Agent', 'Stremio2Kodi/1.0')
            req.add_header('Accept', 'application/json')
            with urllib.request.urlopen(req, timeout=timeout or self.timeout) as response:
                data = response.read().decode('utf-8')
                return json.loads(data)
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
