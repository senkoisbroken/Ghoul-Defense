# Ghoul Defense Helper

A Windows helper that uses screenshots and ordinary foreground keyboard/mouse
input. It does not read Roblox memory or inject code.

## Controls and behavior

- **F8** starts or pauses movement, menu choices and wave automation together.
- Patrol repeats six W taps followed by six S taps at the existing 1.2x timing.
- Choices prioritize Twin Scythes, damage, attack speed and turret buffs; other offers use
  the first available card. One-, two- and three-card menus are supported.
- With 1–3 remaining enemies and a confirmed living boss, movement follows its
  visible lane. An unclear boss position holds movement while recognition retries.
- **F** is used against an aligned boss after four seconds with little HP
  progress, only when Quinque Strike reads Ready, with ten seconds between uses.
- Verified Play Again screens receive **E**. This checks sent input; it cannot
  guarantee the game consumed an ability or completed a restart.
- Movement releases input during menus, pause, focus loss and shutdown.
  Roblox must remain visible in the foreground. Close separate W/S repeaters.

## Launch and installation

This development folder's `start.bat` uses the existing interpreter at
`E:\omniroute\Guess-The-Card-portable\.venv\Scripts\pythonw.exe` and installs nothing.

The distribution package has portable `start.bat`, `install.bat`
and `update.bat` launchers. Its first setup installs 64-bit Python 3.13 and pinned
packages if needed. `install.bat` runs setup/repair without starting the helper.
Normal starts reuse the environment; changed requirements trigger package setup.

## Updates

The published distribution is at https://github.com/senkoisbroken/Ghoul-Defense.
Close the helper and run `update.bat`; it downloads the newest published
release anonymously and verifies SHA-256 checksums and package hashes.
`update.bat --local` or dropping a distribution ZIP onto the launcher supports offline
updates. Installations using the previous updater need the current setup ZIP
once; copy its App Files/updater.py into the existing application folder
(App Files for the clean setup) before running Update.bat to retain saved data.

The updater keeps `.venv`, logs and existing catalog pictures. `package_info.json`
records the packaged version and hashes. Replaced files are backed up under
`.updates/backup-*`; the refactored updater retains the newest five safe backup
trees and clears stale staging trees under the update lock. Linked or inaccessible
trees are left alone. Applying a failed update attempts to restore replaced files.

Refactor changes in this development folder are not published automatically.
Updating the full ZIP, bootstrap helper and GitHub release is a separate release
step. The bootstrap helper must include `package_layout.py` with `updater.py`.

## Saved cards, layouts and diagnostics

All offered perk/relic pictures, including unselected choices, are saved under
`catalog/perks` and `catalog/relics`. Deduplication is by kind and normalized
recognized name. Existing files are never overwritten; this persists on restart.

Recognition supports the recorded landscape layouts and scale variations in
the regression fixtures. This does not guarantee every layout, occlusion, game
update or very small/portrait window. Lane following remains screen-dependent.

`macro.log` rotates at 1 MB with two backups. It records the complete runtime
fingerprint, action decisions, movement gates and boss diagnostics.
`work/boss_lane_unclear.png` holds the latest unclear boss frame.

Use **Send diagnostic logs** to review a sanitized copy of the latest 32 KiB
of `macro.log`, then choose whether to send it to the macro owner's AWS receiver.
The preview can still contain private information: review it before sending.
The upload excludes screenshots and rotated log backups. No pairing code is
needed. Received records are retained for 14 days. Keep the macro open until
it reports success. No logs are sent automatically.

## Module map

- `app.py`: GUI, controls and the public action/ultimate entry points.
- `automation.py`: screen-worker steps, retry bookkeeping and reset paths.
- `components.py`: shared lazy OCR wiring, logging and runtime fingerprint.
- `names.py`, `ocr.py`, `gate.py`, `detector.py`, `frame.py`: card policy,
  recognition, gate/menu detection and shared normalization.
- `ghoul.py`: compatibility exports for existing imports and manual probes.
- `boss.py`: HUD parsing, bar/sprite geometry and boss hold state.
- `win_input.py`: shared Windows input primitives; `desktop.py` and
  `ws_repeater.py` retain their adapter APIs and the standalone repeater.
- `movement.py`, `controls.py`, `ultimate.py`, `catalog.py`: movement,
  capture ownership, ultimate policy and catalog persistence.
- `package_layout.py`, `updater.py`: runtime inventory, validated updates,
  locking, backup/rollback and cleanup.

## Verification and manual tools

Run explicit test modules only through `work/check_tests.py`, using the existing
project Python. Each group is limited to 512 MiB and 45 seconds; do not use full
unittest discovery or raise those limits. Disable bytecode writes when verifying
state integrity. See REVIEW.md for the current matrix.

Historical probes are in `work/manual/`; they are not automated tests. Some
have live/network or validation-folder side effects, so run them only after
review and explicit authorization. `work/check_tests.py` and `work/seed_catalog.py`
remain at their original paths. Recorded fixtures remain beside their tests.
