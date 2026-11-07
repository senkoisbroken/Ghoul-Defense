"""Apply a validated friend ZIP without replacing environments or saved cards."""

from datetime import datetime, timezone
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import queue
import re
import shutil
import stat
import subprocess
import tempfile
import threading
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
import uuid
import zipfile
import zlib

ROOT_FILES = frozenset({
    'app.py', 'boss.py', 'catalog.py', 'controls.py', 'desktop.py', 'ghoul.py',
    'movement.py', 'ultimate.py', 'ws_repeater.py', 'updater.py',
    'start.bat', 'install.bat', 'update.bat', 'requirements.txt', 'README.md',
    'INSTALL.txt', 'package_info.json',
})
REPOSITORY = 'senkoisbroken/Ghoul-Defense'
RELEASE_API = 'https://api.github.com/repos/'+REPOSITORY+'/releases/latest'
ZIP_NAME = 'Ghoul-Defense-friend.zip'


class UpdateError(RuntimeError):
    pass


def read_https(url, limit):
    if urlsplit(url).scheme != 'https':
        raise UpdateError('Update downloads must use HTTPS.')
    request = Request(url, headers={'User-Agent': 'Ghoul-Defense-Updater',
                                    'Accept': 'application/vnd.github+json',
                                    'X-GitHub-Api-Version': '2026-03-10'})
    try:
        with urlopen(request, timeout=20) as response:
            if urlsplit(response.geturl()).scheme != 'https':
                raise UpdateError('The download redirected to an insecure connection.')
            data = response.read(limit+1)
            if len(data) > limit:
                raise UpdateError('The update response is larger than allowed.')
            return data
    except HTTPError as exc:
        message = ('No published update was found.' if exc.code == 404
                   else 'GitHub could not serve the update (HTTP '+str(exc.code)+'). Try again later.')
        raise UpdateError(message) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise UpdateError('Could not download the update. Check your internet connection.') from exc


def download_latest(folder):
    try:
        release = json.loads(read_https(RELEASE_API, 1024*1024))
        if release.get('draft') or release.get('prerelease'):
            raise UpdateError('No stable published update was found.')
        assets = {}
        for asset in release['assets']:
            if asset.get('name') in (ZIP_NAME, 'checksums.sha256'):
                if asset['name'] in assets:
                    raise UpdateError('The release contains duplicate update assets.')
                url = asset['browser_download_url']
                parsed = urlsplit(url)
                if (parsed.scheme != 'https' or parsed.netloc != 'github.com'
                        or not parsed.path.startswith('/'+REPOSITORY+'/releases/download/')
                        or parsed.query or parsed.fragment):
                    raise UpdateError('The release contains an unexpected download URL.')
                assets[asset['name']] = url
        if set(assets) != {ZIP_NAME, 'checksums.sha256'}:
            raise UpdateError('This release is missing its update ZIP or checksums.')
        checksum_text = read_https(assets['checksums.sha256'], 16*1024).decode('ascii')
        digests = []
        for line in checksum_text.splitlines():
            parts = line.split()
            if len(parts) == 2 and parts[1].lstrip('*') == ZIP_NAME:
                digests.append(parts[0].lower())
        if len(digests) != 1 or re.fullmatch(r'[0-9a-f]{64}', digests[0]) is None:
            raise UpdateError('The release checksum is missing or invalid.')
        data = read_https(assets[ZIP_NAME], 64*1024*1024)
        if hashlib.sha256(data).hexdigest() != digests[0]:
            raise UpdateError('The download failed its SHA-256 check. No update was applied.')
        path = Path(folder) / ZIP_NAME
        path.write_bytes(data)
        return path
    except UpdateError:
        raise
    except (KeyError, TypeError, ValueError, AttributeError, OSError) as exc:
        raise UpdateError('Cannot read the published update: '+str(exc)) from exc


def update_latest(install_dir):
    ensure_macro_closed(Path(install_dir).resolve())
    with tempfile.TemporaryDirectory(prefix='ghoul-update-') as folder:
        return update_zip(download_latest(folder), install_dir)


