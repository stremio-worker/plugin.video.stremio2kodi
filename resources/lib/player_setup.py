"""TMDbHelper player file installation.

The plugin ships a player definition (``resources/player/stremio2kodi.json``)
that lets TMDbHelper route playback through this add-on. It must live inside
TMDbHelper's own profile at ``addon_data/plugin.video.themoviedb.helper/players``.

``ensure_player_file`` is the automatic path used by the background service: it
does nothing unless TMDbHelper is installed and the shipped definition differs
from the installed one, and it notifies only when the file is actually written.
``install_player_file`` is the manual menu action and always (re)installs.
"""
import os
import shutil

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

#: TMDbHelper add-on id that owns the players directory.
_TMDBHELPER = 'plugin.video.themoviedb.helper'
#: Localized strings for the success/failure notifications.
_STR_INSTALLED = 30070
_STR_FAILED = 30071


def _paths():
    """Return ``(source, players_dir, dest)`` for the player definition."""
    addon = xbmcaddon.Addon()
    addon_path = xbmcvfs.translatePath(addon.getAddonInfo('path'))
    source = os.path.join(
        addon_path, 'resources', 'player', 'stremio2kodi.json')
    players_dir = xbmcvfs.translatePath(
        'special://profile/addon_data/'
        'plugin.video.themoviedb.helper/players/')
    dest = os.path.join(players_dir, 'stremio2kodi.json')
    return source, players_dir, dest


def tmdbhelper_present():
    """Return True when TMDbHelper is installed."""
    return xbmc.getCondVisibility('System.HasAddon({})'.format(_TMDBHELPER))


def _files_differ(source, dest):
    """Return True when the destination is missing or has different content."""
    try:
        with open(source, 'rb') as source_fh:
            source_data = source_fh.read()
        with open(dest, 'rb') as dest_fh:
            dest_data = dest_fh.read()
        return source_data != dest_data
    except OSError:
        return True


def _copy(source, players_dir, dest):
    """Copy the player definition, creating its directory if needed."""
    if not os.path.exists(players_dir):
        os.makedirs(players_dir)
    shutil.copy2(source, dest)


def _notify(message_id, icon):
    addon = xbmcaddon.Addon()
    xbmcgui.Dialog().notification(
        addon.getAddonInfo('name'),
        addon.getLocalizedString(message_id),
        icon)


def ensure_player_file():
    """Install or refresh the player when TMDbHelper is present.

    Returns one of ``'absent'`` (TMDbHelper not installed), ``'up-to-date'``,
    ``'installed'`` or ``'error'``. A notification is shown only when the file
    is actually (re)written.
    """
    if not tmdbhelper_present():
        return 'absent'
    source, players_dir, dest = _paths()
    if not _files_differ(source, dest):
        return 'up-to-date'
    try:
        _copy(source, players_dir, dest)
    except Exception as e:
        xbmc.log('Stremio2Kodi: ensure_player_file failed: {}'.format(e),
                 xbmc.LOGERROR)
        return 'error'
    _notify(_STR_INSTALLED, xbmcgui.NOTIFICATION_INFO)
    return 'installed'


def install_player_file():
    """Manual menu action: (re)install the player definition."""
    source, players_dir, dest = _paths()
    try:
        _copy(source, players_dir, dest)
    except Exception as e:
        xbmc.log(
            'Stremio2Kodi: Failed to install player: {}'.format(e),
            xbmc.LOGERROR
        )
        _notify(_STR_FAILED, xbmcgui.NOTIFICATION_ERROR)
        return
    _notify(_STR_INSTALLED, xbmcgui.NOTIFICATION_INFO)
