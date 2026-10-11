"""Stremio2Kodi background service.

Declared in addon.xml as ``<extension point="xbmc.service"
library="service.py" start="startup"/>``. Kodi runs this module at startup and
expects it to keep running until playback/abort is requested.

Periodically checks the last addon sync date and, when more than
``SYNC_MAX_AGE_DAYS`` days have passed (or no sync has ever run while the user
is logged in), triggers a silent addon sync via ``RunPlugin``.
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

#: How old a sync may be before an automatic refresh is triggered.
SYNC_MAX_AGE_DAYS = 3
#: How often the service checks for an overdue sync (seconds).
_CHECK_INTERVAL_SEC = 3600
#: Plugin call that runs the sync without a progress dialog.
_PLUGIN = ('plugin://plugin.video.stremio2kodi/'
           '?action=addons_sync&silent=1')


class Stremio2KodiService:
    """Background service: auto-refresh the Stremio addon collection."""

    def __init__(self):
        self._monitor = xbmc.Monitor()

    @staticmethod
    def _sync_is_due():
        """Return True when logged in and the sync is overdue."""
        if not get_account().get('auth_key'):
            return False
        last = get_sync_record().get('sync_time') or 0
        if not last:
            return True  # never synced
        return time.time() - last >= SYNC_MAX_AGE_DAYS * 86400

    def run(self):
        while not self._monitor.abortRequested():
            try:
                if self._sync_is_due():
                    last = get_sync_record().get('sync_time') or 0
                    xbmc.log(
                        'Stremio2Kodi: service: addon sync due (last={}), '
                        'triggering silent sync'.format(last), xbmc.LOGINFO)
                    xbmc.executebuiltin('RunPlugin({})'.format(_PLUGIN))
            except Exception as e:
                xbmc.log('Stremio2Kodi: service: sync check error: {}'.format(
                    e), xbmc.LOGERROR)
            if self._monitor.waitForAbort(_CHECK_INTERVAL_SEC):
                break


if __name__ == '__main__':
    Stremio2KodiService().run()