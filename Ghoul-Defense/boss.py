"""Boss HUD checks and color-independent sprite/ground-marker tracking."""

from dataclasses import dataclass
from pathlib import Path
import re

import cv2
import numpy as np
from ghoul import TextReader, gate_bar


def normalize(image):
    return cv2.resize(image, (960, round(image.shape[0] * 960 / image.shape[1])))


def text_crop(crop, colored=False):
    """Trim blank/art margins so the recognizer sees the entire numeric line."""
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (0, 0, 175), (180, 130, 255))
    # Boss names turn red during enrage; white-only trimming discarded them.
    if colored:
        mask |= cv2.inRange(hsv, (0, 140, 150), (10, 255, 255))
        mask |= cv2.inRange(hsv, (170, 140, 150), (180, 255, 255))
    mask[np.count_nonzero(mask, axis=1) > mask.shape[1] * .8] = 0
    ys, xs = np.nonzero(mask)
    if not len(xs):
        return crop
    return crop[max(0, ys.min()-2):min(mask.shape[0], ys.max()+3),
                max(0, xs.min()-2):min(mask.shape[1], xs.max()+3)]


def hp_fraction(text):
    match = re.search(r'([\d][\d,.]*)\s*([KMBTQ]?)\s*[/|]\s*([\d][\d,.]*)\s*([KMBTQ]?)',
                      text, re.IGNORECASE)
    if not match:
        return None
    units = {'': 1, 'K': 1e3, 'M': 1e6, 'B': 1e9, 'T': 1e12, 'Q': 1e15}
    try:
        current = float(match[1].replace(',', '')) * units[match[2].upper()]
        maximum = float(match[3].replace(',', '')) * units[match[4].upper()]
    except ValueError:
        return None
    return min(1.0, current / maximum) if maximum > 0 else None


def world_scale(image):
    """Scale of the 3D world in a 960-wide frame.

    Roblox keeps the vertical field of view fixed, so a taller frame shows
    the same world objects larger after width normalization.
    """
    return image.shape[0] / 504


def player_marker(image, road_top):
    height, width = image.shape[:2]
    world = world_scale(image)
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, (15, 90, 100), (40, 255, 255))
    mask[:road_top] = 0
    mask[round(height * .88):] = 0
    mask[:, round(width * .3125):] = 0
    mask = cv2.morphologyEx(
        mask, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (max(9, round(9 * world)), 1)))
    mask = cv2.morphologyEx(
        mask, cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT, (max(8, round(16 * world)), 1)))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    rows = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if (round(30 * world) <= w <= round(100 * world)
                and h <= max(2, round(2 * world)) and x > 20):
            near = next((i for i, old in enumerate(rows)
                         if abs(y - old[1]) <= round(9 * world)), None)
            if near is None:
                rows.append((x, y, w, h))
            else:
                if y + h / 2 > rows[near][1] + rows[near][3] / 2:
                    rows[near] = (x, y, w, h)
    return rows[0] if len(rows) == 1 else None


def locate_player(image, road_top):
    marker = player_marker(image, road_top)
    return marker[1] + marker[3] / 2 if marker else None


_bar = cv2.imread(str(Path(__file__).parent / 'assets/boss_health_outline.png'))
if _bar is None:
    raise RuntimeError('Missing common health-bar outline reference')
_BAR_MASKS = {}


def bar_masks(world=1.0):
    key = round(world, 3)
    masks = _BAR_MASKS.get(key)
    if masks is None:
        if len(_BAR_MASKS) >= 32:
            _BAR_MASKS.clear()
        masks = tuple(cv2.inRange(
            cv2.cvtColor(cv2.resize(_bar, None, fx=s * world, fy=s * world),
                         cv2.COLOR_BGR2HSV),
            (0, 0, 135), (180, 100, 255)) for s in (.85, .925, 1, 1.075, 1.15))
        _BAR_MASKS[key] = masks
    return masks


