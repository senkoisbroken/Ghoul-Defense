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
from diagnostic_upload import snapshot_lines, send_snapshot

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
    upload_results = queue.SimpleQueue()
    sharing_status = tk.StringVar(value='Diagnostic log: not sent')
    preview_window = None
    uploading = False
    tk.Label(root, text='Ghoul Defense', font=('Segoe UI', 15, 'bold'), pady=10).pack()
    tk.Label(root, text='Twin Scythes → damage → attack speed → turret buffs\nOtherwise: first available choice',
             padx=25, pady=5).pack()
    tk.Label(root, text='F8 start / pause').pack()
    tk.Label(root, text='Built-in W/S spam · same 1.2× repeater timing').pack()
    def prepare_upload():
        nonlocal preview_window
        if uploading:
            sharing_status.set('Diagnostic log: an upload is already running.')
            return
        if preview_window is not None:
            try:
                still_open = preview_window.winfo_exists()
            except tk.TclError:
                still_open = False
            if still_open:
                preview_window.lift()
                preview_window.focus_set()
                return
            preview_window = None
        from tkinter import messagebox, scrolledtext
        try:
            lines = snapshot_lines(ROOT)
        except (OSError, ValueError) as exc:
            messagebox.showerror('Diagnostic log', str(exc), parent=root)
            return
        preview = tk.Toplevel(root)
        preview_window = preview
        preview.title('Review diagnostic log before sending')
        tk.Label(preview, text='Review this recent, partially sanitized log. It will be sent to the macro owner and retained on AWS for 14 days.', wraplength=600).pack(padx=10, pady=8)
        text = scrolledtext.ScrolledText(preview, width=90, height=24, wrap='word')
        text.pack(padx=10, pady=5)
        text.insert('1.0', ''.join(lines))
        text.config(state='disabled')

        def close_preview():
            nonlocal preview_window
            if preview_window is preview:
                preview_window = None
            preview.destroy()

        def send():
            nonlocal preview_window, uploading
            if uploading:
                return
            uploading = True
            close_preview()
            upload_button.config(state='disabled')
            sharing_status.set('Diagnostic log: sending... Keep this window open.')

            def progress(message):
                upload_results.put(('progress', message))

            def run_upload():
                try:
                    result = send_snapshot(ROOT, None, lines,
                                           progress=progress,
                                           cancelled=stopping.is_set)
                except Exception:
                    result = (False, 'Upload failed unexpectedly. Please try again.')
                upload_results.put(('result', result))

            threading.Thread(target=run_upload, name='diagnostic-upload', daemon=True).start()

        preview.protocol('WM_DELETE_WINDOW', close_preview)
        tk.Button(preview, text='Send this log', command=send).pack(pady=8)
    upload_button = tk.Button(root, text='Send diagnostic logs...', command=prepare_upload)
    upload_button.pack()
    tk.Label(root, textvariable=sharing_status, wraplength=430).pack()
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
        nonlocal previous_keys, poll_id, uploading
        while not upload_results.empty():
            kind, payload = upload_results.get_nowait()
            if kind == 'progress':
                sharing_status.set(payload)
                continue
            accepted, detail = payload
            uploading = False
            upload_button.config(state='normal')
            sharing_status.set(detail)
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
        logger.removeHandler(handler)
        handler.close()


if __name__ == '__main__':
    main()
