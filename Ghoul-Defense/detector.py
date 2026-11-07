"""Adaptive menu, wave, replay and ability recognition."""

from dataclasses import dataclass
from pathlib import Path
import cv2
from names import choose, clean
from ocr import TextReader, _read_raw, _read_names
from frame import to_960

ROOT = Path(__file__).resolve().parent


REFERENCE_WIDTH = 1920


REFERENCE_HEIGHT = 1009


MIN_UI_SCALE = .35


MAX_UI_SCALE = 3.5


def ui_scale_candidates(width, height):
    """Return likely (x, y) template scales in a 960-wide normalized frame.

    Roblox interfaces commonly follow one of these models:

    * width-relative sizes (``UDim2.fromScale(1, 0)``)
    * height-relative sizes
    * fixed pixel offsets
    * independent X/Y scaling (plain ``UDim2`` scale)
    * a uniform scale clamped to the smaller or larger axis

    Returned pairs are compared against the reference template scale.
    """
    if width <= 0 or height <= 0:
        return ((1.0, 1.0),)
    height_scale = (height / REFERENCE_HEIGHT) * (REFERENCE_WIDTH / width)
    fixed_scale = REFERENCE_WIDTH / width
    uniform = min(1.0, height_scale)
    pairs = (
        (1.0, 1.0),
        (height_scale, height_scale),
        (fixed_scale, fixed_scale),
        (1.0, height_scale),
        (height_scale, 1.0),
        (uniform, uniform),
        (max(1.0, height_scale),) * 2,
    )
    scales = []
    for x, y in pairs:
        pair = round(x, 3), round(y, 3)
        if (MIN_UI_SCALE <= pair[0] <= MAX_UI_SCALE
                and MIN_UI_SCALE <= pair[1] <= MAX_UI_SCALE
                and pair not in scales):
            scales.append(pair)
    return tuple(scales)


@dataclass
class Decision:
    kind: str
    name: str
    names: tuple
    target: tuple
    cards: tuple = ()

    @property
    def signature(self):
        return self.kind, self.names