def locate_boss(image, road_top, details=None):
    details = details if details is not None else {}
    height, width = image.shape[:2]
    world = world_scale(image)
    marker = player_marker(image, road_top)
    if marker:
        # Visible geometry survives cropped screenshots and viewport changes.
        world = marker[2] / 44
    # A tall boss's bar can sit above the road's top edge. Keep the road
    # bound for player tracking, but include the space above it for bars.
    road_top = max(0, road_top-round(70*world))
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    white = cv2.inRange(hsv,
                        (0, 0, 80), (180, 180, 255))
    bottom = round(height * .88)
    region = white.copy()
    region[:road_top] = 0
    region[bottom:] = 0
    region = cv2.morphologyEx(
        region, cv2.MORPH_CLOSE,
        cv2.getStructuringElement(cv2.MORPH_RECT, (3, 1)))
    region = cv2.morphologyEx(
        region, cv2.MORPH_OPEN,
        cv2.getStructuringElement(cv2.MORPH_RECT,
                                  (max(20, round(38 * world)), 1)))
    red = cv2.bitwise_or(cv2.inRange(hsv, (0, 140, 180), (10, 255, 255)),
                         cv2.inRange(hsv, (170, 140, 180), (180, 255, 255)))
    lines = []
    # Read horizontal runs separately: hair touching a rim must not merge
    # its contour into a tall component and erase the health bar.
    for y in range(road_top, bottom):
        edges = np.diff(np.pad(region[y] > 0, (1, 1)).astype(np.int8))
        for x, end in zip(np.flatnonzero(edges == 1), np.flatnonzero(edges == -1)):
            w = int(end - x)
            if round(40 * world) <= w <= round(49 * world):
                lines.append((int(x), y, w))
    # Also project from a straight top rim when the bottom touches white hair.
    projected = []
    for x, y, w in lines:
        for depth in range(max(2, round(2*world)), max(4, round(5*world))+1):
            by = y+depth
            if by < bottom:
                projected.append((x, by, w))
    lines.extend(projected)
    peaks = []
    for x, y, w in lines:
        for depth in range(max(2, round(2*world)), max(4, round(5*world))+1):
            top = y-depth
            if top < road_top:
                continue
            inside = hsv[top+1:y, x+2:x+w-2]
            fill = red[top+1:y, x+2:x+w-2] > 0
            # The interior is a horizontal red fill followed by dark gray,
            # rather than arbitrary bright/red portions of the sprite.
            empty = (inside[:, :, 1] < 130) & (inside[:, :, 2] < 135)
            rim = (white[top, x+2:x+w-2] | red[top, x+2:x+w-2]) > 0
            left_rim = white[top:y+1, max(0,x-2):x+2] > 0
            right_rim = white[top:y+1, x+w-2:min(width,x+w+2)] > 0
            if (fill.size and np.mean(fill) >= .15
                    and np.mean(fill[:, :3]) >= .5
                    and np.mean(fill | empty) >= .88 and np.mean(rim) >= .65
                    and np.max(np.mean(left_rim, axis=0)) >= .65
                    and np.max(np.mean(right_rim, axis=0)) >= .65):
                peaks.append((w, x, top, w, depth+1))
                break
    # A thin, partially filled bar may have an interrupted bottom edge. Its
    # full ring can still verify the same common health-bar geometry.
    if not peaks:
        strict = cv2.inRange(hsv, (0, 0, 135), (180, 100, 255))[road_top:bottom]
        for template in bar_masks(world):
            bh, bw = template.shape
            if strict.shape[0] < bh:
                continue
            scores = cv2.matchTemplate(strict, template, cv2.TM_CCOEFF_NORMED)
            _, score, _, (bx, by) = cv2.minMaxLoc(scores)
            if score >= .88:
                peaks.append((float(score), bx, by+road_top, bw, bh))
    if not peaks:
        details['reason'] = 'health_bar_not_found'
        return None
    peaks.sort(reverse=True)
    _, x, y, w, h = peaks[0]
    details['bars'] = [(int(px), int(py), int(pw), int(ph))
                       for _, px, py, pw, ph in peaks]
    if any(abs(px - x) > round(20 * world) or abs(py - y) > round(10 * world)
           for _, px, py, _, _ in peaks[1:]):
        details['reason'] = 'ambiguous_health_bars'
        return None
    # Estimate the road background separately at each height, outside the
    # sprite. This supports different boss heights and colors without an art
    # template or a name-to-lane-offset table.
    left, right = max(0, x - w), min(width, x + 2 * w)
    top, bottom = y + h, min(bottom, round(y + 4.4 * w))
    roi = image[top:bottom, left:right]
    samples = []
    for lo, hi in ((max(0, left - 2*w), max(0, left - w)),
                   (min(width, right + w), min(width, right + 2*w))):
        if hi - lo > 5:
            samples.append(image[top:bottom, lo:hi])
    if not samples or roi.size == 0:
        details['reason'] = 'background_unavailable'
        return None
    background = np.median(np.concatenate(samples, axis=1), axis=1)[:, None, :]
    mask = np.where(np.max(np.abs(roi.astype(float) - background), axis=2) > 35,
                    255, 0).astype(np.uint8)
    mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN,
                            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE,
                            cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    candidates = []
    for contour in contours:
        bx, by, bw, bh = cv2.boundingRect(contour)
        area = cv2.contourArea(contour)
        if (area > 150 * world * world and bh > 35 * world
                and by < 40 * world
                and bx < x + w - left and bx + bw > x - left
                and by + bh < roi.shape[0] - max(2, round(2 * world))):
            candidates.append((area, by + bh))
    if not candidates:
        details['reason'] = 'sprite_not_isolated'
        return None
    candidates.sort(reverse=True)
    details['reason'] = 'located'
    return top + candidates[0][1] + round(4 * world)


@dataclass
class BossObservation:
    name: str
    remaining: int
    target: tuple | None
    hp_fraction: float | None = None


