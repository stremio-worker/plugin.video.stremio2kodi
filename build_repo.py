#!/usr/bin/env python3
"""Kodi repository build script.

Sırayla:
  1. Tüm addon.xml.md5 dosyalarını siler.
  2. Tüm addon.xml dosyalarını bulup yanlarına addon.xml.md5 yazar.
  3. repository.stremio/ içindeki dosyaları (repository.stremio-*.zip hariç)
     zipleyip aynı klasöre repository.stremio-<version>.zip olarak koyar.
  4. addon.xml dosyalarından addons.xml ve addons.xml.md5 üretir.

Kullanım:
    python3 build_repo.py
"""
import fnmatch
import hashlib
import os
import sys
import xml.etree.ElementTree as ET
import zipfile

REPOSITORY_ADDON = 'repository.stremio'
SKIP_DIRS = {'__pycache__', '.git'}


def md5_of_bytes(data):
    return hashlib.md5(data).hexdigest()


def find_files(root, name):
    """root altında (alt klasörler dahil) adı `name` olan tüm dosyaları döndürür."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):

        dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
        if name in filenames:
            found.append(os.path.join(dirpath, name))
    return found


def delete_md5_files(root):
    for path in find_files(root, 'addon.xml.md5'):
        os.remove(path)
        print('  silindi: {}'.format(os.path.relpath(path, root)))


def create_md5_files(root):
    for xml_path in find_files(root, 'addon.xml'):
        with open(xml_path, 'rb') as f:
            digest = md5_of_bytes(f.read())
        with open(xml_path + '.md5', 'w', encoding='utf-8', newline='\n') as f:
            f.write(digest)
        print('  oluşturuldu: {}.md5'.format(os.path.relpath(xml_path, root)))


def build_repository_zip(root):
    repo_dir = os.path.join(root, REPOSITORY_ADDON)
    addon_xml = os.path.join(repo_dir, 'addon.xml')
    if not os.path.isfile(addon_xml):
        sys.exit('{}/addon.xml bulunamadı'.format(REPOSITORY_ADDON))

    version = ET.parse(addon_xml).getroot().get('version')
    zip_name = '{}-{}.zip'.format(REPOSITORY_ADDON, version)
    zip_path = os.path.join(repo_dir, zip_name)

    count = 0

    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as archive:
        for dirpath, dirnames, filenames in os.walk(repo_dir):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS)
            for filename in sorted(filenames):
                # Önceki/şimdiki repository zip'lerini ve md5'leri alma
                if fnmatch.fnmatch(filename, REPOSITORY_ADDON + '-*.zip'):
                    continue
                if filename.endswith('.md5') or filename == '.DS_Store':
                    continue
                full = os.path.join(dirpath, filename)
                rel = os.path.relpath(full, repo_dir)
                archive.write(full, os.path.join(REPOSITORY_ADDON, rel))
                count += 1
    print('  {}/{} ({} dosya)'.format(REPOSITORY_ADDON, zip_name, count))


def addon_block(xml_path):
    """addon.xml içeriğini XML bildirimi olmadan döndürür."""
    with open(xml_path, encoding='utf-8') as f:
        text = f.read().lstrip()
    if text.startswith('<?xml'):
        end = text.find('?>')
        if end != -1:
            text = text[end + 2:].lstrip()
    return text.rstrip() + '\n'


def write_addons_xml(root):
    # Sadece kökün hemen altındaki klasörlerdeki addon.xml dosyaları
    xml_paths = []
    for entry in sorted(os.listdir(root)):
        candidate = os.path.join(root, entry, 'addon.xml')

        if os.path.isfile(candidate):
            xml_paths.append(candidate)

    body = '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>\n<addons>\n'
    body += ''.join(addon_block(p) for p in xml_paths)
    body += '</addons>\n'

    addons_path = os.path.join(root, 'addons.xml')
    with open(addons_path, 'w', encoding='utf-8', newline='\n') as f:
        f.write(body)
    with open(addons_path + '.md5', 'w', encoding='utf-8', newline='\n') as f:
        f.write(md5_of_bytes(body.encode('utf-8')))
    print('  addons.xml ({} eklenti) + addons.xml.md5'.format(len(xml_paths)))


def main():
    root = os.path.dirname(os.path.abspath(__file__))
    print('Klasör: {}'.format(root))

    print('[1/4] Eski addon.xml.md5 dosyaları siliniyor')
    delete_md5_files(root)

    print('[2/4] addon.xml.md5 dosyaları oluşturuluyor')
    create_md5_files(root)

    print('[3/4] Repository zip oluşturuluyor')
    build_repository_zip(root)

    print('[4/4] addons.xml oluşturuluyor')
    write_addons_xml(root)

    print('Bitti.')

    return 0


if __name__ == '__main__':
    sys.exit(main())