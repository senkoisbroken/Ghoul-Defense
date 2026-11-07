"""Own the W/S patrol and boss-following taps independently of screen work."""

import threading

from ws_repeater import Keyboard, Playback

ALIGNED = 12
TAP = .06
INTERVAL = .12


class Movement:
    def __init__(self, keyboard=None):
        self.playback = Playback(keyboard if keyboard is not None else Keyboard())
        self.lock = threading.Lock()
        self.window = None
        self.valid_until = float('-inf')
        self.boss = None
        self.observations = 0
        self.boss_key = None
        self.boss_release = 0.0
        self.boss_press_observation = -1
        self.boss_press_at = float('-inf')

    def observe(self, window, allowed, now, boss=None):
        with self.lock:
            if not allowed:
                self.window = None
                self.valid_until = float('-inf')
                self.boss = None
                self._halt()
                return
            changed = (window != self.window
                       or (boss is not None) != (self.boss is not None))
            self.window = window
            self.valid_until = now + .8
            self.observations += 1
            if changed:
                self._halt()
            self.boss = boss
            if boss is not None and self.boss_key is not None:
                offset = boss[1] - boss[0]
                target = (None if abs(offset) <= ALIGNED
                          else ('W' if offset < 0 else 'S'))
                if target != self.boss_key:
                    self._release_boss()

    def tick(self, now, enabled):
        with self.lock:
            if (not enabled or now > self.valid_until or self.window is None
                    or self.playback.keyboard.foreground() != self.window):
                self._halt()
                return
            if self.boss is not None:
                self._follow_boss(now)
                return
            if not self.playback.running:
                self.playback.start()
            self.playback.tick(now)

    def stop(self):
        with self.lock:
            self.window = None
            self.valid_until = float('-inf')
            self.boss = None
            self._halt()

    def _halt(self):
        try:
            self._release_boss()
        finally:
            self.playback.stop()

    def _release_boss(self):
        key = self.boss_key
        if key is None:
            self.boss_release = 0.0
            return
        if self.playback.held == key:
            self.playback.held = None
        self.playback.keyboard.key(key, False)
        self.boss_key = None
        self.boss_release = 0.0

    def _follow_boss(self, now):
        player_y, boss_y = self.boss
        offset = boss_y - player_y
        target = None if abs(offset) <= ALIGNED else ('W' if offset < 0 else 'S')
        if self.boss_key is not None:
            if target != self.boss_key or now >= self.boss_release:
                self._release_boss()
            if self.boss_key is not None:
                return
        if target is None:
            return
        # One tap per observation: a fresh screen read must follow each press.
        if self.observations <= self.boss_press_observation:
            return
        if now - self.boss_press_at < INTERVAL:
            return
        self.playback.keyboard.key(target, True)
        self.playback.held = target
        self.boss_key = target
        self.boss_release = now + TAP
        self.boss_press_observation = self.observations
        self.boss_press_at = now
