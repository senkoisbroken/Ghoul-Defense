"""Foreground-only Ghoul Defense perk picker and wave starter."""

import json
import hashlib
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
import queue
import threading
import time
import tkinter as tk

from controls import WindowControls, FocusChanged, CaptureUnavailable
from desktop import WindowsDesktop
from ghoul import Detector, combat_visible
from movement import Movement
from boss import BossTracker
from ultimate import UltimatePolicy

ROOT = Path(__file__).resolve().parent


def perform(context, detector, decision):
    """Recheck the current screen after pointer movement, before mouse-down."""
    def verify():
        current = detector.read(context.read())
        if current is None or current.kind != decision.kind:
            return False
        if decision.kind in ('perk', 'relic') and current.cards:
            # Other cards may animate in, but the preferred card and the
            # identity under the pointer must both remain unchanged.
            if current.name != decision.name:
                return False
            x, y = decision.target
            return any(
                name == decision.name
                and cx - 6 <= x <= cx + w + 6 and cy - 6 <= y <= cy + h + 6
                for name, (cx, cy, w, h) in current.cards)
        return bool(current.signature == decision.signature
                    and current.name == decision.name
                    and sum((a - b) ** 2 for a, b in zip(current.target, decision.target)) <= 900)

    if decision.kind == 'replay':
        return bool(verify() and context.press(69))
    return context.click(decision.target, verify=verify)


def attempt_ultimate(context, detector, tracker, policy, boss, now):
    def aligned(observation):
        return bool(observation and observation.target is not None
                    and abs(observation.target[0] - observation.target[1]) <= 12)

    if boss is None:
        policy.reset()
        return False
    key = (context.hwnd, boss.name)
    if not policy.consider(now, key, aligned(boss), boss.hp_fraction, boss.remaining):
        return False
    image = context.read()
    if detector.read(image) is not None:
        policy.reset()
        return False
    current = tracker.read(image)
    if current is None or current.name != boss.name:
        policy.reset()
        return False
    if not policy.consider(time.monotonic(), key, aligned(current),
                           current.hp_fraction, current.remaining):
        return False
    if not detector.ultimate_ready(image, tracker.reader):
        return False
    if context.press(70):
        policy.used(time.monotonic())
        return True
    return False


