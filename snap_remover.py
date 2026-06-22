#!/usr/bin/env python3
"""
Snapchat friend remover -- engine.

CLI:
  python snap_remover.py --scan | --list | --run | --one "Name" | --remove [N] [--delay MIN MAX]

The three-dots menu coordinate is per-device and lives in config.json (set it with
the GUI's Calibrate, or --calibrate X Y). The confirm-button offset self-scales from
the Cancel button's height, so it needs no calibration.

Keeper list: protected.txt (one name per line) -- NEVER removed.
"""

import subprocess, sys, re, time, random, argparse, os, json
from collections import Counter
from dataclasses import dataclass
import xml.etree.ElementTree as ET

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ADB = "adb"
ROSTER_FILE = "friends.txt"
FOLLOWING_FILE = "following.txt"
PROTECTED_FILE = "protected.txt"
CONFIG_FILE = "config.json"
SNAP_PKG = "com.snapchat.android"

THREE_DOTS_XY = (1330, 252)          # default; overridden by config.json (calibrate)
CONFIRM_OFFSET_Y = 185               # fallback only; real offset comes from Cancel's height
UNFOLLOW_X = None                    # X coordinate of the X buttons in Following edit mode

NON_NAMES = {
    "best friends", "my friends", "add friends", "find friends", "view more",
    "quick add", "recents", "search", "all", "added me", "my contacts",
    "following", "done", "edit", "manage accounts followed and notifications.",
}

MIN_DELAY, MAX_DELAY = 3.0, 8.0
DEFAULT_PER_RUN = 60


def load_config():
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_config(cfg):
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def set_three_dots(xy):
    global THREE_DOTS_XY
    THREE_DOTS_XY = (int(xy[0]), int(xy[1]))
    cfg = load_config()
    cfg["three_dots"] = [THREE_DOTS_XY[0], THREE_DOTS_XY[1]]
    save_config(cfg)


def set_unfollow_x(x):
    global UNFOLLOW_X
    UNFOLLOW_X = int(x)
    cfg = load_config()
    cfg["unfollow_x"] = UNFOLLOW_X
    save_config(cfg)


_cfg = load_config()
if _cfg.get("three_dots"):
    THREE_DOTS_XY = (int(_cfg["three_dots"][0]), int(_cfg["three_dots"][1]))
if _cfg.get("unfollow_x"):
    UNFOLLOW_X = int(_cfg["unfollow_x"])




@dataclass
class Node:
    text: str
    desc: str
    rid: str
    clickable: bool
    center: tuple
    height: int = 0
    package: str = ""


def sh(*args, binary=False, timeout=15):
    try:
        return subprocess.run([ADB, *args], capture_output=True,
                              text=not binary, timeout=timeout)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return subprocess.CompletedProcess(args, -1, b"" if binary else "",
                                           b"" if binary else "")


def device_connected():
    return sh("get-state").stdout.strip() == "device"


def screencap():
    return sh("exec-out", "screencap", "-p", binary=True).stdout


def screen_size():
    out = sh("shell", "wm", "size").stdout
    m = re.search(r"(\d+)x(\d+)", out)
    return (int(m.group(1)), int(m.group(2))) if m else (1080, 2400)


_SCREEN = None


def get_screen():
    global _SCREEN
    if _SCREEN is None:
        _SCREEN = screen_size()
    return _SCREEN


