# Snapchat Friend Remover

Bulk-remove Snapchat friends and mass-unfollow accounts from your own account using ADB and Android's `uiautomator`. **Android only** -- this does not work with iOS.

The tool drives the real Snapchat app on your Android phone over USB -- it reads the screen as an XML accessibility tree, matches UI elements by their text, and taps them programmatically. Two elements that Snapchat hides from the accessibility tree (the three-dots menu on a profile and the "Remove" confirmation button) are handled with coordinate-based taps: the three-dots position is calibrated per-device, and the confirm button is anchored relative to the visible "Cancel" button.

Comes with a Tkinter GUI (`gui.py`) for point-and-click operation and a CLI (`snap_remover.py`) for scripting.

## Disclaimer

**Automating Snapchat may violate its Terms of Service.** Use this tool at your own risk. It is intended solely for managing your own account. The author provides no warranty and is not responsible for any account actions, restrictions, or bans that may result from using this software. By using it, you accept full responsibility.

## Requirements

- **Android phone** with **USB debugging enabled**, connected via USB. **iOS is not supported** -- this tool relies on Android's `uiautomator` and ADB, which have no iOS equivalent.
- **Python 3.10+** on your computer (Windows, macOS, or Linux)
- **Android platform-tools** (`adb`) on your PATH:
  - Windows: `winget install Google.PlatformTools`
  - macOS: `brew install android-platform-tools`
  - Linux: `sudo apt install android-tools-adb` (or equivalent)
- **Snapchat set to English** -- the tool matches English UI strings like "Manage Friendship", "Remove Friend", and "Cancel"

## Setup

1. Clone or download this repo.
2. On your Android phone, enable **Developer Options** (Settings > About Phone > tap Build Number 7 times), then enable **USB Debugging** in Developer Options.
3. Connect your phone via USB. Run `adb devices` and confirm it shows your device as `device`. If it says `unauthorized`, accept the USB debugging prompt on your phone.
4. Open Snapchat on your phone.

No Python dependencies beyond the standard library are needed.

## Calibration (required first step)

The three-dots menu icon on Snapchat's profile screen is invisible to `uiautomator`, so the tool taps it by saved coordinates. These coordinates differ by device/resolution and **must be calibrated once** before removing anyone.

### GUI calibration (recommended)

1. On your phone, open any friend's **profile** (tap their name in the friends list, then tap the name header in the chat).
2. In the GUI, click **Calibrate three-dots**.
3. A screenshot appears. Click the three-dots icon in the screenshot.
4. The coordinate is saved to `config.json`.

### CLI calibration

```
python snap_remover.py --calibrate X Y
```

where X and Y are the pixel coordinates of the three-dots icon on your phone's screen.

## Usage: GUI (recommended)

```
python gui.py
```

The GUI has two tabs: **Friends** (remove friends) and **Following** (unfollow accounts).

### Friends tab workflow

1. **Scan friends** -- scrolls through your Snapchat friends list and builds `friends.txt` (a plain-text roster of every friend, defaulting to `keep`).
2. **Calibrate three-dots** -- required before first removal (see Calibration above).
3. **Check/uncheck** names in the list. Checked = will be removed. Use "Mark all" / "Clear all" for bulk selection.
4. **Save list** -- writes your keep/drop choices to `friends.txt`.
5. Set **delay** (min/max seconds between removals) and **count** (max removals this run).
6. On your phone, open Snapchat to the **friends list**, scrolled to the top.
7. Click **Start removal**. Watch the log pane. Click **Stop** anytime to halt after the current removal finishes.

### Following tab workflow

1. **Scan following** -- scrolls through your Following list and builds `following.txt`.
2. **Calibrate X button** -- required before first unfollow. On the Following list, tap Edit (so X buttons appear), then click "Calibrate X button" in the GUI and click any X in the screenshot.
3. **Check/uncheck** accounts to unfollow. Save the list.
4. On your phone, open the **Following list**.
5. Click **Start unfollow**. The tool enters Edit mode, taps each X, confirms, and moves on.

