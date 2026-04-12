import os
import shutil
import xbmc
import xbmcaddon
import xbmcgui
import xbmcvfs


def install_player_file():
    """Copy the TMDbHelper player JSON to the correct location."""
    addon = xbmcaddon.Addon()
    addon_name = addon.getAddonInfo('name')
    L = addon.getLocalizedString
    addon_path = xbmcvfs.translatePath(addon.getAddonInfo('path'))
    source = os.path.join(
        addon_path, 'resources', 'player', 'stremio2kodi.json'
    )

    players_dir = xbmcvfs.translatePath(
        'special://profile/addon_data/'
        'plugin.video.themoviedb.helper/players/'
    )
    if not os.path.exists(players_dir):
        os.makedirs(players_dir)

    dest = os.path.join(players_dir, 'stremio2kodi.json')

    try:
        shutil.copy2(source, dest)
        xbmcgui.Dialog().notification(
            addon_name,
            L(30070),
            xbmcgui.NOTIFICATION_INFO
        )
    except Exception as e:
        xbmc.log(
            'Stremio2Kodi: Failed to install player: {}'.format(e),
            xbmc.LOGERROR
        )
        xbmcgui.Dialog().notification(
            addon_name,
            L(30071),
            xbmcgui.NOTIFICATION_ERROR
        )
