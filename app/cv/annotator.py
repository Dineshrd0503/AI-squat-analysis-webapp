"""Video annotation: draw pose landmarks, bar path, rep labels, and uncertainty notes."""

from __future__ import annotations

import cv2
import math
import numpy as np
from typing import List, Optional, Tuple, Dict

# Colors (BGR)
COLOR_LANDMARK = (0, 255, 0)      # green
COLOR_SKELETON = (255, 255, 0)    # cyan
COLOR_BAR_PATH = (0, 0, 255)      # red
COLOR_BOTTOM = (0, 165, 255)      # orange
COLOR_TEXT_BG = (0, 0, 0)
COLOR_TEXT = (255, 255, 255)
COLOR_WARN = (0, 100, 255)
COLOR_MIDFOOT = (255, 200, 0)     # gold - balance point
COLOR_FLOOR = (128, 128, 128)     # grey - floor reference
COLOR_DEPTH_A = (0, 200, 255)     # depth landmark A (top of patella)
COLOR_DEPTH_B = (255, 0, 255)     # depth landmark B (hip crease apex)
COLOR_BAR_PATH_OCC = (90, 90, 90)  # grey - bar path through an occluder
COLOR_CREASE = (0, 215, 255)       # depth landmark B* - estimated crease apex
COLOR_PARALLEL = (255, 255, 255)   # the parallel reference line through A


def _dashed_line(frame, p1, p2, color, thickness=1, dash=8):
    """Draw a dashed segment between two points."""
    x1, y1 = p1
    x2, y2 = p2
    dx, dy = x2 - x1, y2 - y1
    length = math.hypot(dx, dy)
    if length < 1:
        return
    ux, uy = dx / length, dy / length
    pos = 0.0
    while pos < length:
        seg = min(dash, length - pos)
        a = (int(x1 + ux * pos), int(y1 + uy * pos))
        b = (int(x1 + ux * (pos + seg)), int(y1 + uy * (pos + seg)))
        cv2.line(frame, a, b, color, thickness, lineType=cv2.LINE_AA)
        pos += dash * 2


def draw_landmark(frame: np.ndarray, pt: Optional[Tuple[int, int]], radius: int = 4,
                  color: Tuple[int, int, int] = COLOR_LANDMARK) -> None:
    if pt is None:
        return
    cv2.circle(frame, (int(pt[0]), int(pt[1])), radius, color, -1, lineType=cv2.LINE_AA)


def draw_line(frame: np.ndarray, p1: Optional[Tuple[int, int]],
              p2: Optional[Tuple[int, int]],
              color: Tuple[int, int, int] = COLOR_SKELETON,
              thickness: int = 2) -> None:
    if p1 is None or p2 is None:
        return
    cv2.line(frame, (int(p1[0]), int(p1[1])), (int(p2[0]), int(p2[1])),
             color, thickness, lineType=cv2.LINE_AA)


def put_text(frame: np.ndarray, text: str, org: Tuple[int, int],
             font_scale: float = 0.55, color: Tuple[int, int, int] = COLOR_TEXT,
             thickness: int = 1, bg: bool = True) -> None:
    if bg:
        (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, font_scale, thickness)
        x, y = org
        cv2.rectangle(frame, (x, y - th - 4), (x + tw, y + 2), COLOR_TEXT_BG, -1)
    cv2.putText(frame, text, org, cv2.FONT_HERSHEY_SIMPLEX, font_scale, color, thickness,
                lineType=cv2.LINE_AA)