class BossTracker:
    def __init__(self, reader=None):
        self.reader = reader
        self.last = {}
        self.engaged = None
        self.missing_headers = 0

    def reset(self):
        self.engaged = None
        self.missing_headers = 0
        self.last = {}

    def read(self, original):
        result = self._read(original)
        if result is not None:
            self.engaged = result
            self.missing_headers = 0
            return result
        reason = self.last.get('reason')
        if self.engaged is not None and reason in ('counter_unreadable', 'boss_header_not_confirmed'):
            if reason == 'boss_header_not_confirmed':
                rows = self.last.get('hud', [])
                weak = len(rows) == 3 and rows[1][1] < .3 and rows[2][1] < .3
                self.missing_headers = self.missing_headers + 1 if weak else 0
                if self.missing_headers >= 2:
                    self.engaged = None
                    return None
            previous = self.engaged
            self.last['reason'] = 'holding_after_uncertain_boss_frame'
            return BossObservation(previous.name, previous.remaining, None)
        self.engaged = None
        self.missing_headers = 0
        return None

    def _read(self, original):
        image = normalize(original)
        gate = gate_bar(image)
        if gate is None:
            self.last = {'reason': 'gate_not_visible'}
            return None
        x, y, w, h = gate
        world = world_scale(image)
        # The green fill shrinks when the gate takes damage; its midpoint is
        # not the HUD's center. The HUD remains centered in the client view.
        center = image.shape[1] // 2
        scale = original.shape[1] / image.shape[1]

        def native_crop(left, top, right, bottom):
            return original[max(0, round(top*scale)):round(bottom*scale),
                            max(0, round(left*scale)):round(right*scale)]

        # Locate the HUD in normalized geometry, but recognize its original
        # pixels so decimal points do not disappear in a second downsample.
        count = native_crop(center-round(75*world), max(0,y-round(16*world)),
                            center+round(75*world), y-1)
        name = native_crop(center-round(123*world), y+round(h*2),
                           center+round(45*world), y+round(h*3.9))
        health = native_crop(center+round(28*world), y+round(h*2),
                             center+round(125*world), y+round(h*3.9))
        if any(crop.size == 0 for crop in (count, name, health)):
            return None
        if self.reader is None:
            self.reader = TextReader()
        rows = list(self.reader.read([text_crop(count), text_crop(name),
                                      text_crop(health)]))
        if not rows[1][0] or rows[1][1] < .7:
            # Retry only the unreadable title in color. Normal white titles
            # keep their tighter crop instead of including red scenery.
            rows[1] = self.reader.read([text_crop(name, colored=True)])[0]
        if rows[2][1] < .7 or hp_fraction(rows[2][0]) is None:
            # Compression can merge a decimal or slash with the text outline.
            # Retry actual pixels with different margins/resampling; retain
            # the HP grammar and confidence requirements.
            cropped = text_crop(health)
            _, binary = cv2.threshold(cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY),
                                       170, 255, cv2.THRESH_BINARY)
            alternatives = self.reader.read([
                cv2.resize(cropped, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC),
                cv2.cvtColor(binary, cv2.COLOR_GRAY2BGR),
                cv2.cvtColor(255-binary, cv2.COLOR_GRAY2BGR)])
            valid = [row for row in alternatives if hp_fraction(row[0]) is not None]
            if valid:
                best = max(valid, key=lambda row: row[1])
                if best[1] > rows[2][1]:
                    rows[2] = best
        self.last = {'reason': 'counter_unreadable',
                     'hud': [(text, round(float(score), 3)) for text, score in rows]}
        text, confidence = rows[0]
        match = re.fullmatch(r'\s*(\d+)\s*remaining\s*', text, re.IGNORECASE)
        if match is None or confidence < .7:
            return None
        remaining = int(match[1])
        self.last['remaining'] = remaining
        if not 1 <= remaining <= 3:
            self.last['reason'] = 'many_enemies_or_wave_finished'
            return None
        boss_name, name_confidence = rows[1]
        boss_name = re.sub(r'\s+is\s+enraged[!\s]*$', '', boss_name,
                           flags=re.IGNORECASE).strip()
        hp, hp_confidence = rows[2]
        if (name_confidence < .7 or hp_confidence < .7 or len(boss_name) < 4
                or re.search(r'\d.*[/|].*\d', hp) is None):
            self.last['reason'] = 'boss_header_not_confirmed'
            return None
        fraction = hp_fraction(hp)
        if fraction is None or fraction <= 0:
            self.last['reason'] = 'boss_hp_not_alive'
            return None
        road_top = y + h + round(image.shape[0] * .137)
        details = {}
        player_y = locate_player(image, road_top)
        boss_y = locate_boss(image, road_top, details)
        self.last['boss_detection'] = details
        self.last['player_y'] = player_y
        target = ((player_y, boss_y) if player_y is not None and boss_y is not None else None)
        self.last['reason'] = 'following' if target else 'lane_not_visible'
        return BossObservation(boss_name, remaining, target, fraction)
