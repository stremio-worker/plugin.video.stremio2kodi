"""Stremio2Kodi background service.

Declared in addon.xml as ``<extension point="xbmc.service"
library="service.py" start="startup"/>``. Kodi runs this module at startup and
expects it to keep running until playback/abort is requested.
"""
import xbmc


class Stremio2KodiService:
    """Placeholder service: idles until Kodi requests abort.

    Add startup work (e.g. warm caches, register players) in ``run``.
    """

    def __init__(self):
        self._monitor = xbmc.Monitor()

    def run(self):
        while not self._monitor.abortRequested():
            if self._monitor.waitForAbort(1):
                break


if __name__ == '__main__':
    Stremio2KodiService().run()