### Delay settings

The delay between actions is the main pacing control. The Friends tab defaults to 1-3 seconds; the Following tab defaults to 0.5-1 seconds (faster, since unfollowing is a simpler two-tap flow). Shorter is faster but more bot-like.

## Usage: CLI

All modes:

```
# Friends
python snap_remover.py --scan             # Build/refresh friends.txt (no taps)
python snap_remover.py --list             # Dump current screen + keep/drop decisions (no taps)
python snap_remover.py --run              # Dry audit: scroll whole list, print KEEP vs REMOVE (no taps)
python snap_remover.py --one "Name"       # Remove ONE friend, confirming every tap
python snap_remover.py --remove [N]       # Live batch: remove up to N friends (default 60)
python snap_remover.py --remove 50 --delay 1 3   # Batch with custom pacing
python snap_remover.py --calibrate X Y    # Save three-dots coordinate

# Following
python snap_remover.py --scan-following   # Build/refresh following.txt (no taps)
python snap_remover.py --unfollow [N]     # Batch unfollow up to N accounts (default 60)
python snap_remover.py --unfollow 100 --delay 0.5 1  # Faster pacing
python snap_remover.py --calibrate-x X    # Save X-button coordinate for unfollow
```

### Suggested CLI workflow

1. `--scan` to build the roster.
2. Edit `friends.txt`: change `keep` to `drop` for people to remove. Tip: find-replace `keep ` with `drop `, then set your few keepers back to `keep`.
3. `--run` to dry-audit your choices (nothing is tapped).
4. `--one "Name"` to test the full removal flow on one person, confirming each tap.
5. `--remove 5` to do a small live batch.
6. `--remove 60` (or higher) for the full run.

## Safety notes

- **`friends.txt`** and **`following.txt`** are the source of truth. Nobody is removed/unfollowed unless explicitly marked `drop`. Default is `keep`.
- **`protected.txt`** (if present) is a one-time migration mechanism: on first run with both files present, names in `protected.txt` are forced to `keep` in the roster, then the file is renamed to `.bak`.
- The tool enables **Do Not Disturb** and **stay-awake** on the phone during batch runs to prevent notification popups from blocking taps. Both are restored when the run ends.
- A **random delay** between actions makes the tapping pattern less uniform.
- If the tool detects it has left Snapchat or the expected screen (e.g., a notification takes focus), it **stops immediately** rather than blindly tapping on an unknown screen.
- If the tool loses the friends list during friend removal, it attempts to navigate back automatically.

## Limitations

- **Android only.** This tool uses ADB and Android's `uiautomator`. There is no iOS support.
- **Swipe coordinates auto-scale** by querying the device's screen size via `adb shell wm size`, so scrolling should work across resolutions. If the query fails, it falls back to 1080x2400.
- **English only.** The text matchers look for English strings: "My Friends", "Best Friends", "Manage Friendship", "Remove Friend", "Cancel", etc. Non-English Snapchat locales will break the flow.
- **Snapchat UI changes.** Any Snapchat update that renames buttons, moves the three-dots icon, or restructures the profile/removal flow will require code updates.
- **One device at a time.** If multiple ADB devices are connected, commands will fail. Disconnect extras or use `adb -s <serial>`.
- **Duplicate display names (friends only).** If two friends have the exact same display name on screen simultaneously, the tool skips them to avoid removing the wrong person. Use `--one` for manual removal.

## Files

| File | Tracked | Purpose |
|------|---------|---------|
| `snap_remover.py` | Yes | Engine + CLI |
| `gui.py` | Yes | Tkinter GUI |
| `friends.txt` | No | Your personal roster (keep/drop per friend) |
| `following.txt` | No | Your personal roster (keep/drop per following) |
| `protected.txt` | No | One-time keeper migration (renamed to .bak after use) |
| `config.json` | No | Calibrated coordinates (three-dots, X button) |

## License

MIT -- see [LICENSE](LICENSE) for details.