def _bounds(b):
    nums = re.findall(r"\d+", b)
    if len(nums) != 4:
        return None, 0
    x1, y1, x2, y2 = map(int, nums)
    return ((x1 + x2) // 2, (y1 + y2) // 2), (y2 - y1)


def dump():
    sh("shell", "uiautomator", "dump")
    raw = sh("exec-out", "cat", "/sdcard/window_dump.xml", binary=True).stdout
    if not raw:
        return []
    try:
        root = ET.fromstring(raw.decode("utf-8", "replace"))
    except ET.ParseError:
        return []
    out = []
    for n in root.iter("node"):
        a = n.attrib
        c, h = _bounds(a.get("bounds", ""))
        out.append(Node(
            text=a.get("text", ""), desc=a.get("content-desc", ""),
            rid=a.get("resource-id", ""), clickable=a.get("clickable", "") == "true",
            center=c, height=h, package=a.get("package", ""),
        ))
    return out


def find(ns, *, text=None, contains=None, desc=None, clickable=None):
    for n in ns:
        if text is not None and n.text.lower() != text.lower():
            continue
        if contains is not None and contains.lower() not in n.text.lower():
            continue
        if desc is not None and desc.lower() not in n.desc.lower():
            continue
        if clickable is not None and n.clickable != clickable:
            continue
        if n.center is None:
            continue
        return n
    return None


def wait_for(finder, timeout=6.0, interval=0.35):
    end = time.time() + timeout
    while time.time() < end:
        r = finder(dump())
        if r:
            return r
        time.sleep(interval)
    return None


def on_profile(ns):
    return any("profile_identity_section" in (n.rid or "") for n in ns)


def at_friends_list(ns):
    if (find(ns, contains="My Friends") or find(ns, contains="Best Friends")
            or find(ns, contains="Add Friends")):
        return True
    for n in ns:
        t = n.text or ""
        if "A\nB\nC\nD" in t or "W\nX\nY\nZ" in t:
            return True
    return False


def in_snapchat(ns):
    return any(n.package == SNAP_PKG for n in ns)


def tap(n):
    x, y = n.center
    sh("shell", "input", "tap", str(x), str(y))


def tap_xy(x, y):
    sh("shell", "input", "tap", str(int(x)), str(int(y)))


def back():
    sh("shell", "input", "keyevent", "4")


def swipe_up():
    w, h = get_screen()
    sh("shell", "input", "swipe", str(w // 2), str(int(h * 0.55)),
       str(w // 2), str(int(h * 0.20)), "250")


def set_dnd(on):
    try:
        sh("shell", "cmd", "notification", "set_dnd", "on" if on else "off")
        sh("shell", "settings", "put", "global", "zen_mode", "1" if on else "0")
    except Exception:
        pass


def stay_awake(on):
    try:
        sh("shell", "svc", "power", "stayon", "true" if on else "false")
    except Exception:
        pass


def return_to_list(max_backs=8):
    for _ in range(max_backs):
        if wait_for(at_friends_list, timeout=1.5):
            return True
        ns = dump()
        if ns and not in_snapchat(ns):
            return False
        back()
        time.sleep(0.5)
    return wait_for(at_friends_list, timeout=1.0)


def looks_like_name(name):
    n = name.strip()
    if not n or n.lower() in NON_NAMES:
        return False
    if "\n" in n or not any(c.isalpha() for c in n):
        return False
    return len(n) > 1


def visible_names(ns):
    return sorted(n.text.strip().lower() for n in ns if looks_like_name(n.text))


def load_roster():
    roster = {}
    if not os.path.exists(ROSTER_FILE):
        return roster
    with open(ROSTER_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            action, name = parts[0].lower(), parts[1].strip()
            if action in ("keep", "drop"):
                roster[name.lower()] = (action, name)
    return roster


def write_roster(roster):
    names = sorted(roster.values(), key=lambda v: v[1].lower())
    with open(ROSTER_FILE, "w", encoding="utf-8") as f:
        f.write("# Snapchat roster. First word per line: keep = stay, drop = remove.\n\n")
        for action, name in names:
            f.write(f"{action}  {name}\n")



def should_remove(name, roster=None):
    if roster is None:
        roster = load_roster()
    entry = roster.get(name.strip().lower())
    return bool(entry and entry[0] == "drop")



def _migrate_protected_once():
    """One-time: fold any old protected.txt into friends.txt as keep, then retire it."""
    if not (os.path.exists(PROTECTED_FILE) and os.path.exists(ROSTER_FILE)):
        return
    names = []
    with open(PROTECTED_FILE, encoding="utf-8") as f:
        for line in f:
            t = line.strip()
            if t and not t.startswith("#"):
                names.append(t)
    roster = load_roster()
    changed = False
    for n in names:
        k = n.lower()
        if k in roster and roster[k][0] != "keep":
            roster[k] = ("keep", roster[k][1]); changed = True
        elif k not in roster:
            roster[k] = ("keep", n); changed = True
    if changed:
        write_roster(roster)
    try:
        os.replace(PROTECTED_FILE, PROTECTED_FILE + ".bak")
    except OSError:
        pass


_migrate_protected_once()


def scan_roster():
    """Scroll the whole list (no taps) and write friends.txt; return the roster dict."""
    existing = load_roster()
    found = dict(existing)
    seen, stable = set(), 0
    while stable < 2:
        new = 0
        for n in dump():
            if looks_like_name(n.text) and n.text not in seen:
                seen.add(n.text)
                if n.text.lower() not in found:
                    found[n.text.lower()] = ("keep", n.text)
                new += 1
        stable = stable + 1 if new == 0 else 0
        swipe_up()
        time.sleep(0.7)
    write_roster(found)
    return found


# ---------------------------------------------------------------------------
# Following list: roster, detection, scan, unfollow
# ---------------------------------------------------------------------------
def load_following():
    roster = {}
    if not os.path.exists(FOLLOWING_FILE):
        return roster
    with open(FOLLOWING_FILE, encoding="utf-8") as f:
        for line in f:
            line = line.rstrip("\n")
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            parts = line.split(None, 1)
            if len(parts) != 2:
                continue
            action, name = parts[0].lower(), parts[1].strip()
            if action in ("keep", "drop"):
                roster[name.lower()] = (action, name)
    return roster


def write_following(roster):
    names = sorted(roster.values(), key=lambda v: v[1].lower())
    with open(FOLLOWING_FILE, "w", encoding="utf-8") as f:
        f.write("# Following roster. keep = stay, drop = unfollow.\n\n")
        for action, name in names:
            f.write(f"{action}  {name}\n")


def at_following_list(ns):
    return bool(find(ns, text="Following") and
                (find(ns, text="Edit", clickable=True) or find(ns, text="Done", clickable=True)))


def in_following_edit_mode(ns):
    return bool(find(ns, text="Done", clickable=True))


def enter_edit_mode(log=print):
    btn = wait_for(lambda ns: find(ns, text="Edit", clickable=True), timeout=5)
    if not btn:
        log("  couldn't find Edit button")
        return False
    tap(btn)
    if not wait_for(lambda ns: find(ns, text="Done", clickable=True), timeout=5):
        log("  Edit mode didn't activate")
        return False
    return True


def exit_edit_mode(log=print):
    btn = wait_for(lambda ns: find(ns, text="Done", clickable=True), timeout=3)
    if btn:
        tap(btn)
    time.sleep(0.5)


def scan_following(log=print):
    existing = load_following()
    found = dict(existing)
    seen, stable = set(), 0
    while stable < 2:
        new = 0
        for n in dump():
            if looks_like_name(n.text) and n.text not in seen:
                seen.add(n.text)
                if n.text.lower() not in found:
                    found[n.text.lower()] = ("keep", n.text)
                new += 1
        stable = stable + 1 if new == 0 else 0
        swipe_up()
        time.sleep(0.7)
    write_following(found)
    return found


def _tap_confirm_dialog(log=print):
    """Handle the confirm dialog (Yes/Cancel) used by the unfollow flow."""
    dialog = wait_for(lambda ns: find(ns, text="Cancel") or find(ns, text="Yes", clickable=True),
                      timeout=5)
    if not dialog:
        log("  confirm dialog never appeared; stopping to be safe")
        return False
    ns = dump()
    btn = find(ns, text="Yes", clickable=True) or find(ns, text="Remove", clickable=True)
    if btn:
        tap(btn)
        return True
    cancel = find(ns, text="Cancel")
    if not cancel:
        log("  confirm dialog not found; skipping")
        return False
    cx, cy = cancel.center
    off = cancel.height if cancel.height and cancel.height > 60 else CONFIRM_OFFSET_Y
    tap_xy(cx, cy - off)
    return True


def unfollow_current(name_node, log=print):
    if UNFOLLOW_X is None:
        log("  X button not calibrated. Run calibrate-x first.")
        return False
    # Safety: verify we're still on the Following list before tapping anything
    ns = dump()
    if not at_following_list(ns):
        log("  not on Following list anymore; stopping to avoid mis-taps")
        return False
    if not in_snapchat(ns):
        log("  left Snapchat; stopping to avoid mis-taps")
        return False
    tap_xy(UNFOLLOW_X, name_node.center[1])
    time.sleep(0.4)
    # Verify the confirm dialog appeared (not some other screen)
    ns = dump()
    if not (find(ns, text="Cancel") or find(ns, text="Yes", clickable=True)
            or find(ns, contains="Remove?")):
        log("  X tap didn't open confirm dialog; stopping to be safe")
        return False
    if not _tap_confirm_dialog(log):
        return False
    time.sleep(0.4)
    return True


def find_next_unfollow_target(drops, done, log=print):
    last = None
    for _ in range(300):
        ns = dump()
        if not at_following_list(ns):
            return None
        for n in ns:
            if not looks_like_name(n.text):
                continue
            key = n.text.strip().lower()
            if key in drops and key not in done:
                return n
        names = visible_names(ns)
        if names == last:
            return None
        last = names
        swipe_up()
        time.sleep(0.5)
    return None


def run_unfollow_batch(cap, dmin, dmax, log=print, should_stop=lambda: False, on_progress=None):
    roster = load_following()
    drops = {k: v[1] for k, v in roster.items() if v[0] == "drop"}
    if not drops:
        log("Nobody is marked 'drop' in following.txt.")
        return 0, []
    if UNFOLLOW_X is None:
        log("X button not calibrated. Calibrate first.")
        return 0, list(drops.values())
    set_dnd(True)
    stay_awake(True)
    removed, done, succeeded, blank = 0, set(), set(), 0
    try:
        ns = dump()
        if not at_following_list(ns):
            log("Not on the Following list. Navigate there first.")
            return 0, list(drops.values())
        if not in_following_edit_mode(ns):
            log("Entering Edit mode...")
            if not enter_edit_mode(log):
                return 0, list(drops.values())
        while removed < cap and len(done) < len(drops) and not should_stop():
            if not dump():
                blank += 1
                log("  screen off/locked -- pausing 5s.")
                time.sleep(5)
                if blank >= 2:
                    log("Still no screen. Stopping.")
                    break
                continue
            blank = 0
            ns = dump()
            if not in_snapchat(ns):
                log("Left Snapchat (notification?). Stopping to avoid mis-taps.")
                break
            if not in_following_edit_mode(ns):
                if not at_following_list(ns):
                    log("Not on Following list anymore. Stopping.")
                    break
                log("  lost edit mode, re-entering...")
                if not enter_edit_mode(log):
                    break
            target = find_next_unfollow_target(drops, done, log)
            if target is None:
                break
            name = target.text
            done.add(name.strip().lower())
            log(f"[{removed + 1}/{cap}] unfollowing {name} ...")
            if unfollow_current(target, log):
                removed += 1
                succeeded.add(name.strip().lower())
                log(f"    done ({removed})")
                if on_progress:
                    on_progress(removed, cap)
                if should_stop():
                    break
                time.sleep(random.uniform(dmin, dmax))
        exit_edit_mode(log)
    finally:
        set_dnd(False)
        stay_awake(False)
    remaining = [drops[k] for k in drops if k not in succeeded]
    return removed, remaining


def confirm(action):
    r = input(f"  -> {action}   [Enter = do it / s = skip / q = quit]: ").strip().lower()
    if r == "q":
        sys.exit("Quit by user.")
    return r != "s"


def dump_screen(ns, label):
    print(f"\n--- COULDN'T FIND IT ({label}). Screen contents: ---")
    for n in ns:
        if n.text or n.desc:
            flag = " [clickable]" if n.clickable else ""
            print(f"  text={n.text!r}  desc={n.desc!r}  id={n.rid}  @{n.center}{flag}")
    print("--- paste this to me to fix the matcher ---\n")


def remove_current(name, interactive=True, log=print):
    header = wait_for(lambda ns: find(ns, text=name, clickable=True) or find(ns, text=name),
                      timeout=5)
    if not header:
        log(f"  couldn't open profile for {name}")
        return False
    if interactive and not confirm(f"Tap 'name header (open profile)' @{header.center}"):
        return False
    tap(header)

    if not wait_for(on_profile, timeout=6):
        log("  profile didn't open (notification / slow load?)")
        return False

    tdx, tdy = THREE_DOTS_XY
    if interactive and not confirm(f"Tap three-dots menu @ ({tdx},{tdy})"):
        return False
    menu = None
    for _ in range(2):
        if not wait_for(on_profile, timeout=3):
            time.sleep(0.8)
        tap_xy(tdx, tdy)
        menu = wait_for(lambda ns: find(ns, contains="Manage Friendship"), timeout=5)
        if menu:
            break
    if not menu:
        log("  three-dots missed (calibrate?); skipping")
        return False
    if interactive and not confirm(f"Tap 'Manage Friendship' @{menu.center}"):
        return False
    tap(menu)

    rf = wait_for(lambda ns: find(ns, contains="Remove Friend"), timeout=5)
    if not rf:
        log("  no 'Remove Friend' (subscription / public profile?); skipping")
        return False
    if interactive and not confirm(f"Tap 'Remove Friend' @{rf.center}"):
        return False
    tap(rf)

    wait_for(lambda ns: find(ns, text="Cancel") or find(ns, text="Remove", clickable=True),
             timeout=5)
    ns = dump()
    btn = find(ns, text="Remove", clickable=True) or find(ns, text="Yes", clickable=True)
    if btn:
        if interactive and not confirm(f"Tap confirm '{btn.text}' @{btn.center}"):
            return False
        tap(btn)
    else:
        cancel = find(ns, text="Cancel")
        if not cancel:
            log("  confirm dialog not found; skipping")
            return False
        cx, cy = cancel.center
        off = cancel.height if cancel.height and cancel.height > 60 else CONFIRM_OFFSET_Y
        if interactive and not confirm(f"Tap confirm (above Cancel) @ ({cx},{cy - off})"):
            return False
        tap_xy(cx, cy - off)
    time.sleep(0.6)
    return_to_list()
    return True


def find_next_target(drops, done, log=print):
    if not at_friends_list(dump()) and not return_to_list():
        return None
    last = None
    for _ in range(300):
        ns = dump()
        counts = Counter(n.text.strip().lower() for n in ns if looks_like_name(n.text))
        for n in ns:
            if not looks_like_name(n.text):
                continue
            key = n.text.strip().lower()
            if key in drops and key not in done:
                if counts[key] == 1:
                    return n
                done.add(key)        # ambiguous duplicate -> skip for manual handling
                log(f"  ! '{drops[key]}' is on screen more than once; skipping (remove by hand).")
        names = visible_names(ns)
        if names == last:
            return None
        last = names
        swipe_up()
        time.sleep(0.5)
    return None


def run_batch(cap, dmin, dmax, log=print, should_stop=lambda: False, on_progress=None):
    """Headless batch usable by CLI and GUI. Returns (removed, remaining_names)."""
    roster = load_roster()
    drops = {k: v[1] for k, v in roster.items() if v[0] == "drop"}
    if not drops:
        log("Nobody is marked 'drop'.")
        return 0, []
    set_dnd(True)
    stay_awake(True)
    removed, done, succeeded, blank = 0, set(), set(), 0
    try:
        while removed < cap and len(done) < len(drops) and not should_stop():
            if not dump():
                blank += 1
                log("  screen off/locked -- pausing 5s.")
                time.sleep(5)
                if blank >= 2:
                    log("Still no screen. Stopping.")
                    break
                continue
            blank = 0
            target = find_next_target(drops, done, log)
            if target is None:
                break
            name = target.text
            done.add(name.strip().lower())
            log(f"[{removed + 1}/{cap}] removing {name} ...")
            tap(target)
            time.sleep(0.5)
            if remove_current(name, interactive=False, log=log):
                removed += 1
                succeeded.add(name.strip().lower())
                log(f"    done ({removed})")
                if on_progress:
                    on_progress(removed, cap)
                if should_stop():
                    break
                time.sleep(random.uniform(dmin, dmax))
            else:
                return_to_list()
    finally:
        set_dnd(False)
        stay_awake(False)
    remaining = [drops[k] for k in drops if k not in succeeded]
    return removed, remaining


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _cli_list():
    ns = dump()
    if not ns:
        print("Empty dump.")
        return
    roster = load_roster()
    for n in ns:
        if not (n.text or n.desc):
            continue
        d = ""
        if looks_like_name(n.text):
            d = "  REMOVE" if should_remove(n.text, roster) else "  keep"
        clk = " [clickable]" if n.clickable else ""
        print(f"  {n.text!r:30} desc={n.desc!r:18} @{str(n.center):14}{clk}{d}")


def _cli_run():
    roster = load_roster()
    seen, keep, rem, stable = set(), [], [], 0
    while stable < 2:
        new = 0
        for n in dump():
            if looks_like_name(n.text) and n.text not in seen:
                seen.add(n.text)
                new += 1
                (rem if should_remove(n.text, roster) else keep).append(n.text)
        stable = stable + 1 if new == 0 else 0
        swipe_up()
        time.sleep(0.7)
    print(f"Found {len(seen)}. KEEP {len(keep)}.  WOULD REMOVE ({len(rem)}):")
    for name in sorted(rem):
        print(f"  - {name}")
    print("Nothing was touched.")


def _cli_one(name):
    ns = dump()
    target = find(ns, text=name) or find(ns, contains=name)
    if not target:
        print(f"Couldn't find '{name}' on screen.")
        return
    if not confirm(f"Open chat for '{name}'"):
        return
    tap(target)
    time.sleep(1.0)
    print("Done." if remove_current(name, interactive=True) else "Stopped.")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--scan", action="store_true")
    g.add_argument("--list", action="store_true")
    g.add_argument("--run", action="store_true")
    g.add_argument("--one", metavar="NAME")
    g.add_argument("--remove", nargs="?", const=DEFAULT_PER_RUN, type=int, metavar="N")
    g.add_argument("--calibrate", nargs=2, type=int, metavar=("X", "Y"),
                   help="save the three-dots coordinate to config.json")
    g.add_argument("--scan-following", action="store_true",
                   help="scan the Following list and build following.txt")
    g.add_argument("--unfollow", nargs="?", const=DEFAULT_PER_RUN, type=int, metavar="N",
                   help="batch unfollow up to N accounts")
    g.add_argument("--calibrate-x", type=int, metavar="X",
                   help="save the X-button coordinate for unfollow")
    p.add_argument("--delay", nargs=2, type=float, metavar=("MIN", "MAX"))
    args = p.parse_args()
    if args.delay:
        MIN_DELAY, MAX_DELAY = args.delay

    if args.calibrate:
        set_three_dots(args.calibrate)
        print(f"Saved three-dots = {THREE_DOTS_XY} to {CONFIG_FILE}")
        sys.exit(0)

    if args.calibrate_x is not None:
        set_unfollow_x(args.calibrate_x)
        print(f"Saved unfollow X = {UNFOLLOW_X} to {CONFIG_FILE}")
        sys.exit(0)

    if not device_connected():
        sys.exit("No device. Run `adb devices`.")

    if args.scan:
        r = scan_roster()
        print(f"Wrote {ROSTER_FILE}: {len(r)} friends.")
    elif args.list:
        _cli_list()
    elif args.run:
        _cli_run()
    elif args.one:
        _cli_one(args.one)
    elif args.remove is not None:
        print(f"Removing up to {args.remove} with {MIN_DELAY}-{MAX_DELAY}s gaps.")
        if input("Type REMOVE to proceed: ").strip() == "REMOVE":
            removed, remaining = run_batch(args.remove, MIN_DELAY, MAX_DELAY)
            print(f"Removed {removed}. {len(remaining)} still pending.")
        else:
            print("Aborted.")
    elif args.scan_following:
        r = scan_following()
        print(f"Wrote {FOLLOWING_FILE}: {len(r)} accounts.")
    elif args.unfollow is not None:
        print(f"Unfollowing up to {args.unfollow} with {MIN_DELAY}-{MAX_DELAY}s gaps.")
        if input("Type REMOVE to proceed: ").strip() == "REMOVE":
            removed, remaining = run_unfollow_batch(args.unfollow, MIN_DELAY, MAX_DELAY)
            print(f"Unfollowed {removed}. {len(remaining)} still pending.")
        else:
            print("Aborted.")
