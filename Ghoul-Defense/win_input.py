"""Shared Windows input ABI and foreground-only inspection primitives."""

import ctypes
from ctypes import wintypes as w

ULONG_PTR = ctypes.c_size_t
SCAN_CODES = {32: 0x39, 67: 0x2E, 86: 0x2F, 66: 0x30, 69: 0x12,
              70: 0x21, 90: 0x2C, 87: 0x11, 83: 0x1F}


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", w.LONG), ("dy", w.LONG), ("mouseData", w.DWORD),
                ("dwFlags", w.DWORD), ("time", w.DWORD), ("dwExtraInfo", ULONG_PTR)]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", w.WORD), ("wScan", w.WORD), ("dwFlags", w.DWORD),
                ("time", w.DWORD), ("dwExtraInfo", ULONG_PTR)]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [("uMsg", w.DWORD), ("wParamL", w.WORD), ("wParamH", w.WORD)]


class INPUT_UNION(ctypes.Union):
    _fields_ = [("mi", MOUSEINPUT), ("ki", KEYBDINPUT), ("hi", HARDWAREINPUT)]


class INPUT(ctypes.Structure):
    _anonymous_ = ("data",)
    _fields_ = [("type", w.DWORD), ("data", INPUT_UNION)]


# Preserve the standalone repeater's original field names on the shared ABI.
KEYBDINPUT.vk = KEYBDINPUT.wVk
KEYBDINPUT.scan = KEYBDINPUT.wScan
KEYBDINPUT.flags = KEYBDINPUT.dwFlags
KEYBDINPUT.extra = KEYBDINPUT.dwExtraInfo
MOUSEINPUT.data = MOUSEINPUT.mouseData
MOUSEINPUT.flags = MOUSEINPUT.dwFlags
MOUSEINPUT.extra = MOUSEINPUT.dwExtraInfo

USER32 = ctypes.WinDLL("user32", use_last_error=True)
USER32.GetForegroundWindow.argtypes = []
USER32.GetForegroundWindow.restype = w.HWND
USER32.GetClassNameW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
USER32.GetClassNameW.restype = ctypes.c_int
USER32.GetWindowTextW.argtypes = [w.HWND, w.LPWSTR, ctypes.c_int]
USER32.GetWindowTextW.restype = ctypes.c_int
USER32.GetClientRect.argtypes = [w.HWND, ctypes.POINTER(w.RECT)]
USER32.GetClientRect.restype = w.BOOL
USER32.ClientToScreen.argtypes = [w.HWND, ctypes.POINTER(w.POINT)]
USER32.ClientToScreen.restype = w.BOOL
USER32.IsIconic.argtypes = [w.HWND]
USER32.IsIconic.restype = w.BOOL
USER32.GetAsyncKeyState.argtypes = [ctypes.c_int]
USER32.GetAsyncKeyState.restype = w.SHORT
USER32.GetCursorPos.argtypes = [ctypes.POINTER(w.POINT)]
USER32.GetCursorPos.restype = w.BOOL
USER32.SendInput.argtypes = [w.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
USER32.SendInput.restype = w.UINT


def send_input(packet, *, user32=None):
    u = USER32 if user32 is None else user32
    if u.SendInput(1, ctypes.byref(packet), ctypes.sizeof(INPUT)) != 1:
        raise ctypes.WinError(ctypes.get_last_error())


def send_key_scan(scan, down, *, user32=None, sender=None):
    packet = INPUT(type=1)
    packet.ki.wScan = scan
    packet.ki.dwFlags = 8 | (0 if down else 2)
    if sender is None:
        send_input(packet, user32=user32)
    else:
        sender(packet)


def mouse_button(down, right=False, *, user32=None, sender=None):
    packet = INPUT(type=0)
    packet.mi.dwFlags = (8 if down else 16) if right else (2 if down else 4)
    if sender is None:
        send_input(packet, user32=user32)
    else:
        sender(packet)


def move_relative(dx, dy, *, user32=None, sender=None):
    packet = INPUT(type=0)
    packet.mi.dx, packet.mi.dy = dx, dy
    packet.mi.dwFlags = 0x0001 | 0x2000
    if sender is None:
        send_input(packet, user32=user32)
    else:
        sender(packet)


def foreground_roblox(*, user32=None):
    u = USER32 if user32 is None else user32
    hwnd = u.GetForegroundWindow()
    if not hwnd or u.IsIconic(hwnd):
        return None
    name, title = ctypes.create_unicode_buffer(256), ctypes.create_unicode_buffer(512)
    if not u.GetClassNameW(hwnd, name, len(name)) or not u.GetWindowTextW(hwnd, title, len(title)):
        return None
    return hwnd if name.value == "WINDOWSCLIENT" and title.value.lower().startswith("roblox") else None


def key_down(vk, *, user32=None):
    u = USER32 if user32 is None else user32
    return bool(u.GetAsyncKeyState(vk) & 0x8000)


def cursor_position(*, user32=None):
    u = USER32 if user32 is None else user32
    point = w.POINT()
    if not u.GetCursorPos(ctypes.byref(point)):
        raise ctypes.WinError(ctypes.get_last_error())
    return point.x, point.y