def annotate_frame(
    frame: np.ndarray,
    landmarks_px: Optional[dict],
    bar_pt: Optional[Tuple[int, int]],
    bar_history: List[Optional[Tuple[int, int]]],
    frame_idx: int,
    bottom_frames: set,
    rep_labels: Dict[int, str],
    uncertainty: List[str],
    midfoot: Optional[Tuple[int, int]] = None,
    floor: Optional[Tuple[float, float]] = None,
    bar_visible: bool = True,
    occluded: Optional[Dict[str, bool]] = None,
    crease: Optional[Tuple[int, int]] = None,
    depth_status: Optional[str] = None,
) -> np.ndarray:
    h, w = frame.shape[:2]
    overlay = frame.copy()
    occluded = occluded or {}

    # Draw the floor reference line (heel -> toe direction). The document
    # defines the back angle against the floor, so this line is shown so the
    # viewer can judge whether the torso angle is being read against it.
    if floor is not None:
        ang = math.atan2(floor[1], floor[0])
        cx = int(midfoot[0]) if midfoot else w // 2
        cy = int(midfoot[1]) if midfoot else h - 40
        L = w
        p1 = (int(cx - math.cos(ang) * L), int(cy - math.sin(ang) * L))
        p2 = (int(cx + math.cos(ang) * L), int(cy + math.sin(ang) * L))
        cv2.line(overlay, p1, p2, COLOR_FLOOR, 1, lineType=cv2.LINE_AA)

    # Draw bar path history (trajectory). Segments where the bar proxy was
    # hidden are drawn dashed so the viewer is not shown a confident-looking
    # path that is really a model guess.
    for i in range(1, len(bar_history)):
        a, b = bar_history[i - 1], bar_history[i]
        if a is None or b is None:
            continue
        a = (int(a[0]), int(a[1]))
        b = (int(b[0]), int(b[1]))
        if bar_visible and not occluded.get("bar"):
            cv2.line(overlay, a, b, COLOR_BAR_PATH, 2, lineType=cv2.LINE_AA)
        else:
            _dashed_line(overlay, a, b, COLOR_BAR_PATH_OCC, 2, dash=8)
    # Draw current bar point
    if bar_pt is not None:
        bp = (int(bar_pt[0]), int(bar_pt[1]))
        col = COLOR_BAR_PATH if (bar_visible and not occluded.get("bar")) else COLOR_BAR_PATH_OCC
        cv2.circle(overlay, bp, 5, col, -1, lineType=cv2.LINE_AA)
        cv2.circle(overlay, bp, 8, col, 2, lineType=cv2.LINE_AA)
        if occluded.get("bar"):
            put_text(overlay, "bar occluded", (bp[0] + 12, bp[1] - 8),
                     font_scale=0.4, color=COLOR_BAR_PATH_OCC, bg=False)

    # Draw the midfoot balance point (document's balance reference)
    if midfoot is not None:
        cv2.circle(overlay, (int(midfoot[0]), int(midfoot[1])), 6, COLOR_MIDFOOT, -1,
                   lineType=cv2.LINE_AA)
        cv2.circle(overlay, (int(midfoot[0]), int(midfoot[1])), 11, COLOR_MIDFOOT, 2,
                   lineType=cv2.LINE_AA)
        put_text(overlay, "midfoot", (int(midfoot[0]) + 13, int(midfoot[1]) + 4),
                 font_scale=0.4, color=COLOR_MIDFOOT, bg=False)

    # Draw skeleton + landmarks
    if landmarks_px:
        sh = landmarks_px.get("shoulder")
        hip = landmarks_px.get("hip")
        knee = landmarks_px.get("knee")
        ankle = landmarks_px.get("ankle")
        toe = landmarks_px.get("toe")

        draw_line(overlay, sh, hip)
        draw_line(overlay, hip, knee)
        draw_line(overlay, knee, ankle)
        draw_line(overlay, ankle, toe)
        for pt in [sh, hip, knee, ankle]:
            draw_landmark(overlay, pt)

        # Depth landmarks A (top of patella) and B (hip crease apex)
        if knee is not None:
            kp = (int(knee[0]), int(knee[1]))
            cv2.circle(overlay, kp, 5, COLOR_DEPTH_A, -1, lineType=cv2.LINE_AA)
            put_text(overlay, "A", (kp[0] + 6, kp[1] - 6), font_scale=0.45,
                     color=COLOR_DEPTH_A, bg=False)
        if hip is not None:
            hp_ = (int(hip[0]), int(hip[1]))
            cv2.circle(overlay, hp_, 5, COLOR_DEPTH_B, -1, lineType=cv2.LINE_AA)
            put_text(overlay, "B", (hp_[0] + 6, hp_[1] - 6), font_scale=0.45,
                     color=COLOR_DEPTH_B, bg=False)

            # The document's own depth test: the plane through A and B must
            # drop below parallel with the ground. Draw the parallel line
            # through A so the viewer can see whether B is below it.
            # Only draw a conclusion when the depth rule was actually
            # assessed - otherwise the overlay would claim a result the
            # report does not contain.
            if crease is not None and knee is not None:
                cp = (int(crease[0]), int(crease[1]))
                kp = (int(knee[0]), int(knee[1]))
                assessed = depth_status in ("meets standard", "does not meet standard")
                if assessed:
                    cv2.circle(overlay, cp, 6, COLOR_CREASE, -1, lineType=cv2.LINE_AA)
                    cv2.circle(overlay, cp, 11, COLOR_CREASE, 2, lineType=cv2.LINE_AA)
                    put_text(overlay, "B*", (cp[0] + 13, cp[1] + 4), font_scale=0.45,
                             color=COLOR_CREASE, bg=False)
                    cv2.line(overlay, (0, kp[1]), (w, kp[1]), COLOR_PARALLEL, 1,
                             lineType=cv2.LINE_AA)
                    below = cp[1] > kp[1]
                    put_text(overlay, "parallel (through A)", (w - 175, kp[1] - 6),
                             font_scale=0.42, color=COLOR_PARALLEL, bg=False)
                    put_text(overlay,
                             "B* BELOW parallel - depth reached" if below else
                             "B* ABOVE parallel - depth not reached",
                             (w - 300, kp[1] + 16), font_scale=0.46,
                             color=COLOR_CREASE if below else COLOR_BOTTOM, thickness=1)
                else:
                    put_text(overlay, "depth not assessed", (w - 300, kp[1] + 16),
                             font_scale=0.46, color=COLOR_WARN, thickness=1)

        # Highlight bottom position
        if frame_idx in bottom_frames and hip is not None:
            hp_ = (int(hip[0]), int(hip[1]))
            cv2.circle(overlay, hp_, 10, COLOR_BOTTOM, 2, lineType=cv2.LINE_AA)
            put_text(overlay, "BOTTOM", (hp_[0] - 20, hp_[1] - 15), font_scale=0.5,
                     color=COLOR_BOTTOM)

        # Rep label
        if frame_idx in rep_labels:
            put_text(overlay, rep_labels[frame_idx], (10, 30), font_scale=0.7,
                     color=(0, 255, 0), thickness=2)

    # Uncertainty banner (top-right)
    if uncertainty:
        y = 30
        for note in uncertainty[:3]:
            put_text(overlay, "! " + note, (w - 340, y), font_scale=0.45,
                     color=COLOR_WARN, thickness=1)
            y += 20

    return overlay


def build_uncertainty_notes(findings: List[dict]) -> List[str]:
    notes = [
        "Horizontal reference estimated from the heel-to-toe line; if the lifter "
        "is filmed from a three-quarter angle the room may still look tilted.",
    ]
    for f in findings:
        if f["status"] == "cannot assess":
            notes.append(f"{f['rule_id']}: {f['rule']} — cannot assess from side view")
    notes.append("Barbell tracked via wrist proxy (approx.).")
    notes.append("Depth reported in pixels; absolute cm needs calibration.")
    return notes
