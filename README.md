# Ghoul Defense

Windows screenshot-based Ghoul Defense helper. It selects perks/relics, starts
waves, repeats W/S movement, follows detected boss lanes, and restarts runs.
It uses normal foreground keyboard/mouse input and does not read game memory.

## Download

- [Full friend package](https://github.com/senkoisbroken/Ghoul-Defense/releases/latest/download/Ghoul-Defense-friend.zip)
- [Online updater for existing installations](https://github.com/senkoisbroken/Ghoul-Defense/releases/latest/download/Ghoul-Defense-update-helper.zip)
- [Latest release](https://github.com/senkoisbroken/Ghoul-Defense/releases/latest)

New users: extract the full package and run `start.bat`. First setup installs
64-bit Python 3.13 and the required packages if needed. Focus Roblox and press
**F8** to start/pause. Close any separate W/S repeater first.

Existing users: extract the small updater ZIP into your existing Ghoul-Defense
folder once, including users who have the older file-picker updater. Close the
macro and run **update.bat**. It downloads the latest published GitHub release,
checks its SHA-256 checksum, backs up replaced files, and keeps `.venv`, logs,
and existing saved card pictures. Then run `start.bat`.
The small helper includes `package_layout.py`; keep it with `updater.py`.

Friends do not need GitHub accounts, tokens, or GitHub CLI. Offline updates
remain available by dragging a friend ZIP onto `update.bat`.

Updates become available after a new release is published. Local development
edits do not automatically publish themselves. Boss following remains dependent
on screen visibility and recognition; check a first run on a new layout.

The distributable source is in `Ghoul-Defense/`. Releases exclude environments,
logs, diagnostic captures, and development screenshots. See the included
README for controls, priorities, saved pictures and troubleshooting.

The current refactor separates OCR/card policy, detection, automation and input
modules while preserving controls and recognition thresholds. The updater
shares the runtime inventory used by build fingerprints, rechecks the helper
under its update lock, and retains the newest five safely removable backups.
