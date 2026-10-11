"""Stremio authentication client.

Covers the link.strem.io device-login flow (``create`` / ``read``), the
api.strem.io token exchange (``loginWithToken``), the add-on collection fetch
(``addonCollectionGet``) and QR image download. Kept separate from
``stremio.py``, which implements the Stremio Add-on Protocol.
"""
import json
import urllib.parse
import urllib.request

import xbmc

from stremio import BROWSER_HEADERS, decode_body, open_json

_LINK_API = 'https://link.stremio.com/api/v2'
_LOGIN_API = 'https://api.strem.io/api/loginWithToken'
_COLLECTION_API = 'https://api.strem.io/api/addonCollectionGet'
_TIMEOUT = 10

#: PNG file signature, used to reject non-image QR downloads.
_PNG_MAGIC = b'\x89PNG\r\n\x1a\n'


def create_link(timeout=_TIMEOUT):
    """Request a new device-login code. Returns the 'result' dict or None."""
    url = '{}/create?{}'.format(
        _LINK_API, urllib.parse.urlencode({'type': 'Create'}))
    try:
        data = open_json(url, timeout=timeout)
    except Exception as e:
        xbmc.log('Stremio2Kodi: auth create failed: {}'.format(e),
                 xbmc.LOGWARNING)
        return None
    return (data or {}).get('result')


def read_link(code, timeout=_TIMEOUT):
    """Poll a device-login code. Returns the 'result' dict or None."""
    url = '{}/read?{}'.format(
        _LINK_API,
        urllib.parse.urlencode({'type': 'Read', 'code': code}))
    try:
        data = open_json(url, timeout=timeout)
    except Exception as e:
        xbmc.log('Stremio2Kodi: auth read failed: {}'.format(e),
                 xbmc.LOGWARNING)
        return None
    return (data or {}).get('result')


def login_with_token(token, timeout=_TIMEOUT):
    """Exchange a link authKey for a long-lived account authKey.

    Returns the 'result' dict (containing ``authKey`` and ``user``) or None.
    """
    try:
        data = _post_json(
            _LOGIN_API, {'token': token, 'type': 'LoginWithToken'},
            timeout=timeout)
    except Exception as e:
        xbmc.log('Stremio2Kodi: loginWithToken failed: {}'.format(e),
                 xbmc.LOGWARNING)
        return None
    return (data or {}).get('result')


def download_qr(url, dest_path, timeout=_TIMEOUT):
    """Download the QR PNG at ``url`` to ``dest_path``. True on success.

    The body is decompressed (the CDN may gzip even images) and checked
    against the PNG signature: Kodi renders nothing for a corrupt file, so a
    bad download is rejected instead of silently written.
    """
    req = urllib.request.Request(url, headers=BROWSER_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as response:
        body = decode_body(response)
    if not body.startswith(_PNG_MAGIC):
        return False
    with open(dest_path, 'wb') as handle:
        handle.write(body)
    return True


def fetch_addon_collection(auth_key, update=True, timeout=_TIMEOUT):
    """Fetch the add-on collection of the logged-in Stremio account.

    Returns ``(addons, last_modified)`` where ``addons`` is the list of
    ``{transportUrl, transportName, manifest, flags}`` dicts, or
    ``(None, None)`` when the request fails or the payload is malformed.
    """
    try:
        data = _post_json(
            _COLLECTION_API,
            {'type': 'AddonCollectionGet', 'authKey': auth_key,
             'update': bool(update)},
            timeout=timeout)
    except Exception as e:
        xbmc.log('Stremio2Kodi: addonCollectionGet failed: {}'.format(e),
                 xbmc.LOGWARNING)
        return None, None
    if not isinstance(data, dict):
        xbmc.log('Stremio2Kodi: addonCollectionGet: unexpected payload',
                 xbmc.LOGWARNING)
        return None, None
    if 'error' in data:
        xbmc.log('Stremio2Kodi: addonCollectionGet error: {}'.format(
            data.get('error')), xbmc.LOGWARNING)
        return None, None
    result = data.get('result') or {}
    addons = result.get('addons')
    if not isinstance(addons, list):
        xbmc.log('Stremio2Kodi: addonCollectionGet: no addons list',
                 xbmc.LOGWARNING)
        return None, None
    return addons, result.get('lastModified')


def _post_json(url, payload, timeout):
    """POST a JSON payload and return the parsed JSON response."""
    headers = dict(BROWSER_HEADERS)
    headers['Content-Type'] = 'application/json'
    data = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(
        url, data=data, headers=headers, method='POST')
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.loads(decode_body(response).decode('utf-8'))
