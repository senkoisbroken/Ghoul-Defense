"""Shared update allowlist and deterministic runtime inventory."""

import hashlib
from pathlib import Path, PurePosixPath
import re


ROOT_FILES = frozenset({
    'app.py', 'boss.py', 'catalog.py', 'controls.py', 'desktop.py', 'ghoul.py',
    'movement.py', 'ultimate.py', 'ws_repeater.py', 'updater.py',
    'start.bat', 'install.bat', 'update.bat', 'requirements.txt', 'README.md',
    'INSTALL.txt', 'package_info.json',
})
BOOTSTRAP_FILES = ('update.bat', 'updater.py', 'package_layout.py')


def is_allowed(name):
    """Accept only normalized package paths, including future root Python modules."""
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


def runtime_files(root):
    """Return sorted relative POSIX names of existing runtime files, excluding state.

    Root Python modules are discovered dynamically so future module extractions
    automatically affect the build fingerprint. Assets include the shipped UI
    and boss templates; saved catalog images are deliberately outside this list.
    """
    root = Path(root)
    paths = list(root.glob('*.py')) + list((root / 'assets').glob('*.png'))
    paths.extend(root / name for name in
                 ('start.bat', 'install.bat', 'update.bat', 'requirements.txt'))
    return tuple(sorted(path.relative_to(root).as_posix() for path in paths if path.is_file()))


def fingerprint(root):
    """Hash file names and contents in runtime order; retain the 12-character log format."""
    root = Path(root)
    digest = hashlib.sha256()
    for name in runtime_files(root):
        data = (root / name).read_bytes()
        digest.update(name.encode('utf-8') + b'\0')
        digest.update(len(data).to_bytes(8, 'big'))
        digest.update(data)
    return digest.hexdigest()[:12]
