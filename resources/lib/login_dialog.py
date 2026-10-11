"""QR device-login dialog for Stremio.

Shows a QR code, the login link and a 5-minute countdown, polls the Stremio
link API every 3 seconds and closes with the link authKey once the user
authorises the device on their phone. A single daemon worker thread drives
the polling and is stopped promptly when the dialog is closed (Back / Close).
"""
import os
import threading
import time

import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs

import stremio_auth

_ADDON = xbmcaddon.Addon()
_QR_TEMP_PREFIX = 'stremio2kodi_qr_'
_CODE_TTL = 300        # seconds a login code stays valid
_POLL_INTERVAL = 3     # seconds between read polls
_RETRY_DELAY = 5       # seconds before retrying a failed create

# ACTION_PREVIOUS_MENU / ACTION_NAV_BACK
_BACK_ACTIONS = (10, 92)


def _L(string_id):
    return _ADDON.getLocalizedString(string_id)


def _countdown_text(seconds):
    seconds = max(0, int(seconds))
    return _L(30142).format('{}:{:02d}'.format(seconds // 60, seconds % 60))


def _qr_temp_path():
    temp_dir = xbmcvfs.translatePath('special://temp/')
    return os.path.join(
        temp_dir,
        '{}{}.png'.format(_QR_TEMP_PREFIX, int(time.time() * 1000)))


class LoginDialog(xbmcgui.WindowXMLDialog):
    """Modal QR login dialog. Run it via :func:`show_login_dialog`."""

    _BACKGROUND = 1
    _TITLE_LABEL = 2
    _QR_IMAGE = 10
    _LINK_LABEL = 20
    _STATUS_LABEL = 21
    _NEW_CODE_BUTTON = 30
    _CLOSE_BUTTON = 31

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._stop = threading.Event()
        self._regen = threading.Event()
        self._thread = None
        self._auth_key = None
        self._code = None
        self._qr_path = None
        self._deadline = 0.0

    @property
    def auth_key(self):
        """The link authKey once the device is authorised, else None."""
        return self._auth_key

    # --- lifecycle ---------------------------------------------------------

    def onInit(self):
        self._apply_static_text()
        self._thread = threading.Thread(target=self._worker, daemon=True)
        self._thread.start()

    def _apply_static_text(self):
        """Set background and text from Python (skin XML cannot localize)."""
        self._set_background()
        self._set_label(self._TITLE_LABEL, _L(30140))
        self._set_label(self._NEW_CODE_BUTTON, _L(30143))
        self._set_label(self._CLOSE_BUTTON, _L(30144))

    def _set_background(self):
        path = os.path.join(
            xbmcvfs.translatePath(_ADDON.getAddonInfo('path')),
            'resources', 'media', 'login_bg.png')
        try:
            self.getControl(self._BACKGROUND).setImage(path)
        except Exception:
            pass

    def onClick(self, control_id):
        if control_id == self._NEW_CODE_BUTTON:
            self._regen.set()
        elif control_id == self._CLOSE_BUTTON:
            self._request_close()

    def onAction(self, action):
        if action.getId() in _BACK_ACTIONS:
            self._request_close()

    def _request_close(self):
        self._stop.set()
        self.close()

    # --- worker thread -----------------------------------------------------

    def _worker(self):
        monitor = xbmc.Monitor()
        last_poll = 0.0
        try:
            self._refresh_code()
            while not self._stop.is_set() and not monitor.abortRequested():
                now = time.time()
                if self._regen.is_set():
                    self._regen.clear()
                    self._refresh_code()
                    last_poll = 0.0
                    continue
                if now >= self._deadline:
                    self._refresh_code()
                    last_poll = 0.0
                    continue

                self._set_status(_countdown_text(self._deadline - now))
                if now - last_poll >= _POLL_INTERVAL:
                    last_poll = now
                    result = stremio_auth.read_link(self._code)
                    if (result and result.get('success')
                            and result.get('authKey')):
                        self._auth_key = result['authKey']
                        self._set_status(_L(30146))
                        self._stop.wait(2)
                        break
                if self._stop.wait(1):
                    break
        finally:
            self._cleanup()
            self._stop.set()
            try:
                self.close()
            except Exception:
                pass

    def _refresh_code(self):
        """Request a fresh code + QR. Returns True on success."""
        result = stremio_auth.create_link()
        if not result or not result.get('code'):
            xbmc.log('Stremio2Kodi: login: create_link failed',
                     xbmc.LOGWARNING)
            self._set_status(_L(30147))
            self._stop.wait(_RETRY_DELAY)
            return False
        self._code = result['code']
        xbmc.log('Stremio2Kodi: login: code {} created'.format(self._code),
                 xbmc.LOGINFO)
        self._set_link(result.get('link', ''))
        self._set_qr(result.get('qrcode', ''))
        self._deadline = time.time() + _CODE_TTL
        return True

    # --- UI helpers --------------------------------------------------------

    def _set_label(self, control_id, text):
        try:
            self.getControl(control_id).setLabel(text)
        except Exception:
            pass

    def _set_status(self, text):
        try:
            self.getControl(self._STATUS_LABEL).setLabel(text)
        except Exception:
            pass

    def _set_link(self, text):
        try:
            self.getControl(self._LINK_LABEL).setLabel(text)
        except Exception:
            pass

    def _set_qr(self, url):
        if not url:
            xbmc.log('Stremio2Kodi: login: create response had no qrcode',
                     xbmc.LOGWARNING)
            return
        path = _qr_temp_path()
        try:
            if not stremio_auth.download_qr(url, path):
                xbmc.log('Stremio2Kodi: login: QR download failed for {}'
                         .format(url), xbmc.LOGWARNING)
                return
        except Exception as e:
            xbmc.log('Stremio2Kodi: login: QR download error: {}'.format(e),
                     xbmc.LOGWARNING)
            return
        self._delete_qr_file()
        self._qr_path = path
        try:
            self.getControl(self._QR_IMAGE).setImage(path)
            xbmc.log('Stremio2Kodi: login: QR image set from {}'.format(path),
                     xbmc.LOGINFO)
        except Exception as e:
            xbmc.log('Stremio2Kodi: login: setImage failed: {}'.format(e),
                     xbmc.LOGWARNING)

    # --- cleanup -----------------------------------------------------------

    def _delete_qr_file(self):
        if self._qr_path and os.path.exists(self._qr_path):
            try:
                os.remove(self._qr_path)
            except OSError:
                pass
        self._qr_path = None

    def _cleanup(self):
        self._delete_qr_file()
        temp_dir = xbmcvfs.translatePath('special://temp/')
        try:
            for name in os.listdir(temp_dir):
                if (name.startswith(_QR_TEMP_PREFIX)
                        and name.endswith('.png')):
                    try:
                        os.remove(os.path.join(temp_dir, name))
                    except OSError:
                        pass
        except OSError:
            pass


def show_login_dialog(addon_path):
    """Open the QR login dialog. Returns the link authKey or None."""
    dialog = LoginDialog(
        'script-stremio2kodi-accountlogin.xml',
        addon_path, 'Default', '1080i')
    dialog.doModal()
    key = dialog.auth_key
    del dialog
    return key
