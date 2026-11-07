"""Repeat the user's observed W/S taps using foreground Windows input only."""

import ctypes
from ctypes import wintypes as w
import time
import tkinter as tk


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


class KeyInput(ctypes.Structure):
    _fields_ = [("vk", w.WORD), ("scan", w.WORD), ("flags", w.DWORD),
                ("time", w.DWORD), ("extra", ctypes.c_size_t)]


class MouseInput(ctypes.Structure):
    _fields_ = [("dx", w.LONG), ("dy", w.LONG), ("data", w.DWORD),
                ("flags", w.DWORD), ("time", w.DWORD),
                ("extra", ctypes.c_size_t)]


class InputData(ctypes.Union):
    _fields_ = [("ki", KeyInput), ("mi", MouseInput)]


class Input(ctypes.Structure):
    _fields_ = [("type", w.DWORD), ("data", InputData)]


class Keyboard:
    def __init__(self):
        self.u = ctypes.WinDLL("user32", use_last_error=True)
        self.u.GetForegroundWindow.restype = w.HWND
        self.u.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
        self.u.GetClassNameW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
        self.u.GetAsyncKeyState.argtypes = [ctypes.c_int]
        self.u.GetAsyncKeyState.restype = w.SHORT
        self.u.SendInput.argtypes = [w.UINT, ctypes.POINTER(Input), ctypes.c_int]
        self.u.SendInput.restype = w.UINT

    def foreground(self):
        hwnd = self.u.GetForegroundWindow()
        title, name = ctypes.create_unicode_buffer(512), ctypes.create_unicode_buffer(256)
        self.u.GetWindowTextW(hwnd, title, len(title))
        self.u.GetClassNameW(hwnd, name, len(name))
        return hwnd if (name.value == "WINDOWSCLIENT"
                        and title.value.lower().startswith("roblox")) else None

    def key(self, key, down):
        packet = Input(type=1)
        packet.data.ki = KeyInput(0, {"W": 0x11, "S": 0x1F}[key],
                                  0x0008 | (0 if down else 0x0002), 0, 0)
        if self.u.SendInput(1, ctypes.byref(packet), ctypes.sizeof(packet)) != 1:
            raise OSError("Windows rejected the keyboard input")


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
                       if keyboard.u.GetAsyncKeyState(key) & 0x8000}
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
