"""Shared 960-wide screenshot normalization."""

import cv2


def to_960(image):
    scale = image.shape[1] / 960
    return cv2.resize(image, (960, round(image.shape[0] / scale)))
