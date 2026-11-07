"""Decide when a boss stall is safe for the ultimate, without side effects."""

STALL_SECONDS = 4.0
HP_DROP = .03
COOLDOWN = 10.0
EPSILON = 1e-9
_UNSET = object()


def valid_hp(value):
    try:
        return 0 < value <= 1
    except TypeError:
        return False


def valid_remaining(value):
    try:
        return 1 <= value <= 3
    except TypeError:
        return False


class UltimatePolicy:
    def __init__(self):
        self.key = _UNSET
        self.since = None
        self.baseline = None
        self.used_at = float('-inf')

    def consider(self, now, key, aligned, hp_fraction, remaining):
        if not aligned or not valid_hp(hp_fraction):
            self._clear_stall()
            return False
        if key != self.key:
            self._clear_stall()
            self.key = key
            self.since = now
            self.baseline = hp_fraction
        elif self.since is None:
            self.since = now
            self.baseline = hp_fraction
        elif self.baseline - hp_fraction >= HP_DROP - EPSILON:
            self.since = now
            self.baseline = hp_fraction
        if not valid_remaining(remaining):
            return False
        if now - self.used_at < COOLDOWN - EPSILON:
            return False
        return now - self.since >= STALL_SECONDS - EPSILON

    def used(self, now):
        self.used_at = max(self.used_at, now)

    def reset(self):
        self._clear_stall()

    def _clear_stall(self):
        self.key = _UNSET
        self.since = None
        self.baseline = None