def main():
    import cv2
    import mss
    from catalog import Catalog

    (ROOT / 'work').mkdir(exist_ok=True)
    cv2.setNumThreads(1)
    logger = logging.getLogger('ghoul')
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(ROOT / 'macro.log', maxBytes=1_000_000,
                                  backupCount=2, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
    logger.addHandler(handler)
    desktop = WindowsDesktop()
    desktop.prepare_dpi()
    root = tk.Tk()
    root.title('Ghoul Defense')
    root.resizable(False, False)
    running, stopping = threading.Event(), threading.Event()
    motion = Movement()
    messages = queue.Queue(maxsize=20)
    status = tk.StringVar(value='Paused — F8 starts')
    tk.Label(root, text='Ghoul Defense', font=('Segoe UI', 15, 'bold'), pady=10).pack()
    tk.Label(root, text='Damage → attack speed → turret buffs\nOtherwise: first available choice',
             padx=25, pady=5).pack()
    tk.Label(root, text='F8 start / pause').pack()
    tk.Label(root, text='Built-in W/S spam · same 1.2× repeater timing').pack()
    tk.Label(root, textvariable=status, wraplength=430, padx=20, pady=12).pack()

    def report(message):
        try:
            messages.put_nowait(message)
        except queue.Full:
            pass

    def start():
        running.set()
        logger.info('running_changed true')
        status.set('Running — focus Roblox')

    def pause():
        running.clear()
        motion.stop()
        logger.info('running_changed false')
        status.set('Paused — F8 starts')

    buttons = tk.Frame(root)
    buttons.pack(pady=(0, 12))
    tk.Button(buttons, text='Start', command=start, width=12).pack(side='left', padx=5)
    tk.Button(buttons, text='Pause', command=pause, width=12).pack(side='left', padx=5)

    def worker():
        detector = Detector()
        boss_tracker = BossTracker()
        ultimate = UltimatePolicy()
        catalog = Catalog(ROOT / 'catalog')
        last = None
        attempted = 0
        previous_status = None
        error_at = 0
        last_boss = None
        last_movement_gate = None
        boss_logged_at = 0
        with mss.MSS() as capture:
            while not stopping.is_set():
                if not running.wait(.1):
                    last = None
                    continue
                if stopping.is_set():
                    break
                try:
                    hwnd = desktop.roblox_window()
                    if not hwnd:
                        motion.stop()
                        ultimate.reset()
                        boss_tracker.reset()
                        message = 'Waiting for Roblox in the foreground'
                        last = None
                    else:
                        bounds = desktop.client_rect(hwnd)
                        context = WindowControls(desktop, capture, hwnd, bounds,
                                                 lambda: running.is_set() and not stopping.is_set())
                        image = context.read()
                        decision = detector.read(image)
                        if decision is None:
                            combat = combat_visible(image)
                            boss = boss_tracker.read(image) if combat else None
                            target = boss.target if boss is not None else None
                            movement_gate = (combat, boss is not None, target is not None)
                            if movement_gate != last_movement_gate:
                                logger.info('movement_gate combat=%s boss=%s target=%s',
                                            *movement_gate)
                                last_movement_gate = movement_gate
                            motion.observe(hwnd, combat and (boss is None or target is not None),
                                           time.monotonic(), boss=target)
                            if attempt_ultimate(context, detector, boss_tracker, ultimate,
                                                boss, time.monotonic()):
                                logger.info('ultimate_f_sent window=%s boss=%s', hwnd, boss.name)
                            if combat and time.monotonic() - boss_logged_at > 3:
                                logger.info('boss_scan %s', json.dumps(boss_tracker.last,
                                                                       ensure_ascii=True))
                                boss_logged_at = time.monotonic()
                            message = ('Waiting for the combat HUD — movement stopped' if not combat
                                       else 'Following ' + boss.name + ' lane' if target is not None
                                       else 'Boss detected — checking its lane' if boss is not None
                                       else 'W/S patrol — watching for choices and Start Wave')
                            mode = ((boss.name, boss.remaining,
                                     tuple(round(y / 12) for y in target) if target else None)
                                    if boss is not None else None)
                            if mode != last_boss:
                                logger.info('boss_tracking %s', json.dumps({
                                    'name': boss.name if boss else None,
                                    'remaining': boss.remaining if boss else None,
                                    'target': target, 'window': int(hwnd)}))
                                if boss is not None and target is None:
                                    path = ROOT / 'work/boss_lane_unclear.png'
                                    cv2.imwrite(str(path), image)
                                    logger.info('boss_lane_capture %s', path)
                                last_boss = mode
                            last = None
                        else:
                            motion.stop()
                            last_movement_gate = None
                            ultimate.reset()
                            boss_tracker.reset()
                            for path in catalog.save(image, decision):
                                logger.info('catalog_saved %s', path)
                            identity = (hwnd, decision.signature)
                            now = time.monotonic()
                            message = ('Playing again' if decision.kind == 'replay'
                                       else 'Starting next wave' if decision.kind == 'wave'
                                       else 'Choosing ' + decision.name)
                            if identity != last or now - attempted >= 1.5:
                                accepted = perform(context, detector, decision)
                                last, attempted = identity, time.monotonic()
                                logger.info('action %s', json.dumps({
                                    'kind': decision.kind, 'chosen': decision.name,
                                    'offered': decision.names, 'target': decision.target,
                                    'accepted': bool(accepted), 'window': int(hwnd)}))
                                if not accepted:
                                    message = 'Screen changed — checking again'
                    if message != previous_status:
                        report(message)
                        previous_status = message
                except (FocusChanged, CaptureUnavailable):
                    motion.stop()
                    ultimate.reset()
                    boss_tracker.reset()
                    last = None
                except Exception as exc:
                    motion.stop()
                    ultimate.reset()
                    report('Error: ' + str(exc))
                    now = time.monotonic()
                    if now - error_at > 10:
                        logger.exception('Worker error')
                        error_at = now
                    stopping.wait(.5)
                stopping.wait(.12)

    def movement_worker():
        try:
            while not stopping.is_set():
                motion.tick(time.monotonic(), running.is_set())
                stopping.wait(.005)
        except Exception as exc:
            running.clear()
            report('Movement stopped: ' + str(exc))
            logger.exception('Movement error')
        finally:
            motion.stop()

    movement_thread = threading.Thread(target=movement_worker,
                                       name='ghoul-movement-worker', daemon=True)
    movement_thread.start()
    thread = threading.Thread(target=worker, name='ghoul-screen-worker', daemon=True)
    thread.start()
    previous_keys = set()

    def poll():
        nonlocal previous_keys
        pressed = {key for key in (0x77,) if desktop.down(key)}
        new = pressed - previous_keys
        previous_keys = pressed
        if 0x77 in new:
            if running.is_set():
                pause()
            else:
                start()
        while True:
            try:
                text = messages.get_nowait()
                if running.is_set():
                    status.set(text)
            except queue.Empty:
                break
        root.after(40, poll)

    def close():
        running.clear()
        stopping.set()
        motion.stop()
        root.destroy()

    root.protocol('WM_DELETE_WINDOW', close)
    build = hashlib.sha256(b''.join((ROOT / name).read_bytes() for name in
        ('app.py', 'boss.py', 'ghoul.py', 'movement.py', 'ultimate.py'))).hexdigest()[:12]
    logger.info('Started paused build=%s; screenshot-only detection; no game memory access', build)
    poll()
    try:
        root.mainloop()
    finally:
        running.clear()
        stopping.set()
        motion.stop()
        thread.join(timeout=2)
        movement_thread.join(timeout=2)
        handler.close()


if __name__ == '__main__':
    main()
