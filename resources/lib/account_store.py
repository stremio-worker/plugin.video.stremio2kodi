"""Persist the Stremio account in hidden addon settings.

Only the account ``authKey`` and ``email`` are stored; the password is never
kept. The backing settings (``auth_key``, ``account_email``) are declared in
``resources/settings.xml`` as Internal (never shown to the user).
"""
import xbmcaddon

_AUTH_KEY = 'auth_key'
_EMAIL = 'account_email'


def get_account():
    """Return {'auth_key': str, 'email': str}; values are '' when unset."""
    addon = xbmcaddon.Addon()
    return {
        'auth_key': addon.getSetting(_AUTH_KEY) or '',
        'email': addon.getSetting(_EMAIL) or '',
    }


def save_account(auth_key, email):
    """Store the Stremio account authKey and email."""
    addon = xbmcaddon.Addon()
    addon.setSetting(_AUTH_KEY, auth_key or '')
    addon.setSetting(_EMAIL, email or '')


def clear_account():
    """Remove the stored account (log out)."""
    addon = xbmcaddon.Addon()
    addon.setSetting(_AUTH_KEY, '')
    addon.setSetting(_EMAIL, '')


def is_logged_in():
    """Return True when an account authKey is stored."""
    return bool(xbmcaddon.Addon().getSetting(_AUTH_KEY))
