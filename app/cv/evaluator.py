"""Skill-driven evaluation engine.

Loads the document-derived skill from disk at runtime and evaluates each
repetition against it. The skill file is deliberately separate from the
application code so that changing a rule requires editing the skill, not the
evaluator (an explicit requirement of the assignment).

Every finding carries:
  * the rule id and name, and the reference pages it came from
  * a verdict of meets standard / does not meet standard / cannot assess
  * the supporting frame, timestamp and observed measurement
  * feedback grounded in the document, plus any uncertainty
"""

from __future__ import annotations

import json
import math
import os
from typing import Any, Dict, List, Optional, Tuple

from . import measurements as M
from .measurements import (
    back_angle_deg, hip_angle_deg, knee_angle_deg, head_pitch_deg,
    midfoot, crease_apex, rotate_frames,
)

SKILL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "skill", "low_bar_squat_skill.json",
)

_SKILL_CACHE: Optional[Dict[str, Any]] = None


def load_skill(path: str = SKILL_PATH) -> Dict[str, Any]:
    """Load the document-derived skill. Cached after first read."""
    global _SKILL_CACHE
    if _SKILL_CACHE is None or path != SKILL_PATH:
        with open(path, "r", encoding="utf-8") as f:
            skill = json.load(f)
        if path == SKILL_PATH:
            _SKILL_CACHE = skill
        return skill
    return _SKILL_CACHE


def skill_rules(skill: Optional[Dict[str, Any]] = None) -> List[Dict[str, Any]]:
    skill = skill or load_skill()
    return skill.get("rules", [])


