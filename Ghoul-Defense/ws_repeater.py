"""Repeat the user's observed W/S taps using foreground Windows input only."""

import time
import tkinter as tk

import win_input
from win_input import KEYBDINPUT as KeyInput, MOUSEINPUT as MouseInput
from win_input import INPUT_UNION as InputData, INPUT as Input

__all__ = ['KeyInput', 'MouseInput', 'InputData', 'Input', 'Keyboard', 'Playback',
           'OBSERVED', 'SPEED', 'SEQUENCE', 'main']


# Complete observed cycle, from the first W down to the next cycle's W down.
OBSERVED = (
    (0.081, "W"), (0.153, None), (0.241, "W"), (0.335, None),
    (0.428, "W"), (0.503, None), (0.608, "W"), (0.680, None),
    (0.775, "W"), (0.852, None), (0.948, "W"), (1.040, None),
    (1.150, "S"), (1.235, None), (1.317, "S"), (1.403, None),
    (1.474, "S"), (1.556, None), (1.647, "S"), (1.717, None),
    (1.809, "S"), (1.890, None), (1.971, "S"), (2.081, None),
)
SPEED = 1.2
SEQUENCE = tuple(
    (key, ((OBSERVED[i + 1][0] if i + 1 < len(OBSERVED) else 2.173) - at) / SPEED)
    for i, (at, key) in enumerate(OBSERVED)
)


class Keyboard:
    def __init__(self):
        self.u = win_input.USER32

    def foreground(self):
        return win_input.foreground_roblox(user32=self.u)

    def down(self, vk):
        return win_input.key_down(vk, user32=self.u)

    def key(self, key, down):
        scan = win_input.SCAN_CODES[{"W": 87, "S": 83}[key]]
        try:
            win_input.send_key_scan(scan, down, user32=self.u)
        except OSError:
            raise OSError("Windows rejected the keyboard input") from None


class Playback:
    def __init__(self, keyboard):
        self.keyboard = keyboard
        self.running = False
        self.held = None
        self.window = None
        self.index = 0
        self.due = 0

    def release(self):
        if self.held:
            key = self.held
            self.keyboard.key(key, False)
            self.held = None

    def stop(self):
        self.running = False
        self.release()
        self.window = None
        self.index = 0

    def start(self):
        self.stop()
        self.running = True
        self.due = 0

    def tick(self, now):
        if not self.running:
            return "Stopped — F7 starts"
        window = self.keyboard.foreground()
        if not window:
            self.release()
            self.window = None
            self.index = 0
            self.due = 0
            return "Waiting for Roblox"
        if self.window != window:
            self.release()
            self.window = window
            self.index = 0
            self.due = 0
        if now >= self.due:
            self.release()
            key, duration = SEQUENCE[self.index]
            if key:
                self.keyboard.key(key, True)
                self.held = key
            # Never burst overdue inputs after a delayed timer.
            self.due = now + duration
            self.index = (self.index + 1) % len(SEQUENCE)
        return "Running — F8 stops"


def main():
    keyboard = Keyboard()
    playback = Playback(keyboard)
    root = tk.Tk()
    root.title("W / S Repeater")
    root.resizable(False, False)
    status = tk.StringVar(value="Stopped — F7 starts")
    tk.Label(root, text="Six W taps → six S taps", padx=24, pady=12).pack()
    tk.Label(root, text="F7 start · F8 stop · F9 quit").pack()
    tk.Label(root, textvariable=status, padx=20, pady=12).pack()
    previous = set()

    def close():
        try:
            playback.stop()
        finally:
            root.destroy()

    def poll():
        nonlocal previous
        try:
            pressed = {key for key in (0x76, 0x77, 0x78)
                       if keyboard.down(key)}
            new = pressed - previous
            previous = pressed
            if 0x78 in new:
                close()
                return
            if 0x77 in new:
                playback.stop()
            elif 0x76 in new:
                playback.start()
            status.set(playback.tick(time.monotonic()))
        except Exception as exc:
            playback.running = False
            try:
                playback.release()
            except OSError:
                pass
            status.set(str(exc))
        root.after(5, poll)

    root.protocol("WM_DELETE_WINDOW", close)
    try:
        poll()
        root.mainloop()
    finally:
        playback.stop()


if __name__ == "__main__":
    main()