def safe_name(name):
    parts = PurePosixPath(name).parts
    if (not parts or str(PurePosixPath(name)) != name or '\\' in name or name.startswith('/')
            or any(part in ('.', '..') or not re.fullmatch(r'[A-Za-z0-9_.-]+', part)
                   for part in parts)):
        return False
    reserved = {'CON', 'PRN', 'AUX', 'NUL'} | {
        prefix+str(i) for prefix in ('COM', 'LPT') for i in range(1, 10)}
    if any(part.endswith('.') or part.split('.')[0].upper() in reserved for part in parts):
        return False
    return (name in ROOT_FILES
            or len(parts) == 1 and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*\.py', name) is not None
            or len(parts) == 2 and parts[0] == 'assets' and parts[1].endswith('.png')
            or len(parts) == 3 and parts[0] == 'catalog'
            and parts[1] in ('perks', 'relics') and parts[2].endswith('.png'))


def read_package(path):
    try:
        files = {}
        seen = set()
        with zipfile.ZipFile(path) as archive:
            entries = archive.infolist()
            if len(entries) > 10000 or sum(entry.file_size for entry in entries) > 64*1024*1024:
                raise UpdateError('Update ZIP is too large.')
            for entry in entries:
                name = entry.filename
                if name.casefold() in seen:
                    raise UpdateError('Duplicate ZIP entry: ' + name)
                seen.add(name.casefold())
                if (not name.startswith('Ghoul-Defense/') or '\\' in name
                        or '..' in PurePosixPath(name).parts
                        or stat.S_ISLNK(entry.external_attr >> 16)):
                    raise UpdateError('Unsafe ZIP entry: ' + name)
                relative = name[len('Ghoul-Defense/'):]
                if entry.is_dir():
                    if relative.rstrip('/') not in ('', 'assets', 'catalog',
                                                    'catalog/perks', 'catalog/relics'):
                        raise UpdateError('Unexpected ZIP directory: ' + name)
                    continue
                if not safe_name(relative):
                    raise UpdateError('Unexpected ZIP file: ' + name)
                files[relative] = archive.read(entry)
        raw_manifest = files.get('package_info.json')
        if raw_manifest is None:
            raise UpdateError('This ZIP has no package_info.json. Use a current friend ZIP.')
        manifest = json.loads(raw_manifest)
        hashes = manifest.get('sha256')
        build = manifest.get('package_version', manifest.get('source_build'))
        if (not isinstance(hashes, dict) or not isinstance(build, str) or not build
                or set(hashes) != set(files)-{'package_info.json'}
                or not {'app.py', 'start.bat', 'requirements.txt'} <= set(hashes)):
            raise UpdateError('The update manifest is incomplete.')
        for name, digest in hashes.items():
            if not isinstance(digest, str) or hashlib.sha256(files[name]).hexdigest() != digest:
                raise UpdateError('Update file failed its hash check: ' + name)
        return files, build
    except UpdateError:
        raise
    except (OSError, ValueError, TypeError, AttributeError, zipfile.BadZipFile,
            RuntimeError, KeyError, EOFError, zlib.error) as exc:
        raise UpdateError('Cannot read update ZIP: ' + str(exc)) from exc


def ensure_macro_closed(install_dir):
    """Read process command lines only; never open Roblox or send input."""
    if os.name != 'nt':
        return
    env = os.environ.copy()
    env['GHOUL_UPDATE_APP'] = str(Path(install_dir) / 'app.py')
    script = """$ErrorActionPreference='Stop'
$target=$env:GHOUL_UPDATE_APP
$found=Get-CimInstance Win32_Process -Filter "Name = 'python.exe' OR Name = 'pythonw.exe'" |
 Where-Object { $_.CommandLine -and $_.CommandLine.IndexOf($target,[StringComparison]::OrdinalIgnoreCase) -ge 0 }
if ($found) { exit 2 }
"""
    try:
        result = subprocess.run(['powershell.exe', '-NoProfile', '-Command', script],
                                env=env, capture_output=True, timeout=15,
                                creationflags=subprocess.CREATE_NO_WINDOW)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise UpdateError('Could not check whether the helper is closed. Try again.') from exc
    if result.returncode == 2:
        raise UpdateError('Close Ghoul Defense first, then run update.bat again.')
    if result.returncode:
        raise UpdateError('Windows could not check running helpers. No update was applied.')


def destination(root, name):
    target = root / name
    if target.is_symlink() or not target.resolve().is_relative_to(root):
        raise UpdateError('Update path points outside the installation: ' + name)
    return target


