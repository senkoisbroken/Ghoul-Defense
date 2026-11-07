"""Persist offered perk and relic cards once per normalized name."""

from pathlib import Path

import cv2

from ghoul import canonical, clean

FOLDERS = {'perk': 'perks', 'relic': 'relics'}


def valid_image(image):
    shape = getattr(image, 'shape', None)
    return (
        shape is not None
        and len(shape) == 3
        and shape[0] > 0
        and shape[1] > 0
        and shape[2] >= 3
    )


def crop_card(image, rect):
    """Return the requested BGR crop, or None when the rectangle is unusable."""
    try:
        x, y, width, height = (int(value) for value in rect)
    except (TypeError, ValueError):
        return None
    if width <= 0 or height <= 0 or x < 0 or y < 0:
        return None
    if x + width > image.shape[1] or y + height > image.shape[0]:
        return None
    crop = image[y:y + height, x:x + width]
    if crop.size == 0 or crop.shape[0] == 0 or crop.shape[1] == 0:
        return None
    return crop


class Catalog:
    def __init__(self, folder):
        self.folder = Path(folder)

    def save(self, image, decision):
        subfolder = FOLDERS.get(getattr(decision, 'kind', None))
        if subfolder is None or not valid_image(image):
            return []
        saved = []
        for name, rect in getattr(decision, 'cards', ()) or ():
            if not isinstance(name, str):
                continue
            key = clean(canonical(name))
            crop = crop_card(image, rect) if key else None
            if crop is None:
                continue
            path = self.folder / subfolder / (key + '.png')
            if path.exists():
                continue
            try:
                ok, encoded = cv2.imencode('.png', crop)
            except cv2.error:
                continue
            if not ok:
                continue
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                # Exclusive creation preserves any image already on disk.
                with open(path, 'xb') as handle:
                    handle.write(encoded.tobytes())
            except FileExistsError:
                continue
            saved.append(str(path))
        return saved
