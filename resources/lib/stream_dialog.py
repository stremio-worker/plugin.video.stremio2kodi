"""Custom stream picker with real lazy loading.

``xbmcgui.Dialog().select`` only opens once the whole stream search has
finished, so the user stares at a progress bar while every add-on is polled.
This dialog opens immediately and appends streams to the list as each add-on
answers, letting the user pick a source as soon as one is available.

A single daemon worker thread drives the fetch (via a ``producer`` callable)
and updates the list control directly, following the same pattern as
``login_dialog.LoginDialog``. Closing the dialog (Back/Close) or selecting an
item stops the worker. The picked stream is exposed as
``StreamSelectDialog.selected_stream``.

The module is deliberately decoupled from ``main.py`` (no import) to avoid a
circular dependency: callers pass in an ``item_factory`` and a ``sort_key``.
"""
import threading
import traceback

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

_ADDON = xbmcaddon.Addon()

# ACTION_PREVIOUS_MENU / ACTION_NAV_BACK
_BACK_ACTIONS = (10, 92)

# Control ids in script-stremio2kodi-streamselect.xml
_LIST = 100
_TITLE = 2
_STATUS = 3

# Localized string ids (kept in sync with strings.po)
_ID_TITLE = 30030
_ID_NO_STREAMS = 30031
_ID_SEARCHING = 30036
_ID_FOUND_SEARCHING = 30040
_ID_FOUND = 30041


def _L(string_id):
    return _ADDON.getLocalizedString(string_id)


def _plural(count):
    return 's' if count != 1 else ''


class StreamSelectDialog(xbmcgui.WindowXMLDialog):
    """Modal stream picker whose list fills in while add-ons load."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stop = threading.Event()
        self._monitor = xbmc.Monitor()
        self._thread = None
        self._streams = []
        self._item_factory = None
        self._sort_key = None
        self._producer = None
        self._title_id = _ID_TITLE
        self._loaded = False
        self.selected_stream = None

    # --- configuration -----------------------------------------------------

    def setup(self, item_factory, sort_key=None, streams=None, producer=None,
              title_id=_ID_TITLE):
        """Configure the dialog; call before :meth:`doModal`.

        ``item_factory(stream)`` builds the ``ListItem`` for a stream.
        ``sort_key(stream)`` is applied once when loading completes.
        ``streams`` are preloaded results (shown immediately, no fetching).
        ``producer(on_batch, is_cancelled)`` runs in a worker thread and calls
        ``on_batch(streams)`` whenever a batch of streams arrives.
        """
        self._item_factory = item_factory
        self._sort_key = sort_key
        self._producer = producer
        self._title_id = title_id
        if streams:
            self._streams = list(streams)

    # --- lifecycle ---------------------------------------------------------

    def onInit(self):
        self._set_label(_TITLE, _L(self._title_id))
        if self._producer is not None:
            self._set_status(_L(_ID_SEARCHING))
            self._thread = threading.Thread(target=self._worker, daemon=True)
            self._thread.start()
        else:
            self._show_preloaded()

    def onClick(self, control_id):
        if control_id == _LIST:
            self._select_current()

    def onAction(self, action):
        if action.getId() in _BACK_ACTIONS:
            self._request_close()

    # --- preloaded list ----------------------------------------------------

    def _show_preloaded(self):
        if self._sort_key is not None:
            self._streams.sort(key=self._sort_key)
        self._loaded = True
        self._populate(self._streams)
        self._set_status(self._status_text())

    # --- worker ------------------------------------------------------------

    def _worker(self):
        try:
            if self._producer is not None:
                self._producer(self._on_batch, self._is_cancelled)
        except Exception:
            xbmc.log('Stremio2Kodi: stream dialog worker error: {}'.format(
                traceback.format_exc()), xbmc.LOGERROR)
        finally:
            if not self._stop.is_set():
                self._finalize()

    def _is_cancelled(self):
        return self._stop.is_set() or self._monitor.abortRequested()

    def _on_batch(self, streams):
        """Append a freshly fetched batch to the list (worker thread)."""
        if self._stop.is_set() or not streams:
            return
        self._streams.extend(streams)
        try:
            self.getControl(_LIST).addItems(
                [self._build_item(s) for s in streams])
        except Exception:
            pass
        self._set_status(self._status_text())

    def _finalize(self):
        """Sort the complete list once and show the final status."""
        focus = None
        try:
            pos = self.getControl(_LIST).getSelectedPosition()
            if 0 <= pos < len(self._streams):
                focus = self._streams[pos]
        except Exception:
            pass
        if self._sort_key is not None:
            self._streams.sort(key=self._sort_key)
        self._populate(self._streams)
        if focus is not None:
            try:
                self.getControl(_LIST).selectItem(self._streams.index(focus))
            except Exception:
                pass
        self._loaded = True
        self._set_status(self._status_text())
        if not self._streams:
            self._notify_no_streams()
            self._request_close()

    # --- selection / close -------------------------------------------------

    def _select_current(self):
        try:
            pos = self.getControl(_LIST).getSelectedPosition()
        except Exception:
            return
        if 0 <= pos < len(self._streams):
            self.selected_stream = self._streams[pos]
            self._request_close()

    def _request_close(self):
        self._stop.set()
        try:
            self.close()
        except Exception:
            pass

    # --- UI helpers --------------------------------------------------------

    def _build_item(self, stream):
        try:
            return self._item_factory(stream)
        except Exception:
            return xbmcgui.ListItem(
                stream.get('name', '') or 'Unknown Source')

    def _populate(self, streams):
        try:
            ctrl = self.getControl(_LIST)
            ctrl.reset()
            ctrl.addItems([self._build_item(s) for s in streams])
        except Exception:
            pass

    def _status_text(self):
        count = len(self._streams)
        if self._loaded:
            return _L(_ID_FOUND).format(count, _plural(count))
        return _L(_ID_FOUND_SEARCHING).format(count, _plural(count))

    def _set_label(self, control_id, text):
        try:
            self.getControl(control_id).setLabel(text)
        except Exception:
            pass

    def _set_status(self, text):
        self._set_label(_STATUS, text)

    def _notify_no_streams(self):
        try:
            xbmcgui.Dialog().notification(
                _ADDON.getAddonInfo('name'), _L(_ID_NO_STREAMS),
                xbmcgui.NOTIFICATION_WARNING)
        except Exception:
            pass


def show_stream_dialog(item_factory, sort_key=None, streams=None,
                       producer=None, title_id=_ID_TITLE):
    """Open the stream picker and return the chosen stream dict (or None)."""
    addon_path = xbmcvfs.translatePath(_ADDON.getAddonInfo('path'))
    dialog = StreamSelectDialog(
        'script-stremio2kodi-streamselect.xml',
        addon_path, 'Default', '1080i')
    dialog.setup(item_factory, sort_key=sort_key, streams=streams,
                 producer=producer, title_id=title_id)
    dialog.doModal()
    selected = dialog.selected_stream
    del dialog
    return selected
