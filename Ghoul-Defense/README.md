# Ghoul Defense - Windows friend package

Extract the entire ZIP to a writable folder, then double-click **start.bat**.
The launcher checks for 64-bit Python 3.13. If needed, it downloads Python
3.13.17 from python.org and installs it for your Windows account. It creates a
local `.venv` and installs the pinned dependencies. Internet is required for
first-time setup. No administrator installation is required.

`install.bat` runs setup without opening the helper. You normally need it only
once; `start.bat` also handles setup when needed. Keep the extracted files together.
Once setup succeeds, normal launches reuse the existing environment. Packages
are installed again when requirements change, or when you run `install.bat`
to repair the installation.

## Updating an existing installation

1. Close the Ghoul Defense helper.
2. Double-click **update.bat** in your existing Ghoul-Defense folder.
3. It downloads the latest published release from
   https://github.com/senkoisbroken/Ghoul-Defense and checks its SHA-256 checksum.
4. Wait for Update complete, then open **start.bat**.

Friends do not need GitHub accounts, tokens, or GitHub CLI. An internet connection
is needed to download updates. Local edits are available to friends after the
maintainer publishes a new GitHub release.

For offline updates, drag a downloaded friend ZIP onto `update.bat` (or run
`update.bat --local` to choose a ZIP). Updates keep `.venv`, logs,
and existing catalog pictures, and add any new catalog pictures. Required
packages are refreshed on the next launch only if requirements changed.
Replaced files are backed up under `.updates/backup-*`. The updater validates
the package manifest and file hashes before applying changes, and attempts to
restore replaced files if applying an update fails.

For friends with an older version that has no `update.bat`, extract the small
**Ghoul-Defense-update-helper.zip** into their existing Ghoul-Defense folder
once. It adds `update.bat`, `updater.py`, and the shared `package_layout.py`
dependency; then follow the steps above.
New installations already include the online updater. Friends who have the
older file-picker updater should also copy the new updater-helper ZIP into
their existing folder once to enable direct GitHub updates.

The refactored updater keeps the newest five safe backup trees after a
successful update and clears stale staging trees while holding the update lock.
Linked or inaccessible trees are left alone. The helper's runtime fingerprint
now covers every runtime module, required reference asset and launcher.

## Use

1. Open Ghoul Defense in Roblox.
2. Open `start.bat`. The helper starts paused.
3. Close any separate W/S repeater or other macro that sends the same controls.
4. Focus Roblox and press **F8** to start. Press **F8** again to pause.
5. Keep the game visible and in the foreground. Focus loss stops input.

F8 controls everything: six W taps followed by six S taps at the current 1.2x
speed, perk/relic selection, and starting waves. Menu choices prioritize damage,
then attack speed, then turret buffs; other offers use the first available card.
One-, two- and three-card menus are supported.

With 1-3 enemies remaining and a confirmed living boss HUD, movement tries to
align with the boss and follow lane changes. If its lane is unclear, movement
holds while the screen is checked again. This remains experimental; first-run
monitoring is recommended on a different computer or window layout.

The helper can press **F** when aligned with a boss after four seconds with
little HP progress, provided Quinque Strike reads Ready. There is a ten-second
cooldown between accepted F inputs. It presses **E** on a verified Play Again
screen to restart. These checks verify sent input; they cannot guarantee that
the game accepted an ability or completed a restart.

## Saved card pictures

Your package includes the current perk/relic picture catalog. All offered cards
are saved, including unselected ones, under `catalog/perks` and `catalog/relics`.
There is one PNG per kind and normalized recognized name. Existing images are
not overwritten, and changed pick counts or hover appearance do not add copies.

## Troubleshooting

- Run from the extracted folder, not inside the ZIP viewer.
- If setup fails, keep the error window open and share its text.
- `macro.log` records actions, F8 state and the loaded source build. It rotates
  automatically. `work/boss_lane_unclear.png` holds the latest unclear boss frame.
- If the game UI is clipped, hidden or changed by an update, detection may wait.
- Candy Bonus belongs to permanent Upgrades, not run perks. The helper does not
  buy permanent upgrades, spend Robux, read Roblox process memory or inject code.

This ZIP contains the current helper, reference assets and card catalog. Python
and packages are downloaded by setup; no machine-specific virtual environment,
account configuration, development screenshots or old logs are bundled.

Optional diagnostic sharing: tick the checkbox in the app and enter the private pairing code supplied by the macro owner. Selected action and status events are sent to the owner. Screenshots and complete local log files are not uploaded. Uncheck to stop sharing and remove the saved Windows-encrypted code. Received events are retained for 14 days.