@contextmanager
def update_lock(root):
    if os.name != 'nt':
        yield
        return
    import msvcrt
    try:
        destination(root, '.updates').mkdir(exist_ok=True)
        handle = destination(root, '.updates/update.lock').open('a+b')
    except OSError as exc:
        raise UpdateError('Cannot create the update lock: '+str(exc)) from exc
    try:
        if handle.tell() == 0:
            handle.write(b'0')
            handle.flush()
        handle.seek(0)
        try:
            msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise UpdateError('Another update is running. Close it and try again.') from exc
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    finally:
        handle.close()


def update_zip(zip_path, install_dir):
    files, build = read_package(zip_path)
    root = Path(install_dir).resolve()
    if not root.is_dir():
        raise UpdateError('The installation folder does not exist.')
    ensure_macro_closed(root)
    with update_lock(root):
        return apply_files(files, build, root)


def apply_files(files, build, root):
    changes = []
    try:
        for name in sorted(files, key=lambda name: (name == 'package_info.json', name)):
            target = destination(root, name)
            if name.startswith('catalog/') and target.exists():
                continue
            if not target.is_file() or target.read_bytes() != files[name]:
                changes.append(name)
    except OSError as exc:
        raise UpdateError('Cannot inspect installed files: ' + str(exc)) from exc
    if not changes:
        return {'updated': False, 'build': build, 'backup': None}
    tag = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')+'-'+uuid.uuid4().hex[:8]
    updates = destination(root, '.updates')
    stage = updates / ('staging-'+tag)
    backup = updates / ('backup-'+tag)
    existed = set()
    applied = []
    try:
        stage.mkdir(parents=True)
        backup.mkdir()
        for index, name in enumerate(changes):
            target = destination(root, name)
            (stage / str(index)).write_bytes(files[name])
            if target.exists():
                existed.add(name)
                saved = backup / name
                saved.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, saved)
        for index, name in enumerate(changes):
            target = destination(root, name)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(stage / str(index), target)
            applied.append(name)
    except (OSError, UpdateError) as exc:
        failed = []
        for name in reversed(applied):
            try:
                target = destination(root, name)
                if name in existed:
                    shutil.copy2(backup / name, target)
                else:
                    target.unlink(missing_ok=True)
            except (OSError, UpdateError):
                failed.append(name)
        message = ('Update failed; replaced files were restored.' if not failed
                   else 'Update failed; some files could not be restored: '+', '.join(failed))
        raise UpdateError(message+' Backup: '+str(backup)+' Details: '+str(exc)) from exc
    finally:
        if stage.is_dir():
            for path in stage.iterdir():
                try:
                    path.unlink()
                except OSError:
                    pass
            try:
                stage.rmdir()
            except OSError:
                pass
    return {'updated': True, 'build': build, 'backup': str(backup)}


def main():
    import sys
    import tkinter as tk
    from tkinter import filedialog, messagebox
    root = tk.Tk()
    root.withdraw()
    path = None
    if len(sys.argv) > 1:
        path = (filedialog.askopenfilename(title='Select a local Ghoul Defense friend ZIP',
                                          filetypes=[('ZIP update', '*.zip')])
                if sys.argv[1] == '--local' else sys.argv[1])
        if not path:
            root.destroy()
            return
    root.title('Ghoul Defense update')
    tk.Label(root, text=('Applying local update...' if path else
                        'Checking GitHub and downloading the latest update...'),
             padx=25, pady=20).pack()
    root.resizable(False, False)
    root.protocol('WM_DELETE_WINDOW', lambda: None)
    root.deiconify()
    results = queue.Queue()

    def worker():
        try:
            install = Path(__file__).resolve().parent
            results.put((True, update_zip(path, install) if path else update_latest(install)))
        except Exception as exc:
            results.put((False, str(exc)))

    def poll():
        try:
            success, result = results.get_nowait()
        except queue.Empty:
            root.after(75, poll)
            return
        root.withdraw()
        if success:
            text = ('Update complete.' if result['updated'] else 'This update is already installed.')
            text += '\n\nYour Python environment, saved cards and logs were kept.\n'
            text += 'Open start.bat to run the helper.\nBuild: '+result['build']
            if result['backup']:
                text += '\nBackup: '+result['backup']
            messagebox.showinfo('Ghoul Defense update', text)
        else:
            messagebox.showerror('Ghoul Defense update', result)
        root.destroy()

    threading.Thread(target=worker, name='ghoul-update', daemon=False).start()
    root.after(75, poll)
    root.mainloop()


if __name__ == '__main__':
    main()
