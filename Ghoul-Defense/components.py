"""Construct shared dependencies and diagnostics without starting automation."""

from dataclasses import dataclass
import logging
from logging.handlers import RotatingFileHandler

from boss import BossTracker
from catalog import Catalog
from detector import Detector
from ocr import TextReader
from package_layout import fingerprint
from ultimate import UltimatePolicy


@dataclass
class Components:
    reader: object
    detector: object
    boss_tracker: object
    ultimate: object
    catalog: object


def build_components(root, reader=None, *, reader_factory=TextReader,
                     detector_factory=Detector, tracker_factory=BossTracker,
                     ultimate_factory=UltimatePolicy, catalog_factory=Catalog):
    shared = reader if reader is not None else reader_factory(lazy=True)
    return Components(shared, detector_factory(reader=shared), tracker_factory(reader=shared),
                      ultimate_factory(), catalog_factory(root/'catalog'))


def configure_logging(root):
    logger = logging.getLogger('ghoul')
    logger.setLevel(logging.INFO)
    handler = RotatingFileHandler(root/'macro.log', maxBytes=1_000_000,
                                  backupCount=2, encoding='utf-8')
    handler.setFormatter(logging.Formatter('%(asctime)s %(message)s'))
    logger.addHandler(handler)
    return logger, handler


def build_fingerprint(root):
    return fingerprint(root)
