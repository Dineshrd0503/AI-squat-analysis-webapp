"""Viewpoint classification.

The assignment specifies side-view recordings, and the document's criteria
are all defined in the sagittal plane. Feeding a front or rear view into the
sagittal rules produces confident-looking but meaningless numbers, so the
recording is classified first and non-side-view footage is reported as
"cannot assess" instead.

Two independent signals are used:

1. **Limb separation.** In a side view the left and right legs project to
   nearly the same place on screen (they are separated by the depth of the
   feet), so the horizontal distance between the two ankles is small relative
   to the length of the torso. In a front or rear view the two ankles are
   separated by roughly the stance width, which is comparable to the torso
   length.

2. **Foot line direction.** In a side view the heel-to-toe line lies roughly
   along the floor, so it is close to horizontal in the image. Seen from the
   front the foot points at the camera, so the line is foreshortened and
   points mostly vertically.
"""

from __future__ import annotations

import math
from statistics import median
from typing import Dict, List, Optional, Tuple

Point = Tuple[float, float]


def classify_view(
    frames: List[Dict[str, Optional[Point]]],
    ankle_sep: List[Optional[float]] = None,
    shoulder_sep: List[Optional[float]] = None,
) -> Dict[str, object]:
    """Classify the camera viewpoint of a recording.

    Returns a dict with:
        view: "side_view" | "not_side_view" | "unknown"
        reason: short human-readable explanation
        evidence: the measurements the decision was based on
        note: a caveat that should be surfaced with the result
    """
    seps: List[float] = []
    sh_seps: List[float] = []
    torso_lens: List[float] = []
    foot_angles: List[float] = []

    for i, f in enumerate(frames):
        sh, hp = f.get("shoulder"), f.get("hip")
        if sh and hp:
            d = math.hypot(sh[0] - hp[0], sh[1] - hp[1])
            if d > 1:
                torso_lens.append(d)

        if ankle_sep is not None and i < len(ankle_sep) and ankle_sep[i] is not None:
            seps.append(ankle_sep[i])
        if shoulder_sep is not None and i < len(shoulder_sep) and shoulder_sep[i] is not None:
            sh_seps.append(shoulder_sep[i])

        heel, toe = f.get("heel"), f.get("toe")
        if heel and toe:
            dx, dy = toe[0] - heel[0], toe[1] - heel[1]
            if math.hypot(dx, dy) > 8:
                ang = math.degrees(math.atan2(dy, dx))
                ang = ((ang + 90) % 180) - 90  # tilt from horizontal in [-90, 90]
                foot_angles.append(abs(ang))

    evidence: Dict[str, object] = {
        "median_ankle_separation_px": round(median(seps), 1) if seps else None,
        "median_shoulder_separation_px": round(median(sh_seps), 1) if sh_seps else None,
        "median_torso_length_px": round(median(torso_lens), 1) if torso_lens else None,
        "median_foot_line_tilt_deg": round(median(foot_angles), 1) if foot_angles else None,
    }

    torso = median(torso_lens) if torso_lens else 0.0
    ratio = None
    if seps and torso > 0:
        ratio = median(seps) / torso
        evidence["ankle_separation_over_torso"] = round(ratio, 3)
    sh_ratio = None
    if sh_seps and torso > 0:
        sh_ratio = median(sh_seps) / torso
        evidence["shoulder_separation_over_torso"] = round(sh_ratio, 3)

    # Not enough evidence either way.
    if ratio is None and evidence["median_foot_line_tilt_deg"] is None:
        return {
            "view": "unknown",
            "reason": "not enough tracking data to classify the viewpoint",
            "evidence": evidence,
            "note": "The viewpoint could not be established, so sagittal criteria may be unreliable.",
        }

    # A foot line that is steeply tilted means we are not looking at the
    # lifter from the side.
    steep_foot = (evidence["median_foot_line_tilt_deg"] is not None
                  and evidence["median_foot_line_tilt_deg"] > 55)

    # Wide limb separation means we are looking at the lifter from the front
    # or the back, or from an oblique angle between the two.
    wide_limbs = ratio is not None and ratio > 0.09
    wide_shoulders = sh_ratio is not None and sh_ratio > 0.25

    if steep_foot or wide_limbs or wide_shoulders:
        why = []
        if wide_shoulders:
            why.append("the left and right shoulders are separated by "
                       f"{sh_ratio:.2f} of the torso length in the image")
        if wide_limbs:
            why.append("the left and right legs are separated by "
                       f"{ratio:.2f} of the torso length in the image")
        if steep_foot:
            why.append("the heel-to-toe line is "
                       f"{evidence['median_foot_line_tilt_deg']:.0f} degrees from horizontal")
        return {
            "view": "not_side_view",
            "reason": "; ".join(why),
            "evidence": evidence,
            "note": ("This recording does not appear to be a side view. The document's criteria are "
                     "defined in the sagittal plane, so the depth, torso-angle, knee-position and "
                     "bar-path criteria cannot be evaluated from this angle. Stance width, toe angle "
                     "and knee tracking can be, but are reported as cannot assess throughout."),
        }

    return {
        "view": "side_view",
        "reason": "consistent with a side-on recording",
        "evidence": evidence,
        "note": None,
    }
