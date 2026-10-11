"""Persist the Stremio account in hidden addon settings.

Only the account ``authKey``, ``email`` and the login timestamp are stored; the
password is never kept. The backing settings (``auth_key``, ``account_email``,
``login_time``) are declared in ``resources/settings.xml`` as Internal (never
shown to the user).
"""
import time

import xbmcaddon

_AUTH_KEY = 'auth_key'
_EMAIL = 'account_email'
_LOGIN_TIME = 'login_time'
_SYNC_TOTAL = 'sync_total'
_SYNC_OK = 'sync_ok'
_SYNC_TIME = 'sync_time'


def get_account():
    """Return {'auth_key': str, 'email': str, 'login_time': int}.

    ``login_time`` is a Unix timestamp (seconds) of the last successful login,
    or ``0`` when unset/not logged in.
    """
    addon = xbmcaddon.Addon()
    try:
        login_time = int(addon.getSetting(_LOGIN_TIME) or 0)
    except ValueError:
        login_time = 0
    return {
        'auth_key': addon.getSetting(_AUTH_KEY) or '',
        'email': addon.getSetting(_EMAIL) or '',
        'login_time': login_time,
    }


def save_account(auth_key, email, login_time=None):
    """Store the Stremio account authKey, email and login timestamp.

    ``login_time`` is a Unix timestamp in seconds; defaults to now.
    """
    addon = xbmcaddon.Addon()
    addon.setSetting(_AUTH_KEY, auth_key or '')
    addon.setSetting(_EMAIL, email or '')
    stamp = int(time.time()) if login_time is None else int(login_time)
    addon.setSetting(_LOGIN_TIME, str(stamp))


def clear_account():
    """Remove the stored account (log out)."""
    addon = xbmcaddon.Addon()
    addon.setSetting(_AUTH_KEY, '')
    addon.setSetting(_EMAIL, '')
    addon.setSetting(_LOGIN_TIME, '')


def save_sync_record(total, ok, sync_time=None):
    """Store the last addon-sync result (``ok`` of ``total`` addons)."""
    addon = xbmcaddon.Addon()
    stamp = int(time.time()) if sync_time is None else int(sync_time)
    addon.setSetting(_SYNC_TOTAL, str(int(total)))
    addon.setSetting(_SYNC_OK, str(int(ok)))
    addon.setSetting(_SYNC_TIME, str(stamp))


def get_sync_record():
    """Return {'total': int, 'ok': int, 'sync_time': int}; 0 when unset."""
    addon = xbmcaddon.Addon()

    def _int(key):
        try:
            return int(addon.getSetting(key) or 0)
        except ValueError:
            return 0

    return {
        'total': _int(_SYNC_TOTAL),
        'ok': _int(_SYNC_OK),
        'sync_time': _int(_SYNC_TIME),
    }


def is_logged_in():
    """Return True when an account authKey is stored."""
    return bool(xbmcaddon.Addon().getSetting(_AUTH_KEY))
