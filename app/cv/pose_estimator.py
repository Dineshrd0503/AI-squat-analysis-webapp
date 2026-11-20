"""Pose estimation using MediaPipe Tasks PoseLandmarker.

Extracts key body landmarks (hips, knees, ankles, shoulders, wrists) per frame
and returns them as normalized (0..1) image coordinates plus pixel coordinates.

Falls back gracefully if the task model is unavailable, in which case every
frame reports ``None`` (no pose) and the pipeline still runs, producing
``cannot assess`` findings.
"""

from __future__ import annotations

import os
from typing import Dict, Optional, Tuple

import cv2
import numpy as np

try:
    import mediapipe as mp
    from mediapipe.tasks import python
    from mediapipe.tasks.python import vision
    _TASKS_AVAILABLE = True
except Exception:  # pragma: no cover - environment without mediapipe tasks
    _TASKS_AVAILABLE = False

# MediaPipe pose landmark indices (BlazePose / PoseLandmarker, 33 landmarks)
NOSE = 0
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12
LEFT_HIP = 23
RIGHT_HIP = 24
LEFT_KNEE = 25
RIGHT_KNEE = 26
LEFT_ANKLE = 27
RIGHT_ANKLE = 28
LEFT_WRIST = 15
RIGHT_WRIST = 16
LEFT_HEEL = 29
RIGHT_HEEL = 30
LEFT_FOOT_INDEX = 31
RIGHT_FOOT_INDEX = 32
NOSE = 0
LEFT_EAR = 7
RIGHT_EAR = 8

REQUIRED = [
    LEFT_SHOULDER, RIGHT_SHOULDER,
    LEFT_HIP, RIGHT_HIP,
    LEFT_KNEE, RIGHT_KNEE,
    LEFT_ANKLE, RIGHT_ANKLE,
    LEFT_WRIST, RIGHT_WRIST,
    LEFT_HEEL, RIGHT_HEEL,
    LEFT_FOOT_INDEX, RIGHT_FOOT_INDEX,
]

_MODEL_NAME = "pose_landmarker_lite.task"


def _default_model_path() -> Optional[str]:
    here = os.path.dirname(__file__)
    candidate = os.path.join(here, "..", "models", _MODEL_NAME)
    candidate = os.path.abspath(candidate)
    return candidate if os.path.exists(candidate) else None


class PoseEstimator:
    """Wrapper around MediaPipe Tasks PoseLandmarker for squat-relevant landmarks."""

    def __init__(self, model_path: Optional[str] = None):
        self.model_path = model_path or _default_model_path()
        self.detector = None
        self.available = False
        if not _TASKS_AVAILABLE:
            return
        if not self.model_path or not os.path.exists(self.model_path):
            return
        try:
            base_options = python.BaseOptions(model_asset_path=self.model_path)
            options = vision.PoseLandmarkerOptions(
                base_options=base_options,
                running_mode=vision.RunningMode.VIDEO,
            )
            self.detector = vision.PoseLandmarker.create_from_options(options)
            self.available = True
        except Exception:  # pragma: no cover - model load failure
            self.detector = None
            self.available = False

    def estimate(
        self,
        frame_bgr: np.ndarray,
        timestamp_ms: float = 0.0,
    ) -> Optional[Dict[str, Tuple[float, float, float]]]:
        """Return landmarks as {name: (x, y, z)} in normalized coords, or None."""
        if not self.available or self.detector is None:
            return None
        rgb = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2RGB)
        mp_image = mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb)
        try:
            result = self.detector.detect_for_video(mp_image, int(timestamp_ms))
        except Exception:
            return None
        if not result.pose_landmarks:
            return None
        # pose_landmarks is a list of detected people; take the first (most prominent).
        landmarks = result.pose_landmarks[0]
        name_map = {
            LEFT_SHOULDER: "left_shoulder",
            RIGHT_SHOULDER: "right_shoulder",
            LEFT_HIP: "left_hip",
            RIGHT_HIP: "right_hip",
            LEFT_KNEE: "left_knee",
            RIGHT_KNEE: "right_knee",
            LEFT_ANKLE: "left_ankle",
            RIGHT_ANKLE: "right_ankle",
            LEFT_WRIST: "left_wrist",
            RIGHT_WRIST: "right_wrist",
            LEFT_HEEL: "left_heel",
            RIGHT_HEEL: "right_heel",
            LEFT_FOOT_INDEX: "left_foot_index",
            RIGHT_FOOT_INDEX: "right_foot_index",
            NOSE: "nose",
            LEFT_EAR: "left_ear",
            RIGHT_EAR: "right_ear",
        }
        out: Dict[str, Tuple[float, float, float]] = {}
        for idx, name in name_map.items():
            if idx < len(landmarks):
                p = landmarks[idx]
                out[name] = (p.x, p.y, p.z)
        # Core landmarks (torso/legs) are required; heel/toe are optional because
        # they are frequently invisible when the lifter wears shoes or when the
        # foot is occluded. Their absence downgrades midfoot-based rules to
        # "cannot assess" rather than failing the whole frame.
        core = ("left_shoulder", "right_shoulder", "left_hip", "right_hip",
                "left_knee", "right_knee", "left_ankle", "right_ankle")
        if not all(k in out for k in core):
            return None
        return out

    def close(self):
        if self.detector is not None:
            try:
                self.detector.close()
            except Exception:
                pass


def to_pixel(norm: Tuple[float, float, float], width: int, height: int) -> Tuple[int, int]:
    """Convert normalized (x, y) to pixel coordinates."""
    return int(norm[0] * width), int(norm[1] * height)


def to_pixel_in_frame(
    norm: Optional[Tuple[float, float, float]],
    width: int,
    height: int,
    margin: float = 0.0,
) -> Optional[Tuple[int, int]]:
    """Convert normalized (x, y) to pixels, or return None when the landmark
    falls outside the picture.

    MediaPipe does not clip its output: when part of the body is outside the
    frame it extrapolates, and the normalised coordinates can exceed 1.0
    considerably (values past 1.5 are seen in practice). Such a position is a
    model guess rather than an observation, so it is discarded rather than
    measured against.
    """
    if norm is None:
        return None
    x = norm[0] * width
    y = norm[1] * height
    if x < -margin or x > width + margin or y < -margin or y > height + margin:
        return None
    return int(x), int(y)


def pick_side(
    landmarks: Dict[str, Tuple[float, float, float]],
    left_key: str,
    right_key: str,
    width: int,
) -> Optional[Tuple[float, float, float]]:
    """For sagittal-plane metrics, average the symmetric left/right pair."""
    l = landmarks.get(left_key)
    r = landmarks.get(right_key)
    if l is None and r is None:
        return None
    if l is None:
        return r
    if r is None:
        return l
    return ((l[0] + r[0]) / 2.0, (l[1] + r[1]) / 2.0, (l[2] + r[2]) / 2.0)
