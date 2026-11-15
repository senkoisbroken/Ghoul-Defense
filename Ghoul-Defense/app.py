"""Foreground-only Ghoul Defense perk picker and wave starter."""

from pathlib import Path
import queue
import threading
import time
import tkinter as tk

from controls import WindowControls
from desktop import WindowsDesktop
from detector import Detector
from ocr import TextReader
from movement import Movement
from boss import BossTracker
from ultimate import UltimatePolicy
from automation import ScreenWorker
from components import build_components, configure_logging, build_fingerprint
from remote_logging import ENDPOINT, RemoteLoggingHandler, forget_token, load_token, save_token

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
    logger, handler = configure_logging(ROOT)
    desktop = WindowsDesktop()
    desktop.prepare_dpi()
    root = tk.Tk()
    root.title('Ghoul Defense')
    root.resizable(False, False)
    running, stopping = threading.Event(), threading.Event()
    motion = Movement()
    messages = queue.Queue(maxsize=20)
    status = tk.StringVar(value='Paused — F8 starts')
    remote_handler = None
    remote_checks = queue.SimpleQueue()
    tk.Label(root, text='Ghoul Defense', font=('Segoe UI', 15, 'bold'), pady=10).pack()
    tk.Label(root, text='Damage → attack speed → turret buffs\nOtherwise: first available choice',
             padx=25, pady=5).pack()
    tk.Label(root, text='F8 start / pause').pack()
    tk.Label(root, text='Built-in W/S spam · same 1.2× repeater timing').pack()
    sharing = tk.BooleanVar(value=False)

    def toggle_sharing(reuse_saved=False):
        nonlocal remote_handler
        if not sharing.get():
            if remote_handler is not None:
                logger.removeHandler(remote_handler)
                remote_handler.close()
                remote_handler = None
            try:
                forget_token(ROOT)
            except OSError:
                status.set('Could not clear saved diagnostic settings')
            return
        from tkinter import simpledialog
        token = load_token(ROOT) if reuse_saved else None
        if token is None:
            token = simpledialog.askstring('Share diagnostics',
                'Enter the private diagnostic pairing code from the macro owner.',
                show='*', parent=root)
        if not token:
            sharing.set(False)
            return
        try:
            candidate = RemoteLoggingHandler(ENDPOINT, token)
        except (OSError, ValueError) as error:
            sharing.set(False)
            status.set('Diagnostic sharing setup failed: ' + str(error))
            return

        sharing_button.config(state='disabled')
        status.set('Checking diagnostic connection…')

        def verify_sharing():
            accepted = candidate.verify()
            if stopping.is_set():
                candidate.close()
                return
            remote_checks.put((candidate, token, accepted))

        threading.Thread(target=verify_sharing, name='diagnostics-check', daemon=True).start()

    sharing_button = tk.Checkbutton(root, text='Share diagnostic events with the macro owner',
                                    variable=sharing, command=toggle_sharing)
    sharing_button.pack()
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
        components = build_components(ROOT, reader_factory=TextReader,
                                      detector_factory=Detector, tracker_factory=BossTracker,
                                      ultimate_factory=UltimatePolicy, catalog_factory=Catalog)
        engine = ScreenWorker(ROOT, desktop, motion, running, stopping, report, logger,
                              components, perform=perform, attempt_ultimate=attempt_ultimate,
                              controls_factory=WindowControls)
        with mss.MSS() as capture:
            engine.run(capture)

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
    poll_id = None

    def poll():
        nonlocal previous_keys, poll_id, remote_handler
        while not remote_checks.empty():
            candidate, token, accepted = remote_checks.get_nowait()
            sharing_button.config(state='normal')
            if accepted:
                try:
                    save_token(ROOT, token)
                    remote_handler = candidate
                    logger.addHandler(remote_handler)
                    status.set('Diagnostic sharing connected')
                except OSError:
                    candidate.close()
                    sharing.set(False)
                    status.set('Could not save diagnostic settings')
            else:
                candidate.close()
                sharing.set(False)
                status.set('Diagnostic connection failed. Check the pairing code and internet.')
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
        poll_id = root.after(40, poll)

    def close():
        running.clear()
        stopping.set()
        motion.stop()
        root.destroy()

    root.protocol('WM_DELETE_WINDOW', close)
    if load_token(ROOT):
        sharing.set(True)
        toggle_sharing(reuse_saved=True)
    build = build_fingerprint(ROOT)
    logger.info('Started paused build=%s; screenshot-only detection; no game memory access', build)
    poll()
    try:
        root.mainloop()
    finally:
        running.clear()
        stopping.set()
        motion.stop()
        if poll_id is not None:
            try:
                root.after_cancel(poll_id)
            except tk.TclError:
                pass
        thread.join(timeout=2)
        movement_thread.join(timeout=2)
        if remote_handler is not None:
            logger.removeHandler(remote_handler)
            remote_handler.close()
        logger.removeHandler(handler)
        handler.close()


if __name__ == '__main__':
    main()
