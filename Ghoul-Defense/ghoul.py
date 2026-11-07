"""Compatibility exports for existing macros, tests and manual probes."""

from names import NAMES, CANONICAL, clean, canonical, priority, choose
from ocr import TextReader
from ocr import _read_raw as _read_raw, _read_names as _read_names
from detector import (Detector, Decision, ui_scale_candidates, REFERENCE_WIDTH,
                      REFERENCE_HEIGHT, MIN_UI_SCALE, MAX_UI_SCALE, ROOT)
from frame import to_960
import gate as _gate

_gate_reader = None

__all__ = [
    'NAMES', 'CANONICAL', 'clean', 'canonical', 'priority', 'choose',
    'TextReader', 'Detector', 'Decision', 'ui_scale_candidates',
    'REFERENCE_WIDTH', 'REFERENCE_HEIGHT', 'MIN_UI_SCALE', 'MAX_UI_SCALE',
    'ROOT', 'gate_bar', 'combat_visible',
]


def gate_bar(image, reader=None):
    global _gate_reader
    active = reader if reader is not None else _gate_reader
    result = _gate.gate_bar(image, reader=active)
    if reader is None and _gate_reader is None:
        _gate_reader = _gate._gate_reader
    return result


def combat_visible(original, reader=None):
    return gate_bar(to_960(original), reader=reader) is not None
