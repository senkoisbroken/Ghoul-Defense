"""Use Cyberpunk's stronger choice/retry input profile for UI controls."""

import time
from dataclasses import dataclass
import numpy as np


class FocusChanged(RuntimeError):
    """A frame is no longer owned by the window that requested it."""


class CaptureUnavailable(RuntimeError):
    """The owned capture contains no usable screenshot pixels."""

    def __init__(self, reason):
        self.reason = reason
        super().__init__(reason)


def capture_frame(cap, desktop, hwnd, bounds, allowed):
    def current():
        return (
            allowed()
            and desktop.roblox_window() == hwnd
            and desktop.client_rect(hwnd) == bounds
        )

    if not current():
        raise FocusChanged("Focus, bounds, or run state changed before capture")
    left, top, width, height = bounds
    pixels = np.asarray(
        cap.grab({"left": left, "top": top, "width": width, "height": height})
    )
    if not current():
        raise FocusChanged("Focus, bounds, or run state changed during capture")
    if (
        pixels.ndim != 3
        or pixels.shape[:2] != (height, width)
        or pixels.shape[2] < 3
        or height <= 0
        or width <= 0
    ):
        raise CaptureUnavailable("invalid capture shape")
    image = pixels[:, :, :3].copy()
    if not np.any(image):
        raise CaptureUnavailable("black screenshot")
    return image


def wait_for(read, predicate, allowed, timeout=1.2, interval=0.08):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and allowed():
        result = read()
        if allowed() and predicate(result):
            return result
        time.sleep(interval)
    return None


def click_control(desktop, hwnd, bounds, x, y, allowed, *, before_click=None):
    verification = {} if before_click is None else {"before_click": before_click}
    return desktop.click_client(
        hwnd,
        bounds,
        x,
        y,
        allowed,
        precise=True,
        reacquire=True,
        settle_seconds=0.12,
        hold_seconds=0.15,
        **verification,
    )


@dataclass
class WindowControls:
    """A capture and its follow-up actions belong to one unchanged window."""

    desktop: object
    capture: object
    hwnd: int
    bounds: tuple
    enabled: object

    def allowed(self):
        return (
            self.enabled()
            and self.desktop.roblox_window() == self.hwnd
            and self.desktop.client_rect(self.hwnd) == self.bounds
        )

    def read(self):
        return capture_frame(
            self.capture, self.desktop, self.hwnd, self.bounds, self.enabled
        )

    def click(self, target, verify=None):
        if not self.allowed():
            return False
        verification = {} if verify is None else {"before_click": verify}
        return click_control(
            self.desktop, self.hwnd, self.bounds, *target, self.allowed, **verification
        )

    def press(self, key):
        if not self.allowed():
            return False
        return self.desktop.press_key(self.hwnd, self.bounds, key, self.allowed)
