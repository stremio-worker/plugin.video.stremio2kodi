import os
import json
import xbmcaddon
import xbmcvfs


class AddonManager:
    """Manages the persisted list of configured Stremio add-ons."""

    def __init__(self):
        addon = xbmcaddon.Addon()
        self.profile_path = xbmcvfs.translatePath(
            addon.getAddonInfo('profile')
        )
        self.data_file = os.path.join(
            self.profile_path, 'stremio_addons.json'
        )
        self._ensure_profile_dir()

    def _ensure_profile_dir(self):
        if not os.path.exists(self.profile_path):
            os.makedirs(self.profile_path)

    def get_addons(self):
        """Return the list of configured Stremio add-ons."""
        if not os.path.exists(self.data_file):
            return []
        try:
            with open(self.data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            return []

    def _save(self, addons):
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(addons, f, indent=2, ensure_ascii=False)

    @staticmethod
    def _normalize(url):
        url = url.strip()
        if url.startswith('stremio://'):
            url = 'https://' + url[len('stremio://'):]
        url = url.rstrip('/')
        if url.endswith('/manifest.json'):
            url = url[:-len('/manifest.json')]
        return url

    def add_addon(self, url, name=None):
        """Add a Stremio add-on. Returns True on success, False if duplicate."""
        addons = self.get_addons()
        norm = self._normalize(url)
        for existing in addons:
            if self._normalize(existing['url']) == norm:
                return False
        addons.append({
            'url': url.strip(),
            'name': name or url.strip()
        })
        self._save(addons)
        return True

    def remove_addon(self, idx):
        """Remove a Stremio add-on by its list index."""
        addons = self.get_addons()
        if 0 <= idx < len(addons):
            addons.pop(idx)
            self._save(addons)
            return True
        return False