class Detector:
    def __init__(self, reader=None):
        self.templates = {}
        for name in ('perk_title', 'relic_title', 'start_wave', 'replay_title', 'replay_button',
                     'ultimate_title'):
            image = cv2.imread(str(ROOT / 'assets' / (name + '.png')), 0)
            if image is None:
                raise RuntimeError('Missing reference: ' + name)
            self.templates[name] = image
        self.scaled = {}
        self.hints = {}
        self.ocr = reader

    def template(self, name, x, y):
        key = (name, round(x, 4), round(y, 4))
        image = self.scaled.get(key)
        if image is None:
            if len(self.scaled) > 512:
                self.scaled.clear()
            base = self.templates[name]
            if key[1] == 1.0 and key[2] == 1.0:
                image = base
            else:
                image = cv2.resize(
                    base, (max(1, round(base.shape[1] * key[1])),
                           max(1, round(base.shape[0] * key[2]))))
            # Both the screenshot and the reference have been resampled at
            # non-reference sizes; matching after an equal blur makes the
            # comparison tolerant of the resulting softness.
            image = cv2.GaussianBlur(image, (3, 3), .6)
            self.scaled[key] = image
        return image

    @staticmethod
    def _match(search, template):
        if template.shape[0] > search.shape[0] or template.shape[1] > search.shape[1]:
            return None
        _, score, _, (x, y) = cv2.minMaxLoc(
            cv2.matchTemplate(search, template, cv2.TM_CCOEFF_NORMED))
        return score, (x, y, template.shape[1], template.shape[0])

    def match(self, gray, name, threshold, width, height):
        """Return (score, rect, (x_scale, y_scale)) for the strongest match."""
        search = cv2.GaussianBlur(gray, (3, 3), .6)
        best = None
        hint = self.hints.get((name, width, height))

        def attempt(x, y):
            nonlocal best
            found = self._match(search, self.template(name, x, y))
            if found is not None and (best is None or found[0] > best[0]):
                best = found[0], found[1], (x, y)

        if hint is not None:
            attempt(*hint)
        if best is None or best[0] < threshold:
            for x, y in ui_scale_candidates(width, height):
                if (x, y) != hint:
                    attempt(x, y)
        if best is not None and .66 <= best[0] < threshold:
            # The game can size its UI by width, height, pixels or a clamped
            # scale, and real clients rarely land exactly on a model. Refine
            # each axis around the closest model instead of requiring an
            # exact match in a short fixed list.
            for axis in (0, 1):
                for step in (1, 2, 3):
                    improved = False
                    for direction in (-1, 1):
                        pair = list(best[2])
                        pair[axis] = round(
                            pair[axis] * (1 + direction * step * .005), 4)
                        if not all(MIN_UI_SCALE <= value <= MAX_UI_SCALE
                                   for value in pair):
                            continue
                        found = self._match(
                            search, self.template(name, pair[0], pair[1]))
                        if found is not None and found[0] > best[0]:
                            best = found[0], found[1], (pair[0], pair[1])
                            improved = True
                    if not improved:
                        break
        if best is None or best[0] < threshold:
            return None
        if len(self.hints) > 128:
            self.hints.clear()
        self.hints[(name, width, height)] = best[2]
        return best

    def read(self, original):
        width, height = original.shape[1], original.shape[0]
        scale = width / 960
        image = to_960(original)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

        headings = []
        for name, kind in (('perk_title', 'perk'), ('relic_title', 'relic')):
            found = self.match(gray, name, .93, width, height)
            if found is not None:
                headings.append((found, kind))
        if headings:
            (_, heading, (ui_x, ui_y)), kind = max(headings, key=lambda item: item[0][0])
            frame_height, frame_width = image.shape[:2]
            hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
            # Rarity changes border hue. Detect the bright long edges rather
            # than restricting perks to a particular rarity color.
            border = cv2.inRange(hsv, (0, 0, 150), (180, 255, 255))
            border = cv2.morphologyEx(border, cv2.MORPH_CLOSE,
                                     cv2.getStructuringElement(cv2.MORPH_RECT, (3, 5)))
            # Long vertical card edges survive reward panels behind the menu;
            # whole contours can merge with those unrelated background panels.
            vertical = cv2.morphologyEx(
                border, cv2.MORPH_OPEN,
                cv2.getStructuringElement(cv2.MORPH_RECT,
                                          (1, max(30, round(70 * ui_y)))))
            contours, _ = cv2.findContours(vertical, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            edges = []
            band_start = heading[1] + heading[3] + round(frame_height * .005)
            band_end = (heading[1] + heading[3]
                        + round(min(100 * ui_y, frame_height * .25)))
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                if (w < max(4, round(frame_width * .0125))
                        and h > 150 * ui_y
                        and band_start <= y <= band_end):
                    edges.append((x, y, w, h))
            edges.sort()
            if len(edges) not in (2, 4, 6):
                return None
            cards = []
            # The cards keep their reference aspect when the UI scales
            # uniformly, but independent X/Y scaling stretches them. Compare
            # against the scale measured from the heading instead of one
            # fixed pixel ratio.
            expected_ratio = .82 * ui_x / ui_y
            for a, b in zip(edges[::2], edges[1::2]):
                x, y = a[0], min(a[1], b[1]) - 8
                w, h = b[0] + b[2] - x, max(a[1] + a[3], b[1] + b[3]) - y + 8
                if not (frame_width * .07 < w < frame_width * .5
                        and frame_height * .15 < h < frame_height * .95
                        and .15 < w / h < 2.0
                        and .55 * expected_ratio < w / h < 1.45 * expected_ratio
                        and abs(a[1] - b[1]) < frame_height * .04):
                    return None
                cards.append((x, y, w, h))
            crops = [image[y + round(h * .42):y + round(h * .54),
                           x + round(w * .06):x + round(w * .94)]
                     for x, y, w, h in cards]
            if self.ocr is None:
                self.ocr = TextReader()
            texts = _read_names(self.ocr, crops)
            if any(not name or confidence < 0.60 for name, confidence in texts):
                return None
            names = tuple(name for name, _ in texts)
            chosen = choose(names)
            x, y, w, h = cards[chosen]
            return Decision(kind, names[chosen], names,
                            (round((x + w / 2) * scale), round((y + h * .57) * scale)),
                            tuple((name, tuple(round(v * scale) for v in rect))
                                  for name, rect in zip(names, cards)))
        button = self.match(gray, 'start_wave', .70, width, height)
        if button is not None:
            _, box, _ = button
            x, y, w, h = box
            if (y > image.shape[0] * .55
                    and abs(x + w / 2 - image.shape[1] / 2) < image.shape[1] * .3
                    and self.green_button(image, box)):
                return Decision('wave', 'Start Wave', (),
                                (round((x + w / 2) * scale), round((y + h / 2) * scale)))
        replay_title = self.match(gray, 'replay_title', .85, width, height)
        replay = (self.match(gray, 'replay_button', .69, width, height)
                  if replay_title is not None else None)
        if replay is not None:
            _, box, _ = replay
            _, title_box, _ = replay_title
            x, y, w, h = box
            tx, ty, tw, th = title_box
            if (round(image.shape[0] * .08) < y - (ty + th) < round(image.shape[0] * .8)
                    and abs(x+w/2-tx-tw/2) < round(image.shape[1] * .19)
                    and self.green_button(image, box)):
                return Decision('replay', 'Play Again', (),
                                (round((x + w/2)*scale), round((y + h/2)*scale)))
        return None

    @staticmethod
    def green_button(image, box):
        x, y, w, h = box
        hsv = cv2.cvtColor(image[max(0, y - 6):y + h + 6,
                                max(0, x - 6):x + w + 6], cv2.COLOR_BGR2HSV)
        green = cv2.inRange(hsv, (35, 65, 70), (90, 255, 255))
        return cv2.countNonZero(green) / max(green.size, 1) > .25

    def ultimate_ready(self, original, reader):
        image = to_960(original)
        found = self.match(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), 'ultimate_title',
                           .90, original.shape[1], original.shape[0])
        if found is None:
            return False
        _, box, _ = found
        x, y, w, h = box
        status = image[y+round(h*1.2):y+round(h*2.2), x:x+round(w*.55)]
        if status.size == 0:
            return False
        text, confidence = _read_raw(reader, [status])[0]
        return clean(text) == 'ready' and confidence >= .70
