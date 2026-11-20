"""Measurement extraction for squat assessment.

All geometry is computed in a *gravity-aligned* frame. The document defines
the back angle against the floor (reference p9) and depth against "parallel
with the ground" (reference p2), so a tilted camera must be corrected before
any of those numbers mean anything.

Two corrections are applied and both are disclosed in the output:

1. **Camera roll.** The floor direction is estimated from the heel-to-toe line
   (the document states the feet are flat on the ground, reference p22) and
   the median over the recording is used. Every landmark is then rotated so
   that the floor is horizontal and image-down equals gravity-down.

2. **Hip landmark.** The document identifies depth landmark B as "the hip
   joint, as identified by the apex in the crease of the shorts" (reference
   p2). MediaPipe reports the anatomical hip joint, which sits above the
   crease apex, so the crease apex is estimated a fixed fraction of the torso
   length below the joint. That fraction is an application assumption.
"""

from __future__ import annotations

import math
from statistics import median
from typing import Dict, List, Optional, Tuple

Point = Tuple[float, float]

# Fraction of the shoulder-to-hip length used to estimate the crease apex
# below the anatomical hip joint. Application assumption, not a document value.
CREASE_OFFSET_RATIO = 0.16


def _unit(a: Point, b: Point) -> Optional[Tuple[float, float]]:
    dx, dy = b[0] - a[0], b[1] - a[1]
    n = math.hypot(dx, dy)
    if n < 1e-6:
        return None
    return dx / n, dy / n


# ---------------------------------------------------------------------------
# Camera roll
# ---------------------------------------------------------------------------

def estimate_roll(frames: List[Dict[str, Optional[Point]]]) -> Tuple[float, float, float]:
    """Estimate the camera roll from the heel-to-toe line.

    Returns (roll_radians, facing, spread_radians) where facing is +1 when
    the lifter faces the right of the image and -1 when they face the left, and
    spread is the median absolute deviation of the per-frame angles.

    The foot line is only a valid roll reference when the foot is roughly
    perpendicular to the camera axis. When the lifter is filmed from a
    three-quarter angle the projected foot line is tilted by more than the
    camera roll, and the spread grows. Callers use the spread to report how
    sensitive the vertical measurements are to this estimate.
    """
    angles: List[float] = []
    facing_votes: List[float] = []
    for f in frames:
        heel, toe = f.get("heel"), f.get("toe")
        if not heel or not toe:
            continue
        dx, dy = toe[0] - heel[0], toe[1] - heel[1]
        if math.hypot(dx, dy) < 12:
            continue  # too foreshortened to trust the direction
        ang = math.atan2(dy, dx)
        # Map the line's angle into [-90, 90) so the sign is the tilt only.
        ang = ((ang + math.pi / 2) % math.pi) - math.pi / 2
        angles.append(ang)
        facing_votes.append(1.0 if dx >= 0 else -1.0)
    if not angles:
        return 0.0, 1.0, math.radians(6.0)
    roll = median(angles)
    spread = median([abs(a - roll) for a in angles])
    facing = 1.0 if sum(facing_votes) >= 0 else -1.0
    return roll, facing, spread


def rotate_point(p: Optional[Point], theta: float, cx: float, cy: float) -> Optional[Point]:
    """Rotate a point about (cx, cy) by theta radians."""
    if p is None:
        return None
    x, y = p[0] - cx, p[1] - cy
    c, s = math.cos(theta), math.sin(theta)
    return (cx + x * c - y * s, cy + x * s + y * c)


def rotate_frames(
    frames: List[Dict[str, Optional[Point]]],
    theta: float,
    cx: float,
    cy: float,
) -> List[Dict[str, Optional[Point]]]:
    """Rotate every landmark in every frame into the gravity-aligned frame."""
    out = []
    for f in frames:
        g = {}
        for k, v in f.items():
            if k == "bar":
                g[k] = rotate_point(v, theta, cx, cy)
            else:
                g[k] = rotate_point(v, theta, cx, cy)
        out.append(g)
    return out


# ---------------------------------------------------------------------------
# Angles in the gravity-aligned frame
# ---------------------------------------------------------------------------

def back_angle_deg(shoulder: Optional[Point], hip: Optional[Point]) -> Optional[float]:
    """Angle between the plane of the torso and the floor.

    In the gravity-aligned frame the floor is horizontal, so this is simply
    the angle of the torso away from vertical: 90 deg = vertical torso,
    45 deg = the inclined torso the document describes (reference p22).
    """
    if shoulder is None or hip is None:
        return None
    torso = _unit(hip, shoulder)
    if torso is None:
        return None
    # Angle from vertical: vertical-up is (0, -1) in image coordinates.
    cos_to_vertical = abs(torso[0] * 0.0 + torso[1] * -1.0)
    cos_to_vertical = min(1.0, max(-1.0, cos_to_vertical))
    from_vertical = math.degrees(math.acos(cos_to_vertical))
    return 90.0 - from_vertical


def angle_at(a: Point, b: Point, c: Point) -> float:
    """Interior angle ABC at point b, in degrees."""
    u = (a[0] - b[0], a[1] - b[1])
    v = (c[0] - b[0], c[1] - b[1])
    nu, nv = math.hypot(*u), math.hypot(*v)
    if nu < 1e-6 or nv < 1e-6:
        return 0.0
    cos = (u[0] * v[0] + u[1] * v[1]) / (nu * nv)
    return math.degrees(math.acos(min(1.0, max(-1.0, cos))))


def hip_angle_deg(shoulder: Point, hip: Point, knee: Point) -> float:
    """Angle formed by the plane of the torso and the femur (reference p9)."""
    return angle_at(shoulder, hip, knee)


def knee_angle_deg(hip: Point, knee: Point, ankle: Point) -> float:
    """Angle formed by the femur and the tibia (reference p9)."""
    return angle_at(hip, knee, ankle)


def head_pitch_deg(nose: Optional[Point], ear: Optional[Point]) -> Optional[float]:
    """How far the nose points downward, in degrees.

    In a side view the ear-to-nose axis is roughly horizontal when the head is
    upright and points downward as the chin drops. Positive = chin down
    (looking down), negative = looking up.
    """
    if nose is None or ear is None:
        return None
    axis = (nose[0] - ear[0], nose[1] - ear[1])
    n = math.hypot(*axis)
    if n < 1e-6:
        return None
    axis = (axis[0] / n, axis[1] / n)
    # Gravity-down in the aligned frame is (0, +1).
    down = axis[1]
    down = min(1.0, max(-1.0, down))
    return math.degrees(math.asin(down))


def midfoot(heel: Optional[Point], toe: Optional[Point]) -> Optional[Point]:
    """The document's balance point: halfway between heel and toe (reference p8)."""
    if heel is None or toe is None:
        return None
    return ((heel[0] + toe[0]) / 2.0, (heel[1] + toe[1]) / 2.0)


def crease_apex(
    hip: Optional[Point],
    shoulder: Optional[Point],
    ratio: float = CREASE_OFFSET_RATIO,
) -> Optional[Point]:
    """Estimate the document's depth landmark B (the apex in the crease of the
    shorts) from the anatomical hip joint landmark.

    The crease apex lies below the hip joint along gravity. The offset is
    taken as `ratio` times the shoulder-to-hip length; that ratio is an
    application assumption, disclosed in the report.
    """
    if hip is None or shoulder is None:
        return None
    torso = math.hypot(shoulder[0] - hip[0], shoulder[1] - hip[1])
    if torso < 1e-6:
        return None
    d = torso * ratio
    return (hip[0], hip[1] + d)  # +y is gravity-down in the aligned frame
