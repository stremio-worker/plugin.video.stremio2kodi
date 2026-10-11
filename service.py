"""Stremio2Kodi background service.

Declared in addon.xml as ``<extension point="xbmc.service"
library="service.py" start="startup"/>``. Kodi runs this module at startup and
expects it to keep running until playback/abort is requested.

Two periodic duties:

* Keep the TMDbHelper player definition installed. Kodi exposes no "another
  add-on was installed" hook, so this is polled; the service also starts right
  after this add-on is installed or updated, which covers the "TMDbHelper is
  already present" case immediately.
* Trigger a silent add-on collection sync when the last one is older than
  ``SYNC_MAX_AGE_DAYS`` days (or never ran while the user is logged in).
"""
import os
import sys
import time

import xbmc
import xbmcaddon
import xbmcvfs

ADDON_PATH = xbmcvfs.translatePath(xbmcaddon.Addon().getAddonInfo('path'))
sys.path.insert(0, os.path.join(ADDON_PATH, 'resources', 'lib'))

from account_store import get_account, get_sync_record  # noqa: E402
from player_setup import ensure_player_file  # noqa: E402

#: How old a sync may be before an automatic refresh is triggered.
SYNC_MAX_AGE_DAYS = 3
#: Minimum delay between automatic sync attempts (seconds).
_SYNC_INTERVAL_SEC = 3600
#: Loop tick: how often the player watcher runs (seconds).
_TICK_SEC = 60
#: Plugin call that runs the sync without a progress dialog.
_PLUGIN = ('plugin://plugin.video.stremio2kodi/'
           '?action=addons_sync&silent=1')


class Stremio2KodiService:
    """Background service: player watcher + auto add-on sync."""

    def __init__(self):
        self._monitor = xbmc.Monitor()
        # Allow the first sync check to run immediately at service start.
        self._last_sync_attempt = time.time() - _SYNC_INTERVAL_SEC

    @staticmethod
    def _sync_is_due():
        """Return True when logged in and the sync is overdue."""
        if not get_account().get('auth_key'):
            return False
        last = get_sync_record().get('sync_time') or 0
        if not last:
            return True  # never synced
        return time.time() - last >= SYNC_MAX_AGE_DAYS * 86400

    def _watch_player(self):
        """Install/refresh the TMDbHelper player when it is available."""
        try:
            status = ensure_player_file()
            if status == 'installed':
                xbmc.log(
                    'Stremio2Kodi: service: TMDbHelper player auto-installed',
                    xbmc.LOGINFO)
        except Exception as e:
            xbmc.log('Stremio2Kodi: service: player check error: {}'.format(e),
                     xbmc.LOGERROR)

    def _maybe_sync(self):
        """Trigger a silent sync at most once per ``_SYNC_INTERVAL_SEC``."""
        now = time.time()
        if now - self._last_sync_attempt < _SYNC_INTERVAL_SEC:
            return
        if not self._sync_is_due():
            return
        self._last_sync_attempt = now
        last = get_sync_record().get('sync_time') or 0
        xbmc.log(
            'Stremio2Kodi: service: addon sync due (last={}), '
            'triggering silent sync'.format(last), xbmc.LOGINFO)
        xbmc.executebuiltin('RunPlugin({})'.format(_PLUGIN))

    def run(self):
        while not self._monitor.abortRequested():
            self._watch_player()
            try:
                self._maybe_sync()
            except Exception as e:
                xbmc.log('Stremio2Kodi: service: sync check error: {}'.format(
                    e), xbmc.LOGERROR)
            if self._monitor.waitForAbort(_TICK_SEC):
                break


if __name__ == '__main__':
    Stremio2KodiService().run()