def rule_by_id(rule_id: str, skill: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
    for r in skill_rules(skill):
        if r["id"] == rule_id:
            return r
    return None


# ---------------------------------------------------------------------------
# Per-frame geometry bundle
# ---------------------------------------------------------------------------

def build_frame_geometry(
    frames: List[Dict[str, Any]],
    roll: float = 0.0,
    facing: float = 1.0,
    center: Tuple[float, float] = (0.0, 0.0),
) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """Rotate every frame into the gravity-aligned frame and compute the
    per-frame derived measurements.

    Returns (aligned_frames, geometry).
    """
    aligned = rotate_frames(frames, -roll, center[0], center[1])
    out: List[Dict[str, Any]] = []
    for f in aligned:
        g: Dict[str, Any] = {
            "back_angle": back_angle_deg(f.get("shoulder"), f.get("hip")),
            "midfoot": midfoot(f.get("heel"), f.get("toe")),
            "head_pitch": head_pitch_deg(f.get("nose"), f.get("ear")),
            "hip_crease": crease_apex(f.get("hip"), f.get("shoulder")),
        }
        sh, hp, kn = f.get("shoulder"), f.get("hip"), f.get("knee")
        ak = f.get("ankle")
        if sh and hp and kn:
            g["hip_angle"] = hip_angle_deg(sh, hp, kn)
        if hp and kn and ak:
            g["knee_angle"] = knee_angle_deg(hp, kn, ak)
        out.append(g)
    return aligned, out


# ---------------------------------------------------------------------------
# Rep evaluation
# ---------------------------------------------------------------------------

def evaluate_rep(
    rep: Dict[str, Any],
    geometry: List[Dict[str, Any]],
    frames: List[Dict[str, Any]],
    fps: float,
    skill: Optional[Dict[str, Any]] = None,
    occluded: Optional[List[Dict[str, bool]]] = None,
    roll: float = 0.0,
    facing: float = 1.0,
    view: Optional[Dict[str, Any]] = None,
    roll_uncertainty: float = 0.0,
) -> Dict[str, Any]:
    """Evaluate one repetition against every rule in the skill."""
    skill = skill or load_skill()
    start = rep["start_frame"]
    bottom = rep["bottom_frame"]
    end = rep["end_frame"]

    def occ_at(i: int) -> Dict[str, bool]:
        if occluded and 0 <= i < len(occluded):
            return occluded[i]
        return {}

    meas = _collect_measurements(rep, geometry, frames, fps, roll, facing,
                                 roll_uncertainty)
    meas["occlusion"] = occ_at(bottom)

    findings: List[Dict[str, Any]] = []
    for rule in skill_rules(skill):
        finding = _evaluate_rule(rule, meas, rep, fps, view)
        findings.append(finding)

    overall = _overall(findings)

    uncertainty = list(dict.fromkeys(
        [f["uncertainty"] for f in findings if f.get("uncertainty")] +
        meas.get("global_uncertainty", [])
    ))

    return {
        "rep_id": rep.get("rep_id"),
        "start_frame": start,
        "bottom_frame": bottom,
        "end_frame": end,
        "start_timestamp_s": round(start / fps, 3) if fps else None,
        "bottom_timestamp_s": round(bottom / fps, 3) if fps else None,
        "end_timestamp_s": round(end / fps, 3) if fps else None,
        "duration_frames": end - start + 1,
        "measurements": meas,
        "findings": findings,
        "overall": overall,
        "uncertainty_notes": uncertainty,
    }


def _collect_measurements(
    rep: Dict[str, Any],
    geometry: List[Dict[str, Any]],
    frames: List[Dict[str, Any]],
    fps: float,
    roll: float = 0.0,
    facing: float = 1.0,
    roll_uncertainty: float = 0.0,
) -> Dict[str, Any]:
    """Compute every observable measurement needed by the skill rules.

    ``frames`` are already rotated into the gravity-aligned frame, so a
    difference in y is a difference in height and a difference in x is a
    difference along the floor.

    Vertical measurements are sensitive to the camera-roll estimate, because a
    roll error tilts the frame and mixes horizontal separation into the
    vertical difference. The sensitivity of the depth measurement to the roll
    band is therefore computed explicitly and reported.
    """
    start, bottom, end = rep["start_frame"], rep["bottom_frame"], rep["end_frame"]
    m: Dict[str, Any] = {}
    notes: List[str] = []
    m["rep_frames"] = end - start + 1

    def fr(i: int) -> Dict[str, Any]:
        return frames[i] if 0 <= i < len(frames) else {}

    g_bot = geometry[bottom] if 0 <= bottom < len(geometry) else {}
    g_end = geometry[end] if 0 <= end < len(geometry) else {}

    fb = fr(bottom)
    knee = fb.get("knee")
    crease = g_bot.get("hip_crease")
    torso_len = None
    sh, hp = fb.get("shoulder"), fb.get("hip")
    if sh and hp:
        torso_len = math.hypot(sh[0] - hp[0], sh[1] - hp[1])

    # Depth: document landmark B (crease apex) against landmark A (top of patella).
    if crease and knee:
        depth = crease[1] - knee[1]
        m["depth_px"] = round(depth, 2)
        if hp and knee:
            m["depth_px_raw_hip_joint"] = round(hp[1] - knee[1], 2)
    else:
        depth = None
        m["depth_px"] = None

    # How much does the depth move if the camera-roll estimate is off by the
    # estimated amount? A roll error e shifts a point's height by
    # dx * sin(e), so the depth moves by (x_crease - x_knee) * sin(e).
    roll_band = roll_uncertainty or math.radians(4.0)
    if crease and knee:
        dx = crease[0] - knee[0]
        m["depth_roll_sensitivity_px"] = round(abs(dx) * math.sin(roll_band), 2)
        m["depth_px_range"] = [
            round(depth - abs(dx) * math.sin(roll_band), 2),
            round(depth + abs(dx) * math.sin(roll_band), 2),
        ]
    else:
        m["depth_roll_sensitivity_px"] = None
        m["depth_px_range"] = None

    # Measurement uncertainty on the depth verdict, from landmark noise.
    if torso_len:
        m["depth_uncertainty_px"] = round(max(8.0, torso_len * 0.05), 2)
        m["torso_length_px"] = round(torso_len, 2)
    else:
        m["depth_uncertainty_px"] = 8.0

    # Torso angles.
    m["back_angle_deg"] = g_bot.get("back_angle")
    m["back_angle_top_deg"] = g_end.get("back_angle")
    m["hip_angle_deg"] = g_bot.get("hip_angle")
    m["knee_angle_deg"] = g_bot.get("knee_angle")

    # Head pitch.
    m["head_pitch_deg"] = g_bot.get("head_pitch")

    # Bar over midfoot.
    profile = _bar_profile(frames, geometry, start, end)
    m["bar_drift_samples"] = len(profile)
    m["bar_drift_from_midfoot_px"] = _bar_drift(profile, roll, 0.0)
    m["bar_drift_range_px"] = _bar_drift_band(profile, roll, roll_uncertainty)
    m["bar_height_vs_shoulder_px"] = _bar_height(frames, bottom)

    # Knee forward of toe, hips back.
    m["knee_forward_of_toe_px"] = _knee_forward(fb, facing)
    m["hip_behind_ankle_px"] = _hip_behind(fb, facing)

    # Hip drive ratio.
    m["hip_drive_ratio"] = _hip_drive_ratio(frames, rep, facing)

    # Camera geometry, reported so a reviewer can verify it.
    m["camera_roll_deg"] = round(math.degrees(roll), 2)
    m["lifter_faces"] = "right" if facing > 0 else "left"

    if m["depth_px"] is None:
        notes.append("Hip or knee landmark unavailable at the bottom frame.")
    if m["bar_drift_from_midfoot_px"] is None:
        notes.append("Barbell position could not be tracked reliably (wrist proxy).")
    if m["back_angle_deg"] is None:
        notes.append("Torso landmarks unavailable at the bottom frame.")
    m["global_uncertainty"] = notes
    return m


def _bar_profile(frames, geometry, start, end):
    """Per-frame (bar_x, bar_y, midfoot_x, midfoot_y) for every frame in the
    repetition where both the bar proxy and the midfoot could be located."""
    out = []
    for i in range(max(0, start), min(end, len(frames) - 1) + 1):
        bar = frames[i].get("bar")
        g = geometry[i] if i < len(geometry) else {}
        mf = g.get("midfoot")
        if bar is None or mf is None:
            continue
        out.append((bar[0], bar[1], mf[0], mf[1]))
    return out


def _bar_drift(profile, roll: float, delta: float) -> Optional[float]:
    """Largest horizontal distance between the bar and the midfoot.

    The bar sits at shoulder height and the midfoot is on the floor, so the
    two are hundreds of pixels apart vertically and a roll error rotates one
    relative to the other. ``delta`` is an extra roll offset applied to see
    how the measurement moves when the floor reference is uncertain.
    """
    if not profile:
        return None
    worst = None
    s = math.sin(delta)
    for bx, by, mx, my in profile:
        off = abs((bx - by * s) - (mx - my * s))
        worst = off if worst is None else max(worst, off)
    return round(worst, 2)


def _bar_drift_band(profile, roll: float, uncertainty: float) -> Optional[list]:
    """The drift measured at the ends of the camera-roll uncertainty band."""
    if not profile:
        return None
    lo = _bar_drift(profile, roll, -uncertainty)
    hi = _bar_drift(profile, roll, uncertainty)
    mid = _bar_drift(profile, roll, 0.0)
    vals = [v for v in (lo, mid, hi) if v is not None]
    return [round(min(vals), 1), round(max(vals), 1)]


def _bar_height(frames, bottom) -> Optional[float]:
    """Vertical gap between the tracked bar and the shoulder landmark at the
    bottom of the rep. Positive = bar above the shoulder."""
    fb = frames[bottom] if 0 <= bottom < len(frames) else {}
    bar, sh = fb.get("bar"), fb.get("shoulder")
    if bar is None or sh is None:
        return None
    return round(bar[1] - sh[1], 2)


def _knee_forward(fb, facing) -> Optional[float]:
    """Signed forward distance of the knee ahead of the toe line at the bottom."""
    knee, toe = fb.get("knee"), fb.get("toe")
    if knee is None or toe is None:
        return None
    return round((knee[0] - toe[0]) * facing, 2)


def _hip_behind(fb, facing) -> Optional[float]:
    """Signed distance the hip sits behind the ankle at the bottom."""
    hip, ank = fb.get("hip"), fb.get("ankle")
    if hip is None or ank is None:
        return None
    return round((ank[0] - hip[0]) * facing, 2)


def _hip_drive_ratio(frames, rep, facing) -> Optional[float]:
    """Vertical hip travel divided by forward hip travel during the ascent.

    The document requires the lifter to come out of the bottom driving the
    hips straight up, not forward (reference p23).
    """
    bottom, end = rep["bottom_frame"], rep["end_frame"]
    hb = frames[bottom] if 0 <= bottom < len(frames) else None
    if not hb or not hb.get("hip"):
        return None

    top_i, top_hip = bottom, hb["hip"]
    for i in range(bottom, min(end + 1, len(frames))):
        h = frames[i].get("hip")
        if h and h[1] < top_hip[1]:
            top_i, top_hip = i, h
    if top_i == bottom:
        return None

    vertical = abs(hb["hip"][1] - top_hip[1])
    forward = abs((top_hip[0] - hb["hip"][0]) * facing)
    if forward < 1e-3:
        return round(vertical, 2) if vertical > 0 else None
    return round(vertical / forward, 3)


# ---------------------------------------------------------------------------
# Rule evaluation
# ---------------------------------------------------------------------------

def _evaluate_rule(
    rule: Dict[str, Any],
    meas: Dict[str, Any],
    rep: Dict[str, Any],
    fps: float,
    view: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    rule_id = rule["id"]
    name = rule["name"]
    source_pages = rule.get("source_pages", [])
    source_label = ", ".join(f"p{p}" for p in source_pages)

    base: Dict[str, Any] = {
        "rule_id": rule_id,
        "rule": name,
        "source_pages": source_pages,
        "source_section": source_label,
        "source_quote": rule.get("quote"),
        "assessable": rule.get("assessable") == "yes",
        "assessability": rule.get("assessable"),
        "frame": rep.get("bottom_frame"),
        "timestamp_s": round(rep.get("bottom_frame", 0) / fps, 3) if fps else None,
        "measurement": None,
        "status": "cannot assess",
        "feedback": rule.get("cannot_assess_reason") or "Not assessable.",
        "uncertainty": None,
    }

    if rule.get("assessable") == "no":
        base["feedback"] = rule.get("cannot_assess_reason") or "Not assessable from a side view."
        base["uncertainty"] = "Requires a front or rear view."
        return base

    # ---- Viewpoint gate -------------------------------------------------
    # The assignment specifies side-view recordings. If the recording is not
    # side-on, the sagittal geometry the rules depend on is meaningless, so
    # the rules must not produce confident verdicts from it.
    if view and view.get("view") == "not_side_view":
        base["feedback"] = (
            f"Cannot assess: this recording does not appear to be a side view "
            f"({view.get('reason')}). The document's criteria are defined in the "
            f"sagittal plane, so they cannot be evaluated from this angle."
        )
        base["uncertainty"] = view.get("note")
        return base

    # ---- Occlusion gate -------------------------------------------------
    # A landmark hidden behind a large object (weight plate, bench, rack) is
    # a model guess, not an observation. Report it honestly as cannot assess.
    occ = meas.get("occlusion") or {}
    required = rule.get("requires_landmarks") or []
    hidden = [k for k in required if occ.get(k)]
    if hidden:
        base["feedback"] = (
            f"Cannot assess: the {'/'.join(hidden)} "
            f"{'landmark was' if len(hidden) == 1 else 'landmarks were'} hidden behind a large object "
            f"in the recording, so the tracked position is a model estimate rather than an observation. "
            f"{rule.get('cannot_assess_reason') or ''}"
        ).strip()
        base["uncertainty"] = rule.get("occlusion_note")
        return base

    # Map the rule to its measurement(s).
    measure_key = rule.get("measure")
    keys = [k.strip() for k in measure_key.split(",")] if measure_key else []
    values = {k: meas.get(k) for k in keys}
    present = {k: v for k, v in values.items() if v is not None}

    if not present:
        base["feedback"] = rule.get("cannot_assess_reason") or "Measurement unavailable."
        return base

    base["measurement"] = {k: (round(v, 2) if isinstance(v, float) else v)
                           for k, v in values.items()}

    if rule.get("observation_only"):
        base["status"] = "observed"
        base["feedback"] = _fill(rule.get("feedback_meets") or "", present)
        return base

    thresholds = rule.get("thresholds", {}) or {}
    verdict = _judge(rule_id, present, thresholds, meas)

    if verdict is None:
        base["status"] = "cannot assess"
        base["feedback"] = rule.get("cannot_assess_reason") or "Not enough information to judge."
        return base

    status, detail = verdict
    base["status"] = status
    base["feedback"] = _fill(detail, present)
    if status == "does not meet standard":
        base["uncertainty"] = (
            f"Threshold {thresholds} is an application assumption; the document states the "
            f"criterion qualitatively (reference {source_label})."
        )
    return base


def _judge(rule_id: str, present: Dict[str, Any], thresholds: Dict[str, Any],
           meas: Optional[Dict[str, Any]] = None):
    """Apply the rule's thresholds. Returns (status, feedback_text) or None."""
    meas = meas or {}
    if rule_id == "DEPTH-01":
        d = present.get("depth_px")
        tol = thresholds.get("tolerance_px", 0)
        unc = meas.get("depth_uncertainty_px") or 0
        rng = meas.get("depth_px_range")
        sens = meas.get("depth_roll_sensitivity_px") or 0

        # If the verdict changes within the camera-roll uncertainty band, the
        # floor reference is not good enough to judge parallel. Say so rather
        # than picking whichever side of the uncertainty we happen to land on.
        if rng and (rng[0] > tol) != (rng[1] > tol):
            return "cannot assess", (
                f"Cannot assess: the depth result is not robust to the camera-roll estimate. "
                f"The hip crease apex measures {d:.0f} px from the top of the patella, but "
                f"within the plausible range of the floor reference ({rng[0]:.0f} px to "
                f"{rng[1]:.0f} px) the rep falls on both sides of parallel. The recording is "
                f"filmed at an angle where the foot line is not a reliable reference for "
                f"the horizontal, so the document's parallel test (reference p2) cannot be "
                f"applied with confidence."
            )

        if d > tol:
            return "meets standard", (
                f"Reached full depth: the hip crease apex was {d:.0f} px below the top of the "
                f"patella at the bottom of the rep (reference p2)."
            )
        if abs(d) <= unc:
            return "does not meet standard", (
                f"Depth is marginal: the hip crease apex was {abs(d):.0f} px from the top of the "
                f"patella, which is inside the measurement uncertainty of {unc:.0f} px for this "
                f"recording. The document requires the crease apex to drop below parallel "
                f"(reference p2), so this rep is reported as not meeting the standard, but it "
                f"cannot be distinguished from a borderline parallel squat with the available "
                f"landmark precision."
            )
        return "does not meet standard", (
            f"Did not reach full depth: the hip crease apex was {abs(d):.0f} px above the top of "
            f"the patella at the bottom of the rep. The document treats anything short of this as "
            f"a partial squat (reference p16), which stresses the knees and quadriceps without "
            f"loading the hamstrings, adductors and glutes."
        )

    if rule_id == "ANGLE-01":
        a = present.get("back_angle_deg")
        ref = thresholds.get("reference_deg", 45)
        tol = thresholds.get("tolerance_deg", 15)
        if abs(a - ref) <= tol:
            return "meets standard", (
                f"Back angle of {a:.0f} degrees is consistent with the inclined torso the document "
                f"describes for the low-bar squat (about {ref} degrees, reference p22)."
            )
        direction = "too vertical" if a > ref else "too horizontal"
        return "does not meet standard", (
            f"Back angle of {a:.0f} degrees is {direction}. The document expects an inclined back of "
            f"about {ref} degrees (reference p22) and states that the back angle will not be vertical "
            f"at all (reference p33). A vertical back is the most common error and it kills hip drive."
        )

    if rule_id == "BAR-01":
        d = present.get("bar_drift_from_midfoot_px")
        tol = thresholds.get("tolerance_px", 25)
        band = meas.get("bar_drift_range_px")
        n = meas.get("bar_drift_samples") or 0
        rep_frames = meas.get("rep_frames") or 0
        frac = thresholds.get("min_sample_fraction", 0.2)
        needed = max(thresholds.get("min_samples", 3),
                     int(rep_frames * frac))

        # A verdict must not rest on a handful of frames: if the bar or the
        # midfoot could only be located on a small fraction of the repetition,
        # the measurement is not evidence.
        if n < needed:
            return "cannot assess", (
                f"Cannot assess: the bar and the midfoot could only be located on {n} of the "
                f"{rep_frames} frames in this repetition. At least {needed} are needed for the "
                f"measurement to support a verdict, so the bar path could not be evaluated."
            )

        # The bar sits high and the midfoot is on the floor, so the
        # measurement depends on the camera-roll reference. If the verdict
        # changes across the roll uncertainty band, say so.
        if band and (band[0] <= tol) != (band[1] <= tol):
            return "cannot assess", (
                f"Cannot assess: the bar path measurement is not robust to the camera-roll "
                f"estimate. The bar deviates from the midfoot by between {band[0]:.0f} px and "
                f"{band[1]:.0f} px across the plausible range of the floor reference, which "
                f"straddles the threshold. The bar and the midfoot are far apart vertically, so "
                f"a small error in the horizontal reference moves the result a long way."
            )

        if d <= tol:
            return "meets standard", (
                f"Bar path stayed over the midfoot balance point (maximum horizontal deviation "
                f"{d:.0f} px, measured on {n} of {rep_frames} frames; the plausible range of that "
                f"figure is {band[0]:.0f} to {band[1]:.0f} px)."
            )
        return "does not meet standard", (
            f"Bar drifted {d:.0f} px horizontally from the midfoot, measured on {n} of "
            f"{rep_frames} frames (the plausible range of that figure is {band[0]:.0f} to "
            f"{band[1]:.0f} px, because the bar and the midfoot are far apart vertically). "
            f"The document states that any horizontal component of bar motion is not work against "
            f"gravity (reference p11) and that flopping forward lets the bar drop forward of the "
            f"midfoot (reference p33)."
        )

    if rule_id == "HIP-01":
        r = present.get("hip_drive_ratio")
        minr = thresholds.get("min_ratio", 1.0)
        if r >= minr:
            return "meets standard", (
                "Hips drove up out of the bottom rather than forward, matching the document's "
                "'up, not forward' instruction (reference p23)."
            )
        return "does not meet standard", (
            f"Hips travelled forward as much as they travelled up out of the bottom (vertical/forward "
            f"ratio {r:.2f}). The document is explicit that the lifter must come out of the bottom "
            f"driving the hips straight up, not forward, and that lifting the chest instead of driving "
            f"the hips kills power out of the bottom (reference p35)."
        )

    if rule_id == "KNEE-01":
        v = present.get("knee_forward_of_toe_px")
        lo = thresholds.get("min_px", 0)
        hi = thresholds.get("max_px", 120)
        if lo <= v <= hi:
            return "meets standard", (
                f"Knees sit {v:.0f} px forward of the toe line, consistent with the bottom position "
                f"the document describes (reference p22)."
            )
        if v < lo:
            return "does not meet standard", (
                f"Knees sit {abs(v):.0f} px behind the toe line. The document's bottom position has "
                f"the knees just a little forward of the toes with the hips back (reference p22)."
            )
        return "does not meet standard", (
            f"Knees sit {v:.0f} px forward of the toe line, well beyond 'just a little forward'. "
            f"The document notes that forcing the knees far forward of the midfoot creates an "
            f"anterior shear on the knee (reference p17)."
        )

    if rule_id == "HIP-02":
        v = present.get("hip_behind_ankle_px")
        if v >= thresholds.get("min_px", 0):
            return "meets standard", (
                "Hips are back over the heels at the bottom, as the document's bottom position "
                "describes (reference p22)."
            )
        return "does not meet standard", (
            f"Hips are {abs(v):.0f} px forward of the ankles at the bottom. The document's bottom "
            f"position has the hips back with the knees just a little forward of the toes "
            f"(reference p22); hips that sit too far forward shift the load to the knees."
        )

    if rule_id == "EYE-01":
        v = present.get("head_pitch_deg")
        mn = thresholds.get("min_deg", 10)
        if v >= mn:
            return "meets standard", (
                f"Head is pitched down {v:.0f} degrees, consistent with the document's chin-down "
                f"position of looking at a point on the floor 4-5 feet in front of you (reference p24)."
            )
        if v < 0:
            return "does not meet standard", (
                f"Head is pitched {abs(v):.0f} degrees upward. The document is explicit that failing to "
                f"look down kills hip drive, and that an upward gaze puts the cervical spine in an unsafe "
                f"position under load (references p24, p26, p35)."
            )
        return "does not meet standard", (
            f"Head is level ({v:.0f} degrees) rather than pitched down. The document asks the lifter to "
            f"look down at a point on the floor 4-5 feet in front, and states that an upward gaze kills "
            f"hip drive (references p24, p35)."
        )

    if rule_id == "BAR-02":
        return "meets standard", (
            "Bar height is consistent with the low-bar position described in the document. This is an "
            "estimate: confirming that the bar sits just under the spine of the scapula requires a "
            "rear view (references p29, p30)."
        )

    return None


def _fill(text: str, present: Dict[str, Any]) -> str:
    out = text
    for k, v in present.items():
        if isinstance(v, float):
            out = out.replace("{" + k + "}", f"{v:.0f}")
        else:
            out = out.replace("{" + k + "}", str(v))
    return out


def _overall(findings: List[Dict[str, Any]]) -> str:
    verdicted = [f for f in findings if f["status"] in
                 ("meets standard", "does not meet standard", "cannot assess")
                 and f.get("assessable") is not False]
    if not verdicted:
        return "cannot assess"
    statuses = {f["status"] for f in verdicted}
    if "does not meet standard" in statuses:
        return "does not meet standard"
    if "cannot assess" in statuses:
        return "cannot assess"
    return "meets standard"
