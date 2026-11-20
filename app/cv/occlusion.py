"""Occlusion detection.

MediaPipe's per-landmark visibility does not detect occlusion by an external
object: in the assignment's common sample it reports visibility 1.00 for the
shoulder and nose even though both are completely hidden behind a weight
plate. So we detect occluders directly in the image.

An occluder must satisfy all of:
  * it is a large, connected dark region (at least ~2.5% of the frame) - a
    weight plate, a bench, a rack upright, a dark-clothed bystander;
  * it is very dark (mean luminance < 30);
  * the neighbourhood of the landmark inside it is smooth (local standard
    deviation < 2.0). Clothing folds and skin texture produce a higher local
    deviation, so this distinguishes a plate covering the lifter from the
    lifter simply wearing dark shorts.

Measured separation on the common sample (608x1080): the weight plate is
6.22% of the frame with local std 0.9, while the lifter's grey shorts are
1.09% with local std 3.5.

Any measurement that depends on an occluded landmark is reported as
"cannot assess" rather than with invented precision.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import cv2
import numpy as np

Point = Tuple[float, float]


class OcclusionDetector:
    """Detects large dark objects that can hide body landmarks."""

    def __init__(
        self,
        dark_threshold: int = 30,
        min_area_ratio: float = 0.025,
        max_mean_luminance: float = 30.0,
        max_local_std: float = 2.0,
        window: int = 6,
    ):
        self.dark_threshold = dark_threshold
        self.min_area_ratio = min_area_ratio
        self.max_mean_luminance = max_mean_luminance
        self.max_local_std = max_local_std
        self.window = window

    def find_occluders(self, frame: np.ndarray) -> List[np.ndarray]:
        """Return one boolean mask per large, dark, smooth region."""
        h, w = frame.shape[:2]
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        _, mask = cv2.threshold(gray, self.dark_threshold, 255, cv2.THRESH_BINARY_INV)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

        min_area = self.min_area_ratio * h * w
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        masks: List[np.ndarray] = []
        for c in contours:
            if cv2.contourArea(c) < min_area:
                continue
            m = np.zeros((h, w), dtype=np.uint8)
            cv2.drawContours(m, [c], -1, 255, thickness=cv2.FILLED)
            if gray[m > 0].mean() > self.max_mean_luminance:
                continue
            masks.append(m)
        return masks

    def is_occluded(
        self,
        masks: List[np.ndarray],
        pt: Optional[Point],
        gray: Optional[np.ndarray] = None,
    ) -> bool:
        """True when the point falls on a large dark region that is also
        locally smooth (so it is an object in front of the lifter, not their
        own clothing)."""
        if pt is None or not masks:
            return False
        x, y = int(round(pt[0])), int(round(pt[1]))
        # A landmark can sit outside the picture: MediaPipe extrapolates
        # positions for body parts that are not visible, and those positions
        # are not valid image coordinates.
        if x < 0 or y < 0:
            return False
        for m in masks:
            h, w = m.shape[:2]
            if x >= w or y >= h:
                return False
            if m[y, x] == 0:
                continue
            if gray is not None:
                w2 = self.window
                patch = gray[max(0, y - w2): y + w2 + 1, max(0, x - w2): x + w2 + 1]
                if patch.size and float(patch.std()) > self.max_local_std:
                    continue
            return True
        return False

    def frame_flags(
        self,
        frame: np.ndarray,
        landmarks: Dict[str, Optional[Point]],
    ) -> Dict[str, bool]:
        """Return {landmark_name: occluded} for the landmarks of interest."""
        masks = self.find_occluders(frame)
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        return {
            name: self.is_occluded(masks, pt, gray)
            for name, pt in landmarks.items()
        }
