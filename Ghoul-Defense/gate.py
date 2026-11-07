"""Gate HUD detection independent of menu and boss policy."""

import re
import cv2
from frame import to_960
from ocr import TextReader, _read_raw


_gate_reader = None


def gate_bar(image, reader=None):
    """Locate the gate HUD even when its fill is short, yellow, or red."""
    height, width = image.shape[:2]
    hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)
    green = cv2.inRange(hsv, (35, 70, 70), (90, 255, 255))
    contours, _ = cv2.findContours(green, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    found = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if (width*.12 < w < width*.75 and 2 <= h < height*.06 and w / h > 10
                and y+h < height*.4):
            found.append((x, y, w, h))
    if len(found) == 1:
        return found[0]
    # The full outline remains visible after the colored fill shrinks or
    # changes hue. Match its two horizontal edges, then verify the Gate label
    # and numeric health so XP bars/scenery cannot authorize movement.
    dark = cv2.inRange(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY), 0, 40)
    dark[round(height*.4):] = 0
    dark = cv2.morphologyEx(dark, cv2.MORPH_OPEN,
                           cv2.getStructuringElement(cv2.MORPH_RECT,
                                                     (max(20, round(width*.10)), 1)))
    contours, _ = cv2.findContours(dark, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    lines = [cv2.boundingRect(contour) for contour in contours]
    for x, y, w, h in lines:
        if (not width*.12 < w < width*.75 or h > 2
                or abs(x+w/2-width/2) > width*.08):
            continue
        for bx, by, bw, bh in lines:
            if (not height*.006 < by-y < height*.06 or bh > 2
                    or abs(bx-x) > max(5,round(w*.025))
                    or abs(bw-w) > max(8,round(w*.06))):
                continue
            crop = image[y+1:by, x:x+w]
            white = cv2.inRange(cv2.cvtColor(crop, cv2.COLOR_BGR2HSV),
                                (0, 0, 175), (180, 130, 255))
            points = cv2.findNonZero(white)
            if points is None or len(points) < 12:
                continue
            tx, ty, tw, th = cv2.boundingRect(points)
            text_image = crop[max(0,ty-1):ty+th+1, max(0,tx-1):tx+tw+1]
            global _gate_reader
            active_reader = reader
            if active_reader is None:
                if _gate_reader is None:
                    _gate_reader = TextReader()
                active_reader = _gate_reader
            text, confidence = _read_raw(active_reader, [text_image])[0]
            match = re.fullmatch(r'gate\s*(\d+)\s*[/|]\s*(\d+)', text, re.IGNORECASE)
            if (match and confidence >= .7
                    and 0 < int(match[1]) <= int(match[2])):
                return x, y+1, w, by-y-1
    return None


def combat_visible(original, reader=None):
    image = to_960(original)
    return gate_bar(image, reader) is not None
