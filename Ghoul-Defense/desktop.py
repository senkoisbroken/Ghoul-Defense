"""Windows foreground, client bounds, and owned input only. No process handle."""

import ctypes
import time
from ctypes import wintypes as w

import win_input
from win_input import ULONG_PTR, MOUSEINPUT, KEYBDINPUT, HARDWAREINPUT, INPUT_UNION, INPUT

__all__ = ['ULONG_PTR', 'MOUSEINPUT', 'KEYBDINPUT', 'HARDWAREINPUT',
           'INPUT_UNION', 'INPUT', 'WindowsDesktop']


class WindowsDesktop:
    def __init__(self):
        self.user32 = win_input.USER32

    def prepare_dpi(self):
        try:
            self.user32.SetProcessDpiAwarenessContext.argtypes = [w.HANDLE]
            self.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except (AttributeError, OSError):
            self.user32.SetProcessDPIAware()

    def roblox_window(self):
        return win_input.foreground_roblox(user32=self.user32)

    def client_rect(self, hwnd):
        rect, point = w.RECT(), w.POINT()
        if not self.user32.GetClientRect(
            hwnd, ctypes.byref(rect)
        ) or not self.user32.ClientToScreen(hwnd, ctypes.byref(point)):
            raise OSError("Client bounds unavailable")
        if rect.right < 64 or rect.bottom < 64:
            raise ValueError("Game window is too small")
        return point.x, point.y, rect.right, rect.bottom

    def down(self, key):
        return win_input.key_down(key, user32=self.user32)

    def _send(self, packet):
        win_input.send_input(packet, user32=self.user32)

    def key_button(self, vk, down):
        if vk not in (32, 67, 86, 66, 69, 70, 90):
            raise ValueError("Unsupported output key")
        win_input.send_key_scan(win_input.SCAN_CODES[vk], down, sender=self._send)

    def mouse_button(self, down, right=False):
        win_input.mouse_button(down, right, sender=self._send)

    def press_key(self, hwnd, bounds, vk, allowed):
        """Send an owned key press only to the current foreground game."""
        if (
            not allowed()
            or self.roblox_window() != hwnd
            or self.client_rect(hwnd) != bounds
            or self.down(vk)
        ):
            return False
        self.key_button(vk, True)
        try:
            time.sleep(0.06)
        finally:
            self.key_button(vk, False)
        return True

    def click_client(
        self,
        hwnd,
        bounds,
        x,
        y,
        allowed,
        *,
        settle_seconds=0.03,
        hold_seconds=0.06,
        precise=False,
        reacquire=False,
        before_click=None,
    ):
        """Click a detected client point only while the same game stays foreground."""
        left, top, width, height = bounds
        if not (0 <= x < width and 0 <= y < height):
            raise ValueError("Point is outside the game window")
        if (
            not allowed()
            or self.roblox_window() != hwnd
            or self.client_rect(hwnd) != bounds
        ):
            return False
        # Small relative movements were verified on the live room map. They
        # keep Roblox's cursor tracking in step with the Windows cursor.
        target_x, target_y = left + x, top + y
        deadline = time.monotonic() + 25.0
        # A retry deliberately moves off the target and back so Roblox gets
        # fresh pointer movement even when the previous click left it there.
        destinations = []
        if reacquire:
            offset = 14 if x + 14 < width else -14
            destinations.append((target_x + offset, target_y))
        destinations.append((target_x, target_y))
        step, interval = (12, 0.001) if precise or reacquire else (16, 0.001)
        for destination_x, destination_y in destinations:
            while time.monotonic() < deadline:
                if (
                    not allowed()
                    or self.roblox_window() != hwnd
                    or self.client_rect(hwnd) != bounds
                ):
                    return False
                if self.down(1):
                    return False
                cursor_x, cursor_y = win_input.cursor_position(user32=self.user32)
                dx, dy = destination_x - cursor_x, destination_y - cursor_y
                if abs(dx) <= 1 and abs(dy) <= 1:
                    break
                # Cover long distances quickly, retaining fine motion near the
                # detected control and the final ownership/image checks.
                stride = 5 if max(abs(dx), abs(dy)) <= 24 else step
                win_input.move_relative(
                    max(-stride, min(stride, dx)),
                    max(-stride, min(stride, dy)),
                    sender=self._send,
                )
                time.sleep(interval)
            else:
                return False
        time.sleep(settle_seconds)
        if (
            not allowed()
            or self.roblox_window() != hwnd
            or self.client_rect(hwnd) != bounds
            or self.down(1)
        ):
            return False
        if before_click is not None:
            if not before_click():
                return False
            if (
                not allowed()
                or self.roblox_window() != hwnd
                or self.client_rect(hwnd) != bounds
                or self.down(1)
            ):
                return False
        self.mouse_button(True)
        try:
            time.sleep(hold_seconds)
        finally:
            self.mouse_button(False)
        return True
