"""Unit tests for the squat analysis pipeline.

Run: python -m pytest tests/ -v     (or: python tests/test_pipeline.py)

Covers the parts that are easy to get subtly wrong: repetition detection,
the gravity alignment, the viewpoint classifier, the occlusion detector and
the skill-driven evaluator.
"""

from __future__ import annotations

import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np

from app.cv.rep_detector import detect_reps
from app.cv.measurements import (
    estimate_roll, rotate_point, rotate_frames, back_angle_deg,
    head_pitch_deg, midfoot, crease_apex,
)
from app.cv.viewpoint import classify_view
from app.cv.occlusion import OcclusionDetector
from app.cv.evaluator import load_skill, evaluate_rep, build_frame_geometry

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name} {detail}")
        FAILURES.append(name)


# ---------------------------------------------------------------------------
def test_rep_detection():
    print("\n[rep detection]")
    fps = 30
    # standing -> down -> hold -> up -> pause -> down (shallower) -> up
    hip = ([300.0] * 60
           + list(np.linspace(300, 420, 30)) + [420.0] * 20
           + list(np.linspace(420, 300, 30)) + [300.0] * 40
           + list(np.linspace(300, 360, 25)) + [360.0] * 15
           + list(np.linspace(360, 300, 25)))
    reps = detect_reps(hip, min_rep_frames=int(fps * 0.6), prominence_px=35.0,
                       max_rep_span_frames=int(fps * 12))
    check("detects two complete reps", len(reps) == 2, f"got {len(reps)}")
    if len(reps) == 2:
        # The first rep's bottom plateau spans frames 90-109.
        check("first bottom falls on the deepest plateau",
              90 <= reps[0]["bottom_frame"] <= 109, reps[0])
        # The second rep bottoms on the shallower plateau spanning 205-219.
        check("second bottom falls on the shallow plateau",
              205 <= reps[1]["bottom_frame"] <= 219, reps[1])
        check("rep windows do not overlap",
              reps[0]["end_frame"] <= reps[1]["start_frame"], reps)
        check("each rep is long enough",
              all(r["end_frame"] - r["start_frame"] >= fps for r in reps), reps)

    # A flat signal (no squat) must produce no reps.
    check("no reps in a flat signal", detect_reps([300.0] * 200, 18, 35.0) == [])
    # Tracking dropouts must not create reps.
    noisy = list(hip)
    for i in range(0, len(noisy), 7):
        noisy[i] = None
    check("handles missing frames",
          len(detect_reps(noisy, 18, 35.0, max_rep_span_frames=360)) == 2)


# ---------------------------------------------------------------------------
def test_alignment():
    print("\n[gravity alignment]")
    frames = [{"heel": (100, 100), "toe": (200, 120)}]
    roll, facing, spread = estimate_roll(frames)
    check("roll recovered", abs(math.degrees(roll) - 11.31) < 0.2,
          math.degrees(roll))
    check("facing detected", facing == 1.0, facing)
    check("spread reported", spread >= 0, spread)
    h = rotate_point((100, 100), -roll, 0, 0)
    t = rotate_point((200, 120), -roll, 0, 0)
    check("floor becomes horizontal", abs(t[1] - h[1]) < 1e-6, (h, t))

    # Rotating a point must preserve its distance from the rotation centre.
    p = (410, 90)
    q = rotate_point(p, -roll, 320, 240)
    d1 = math.hypot(p[0] - 320, p[1] - 240)
    d2 = math.hypot(q[0] - 320, q[1] - 240)
    check("rotation is rigid", abs(d1 - d2) < 1e-6, (d1, d2))


# ---------------------------------------------------------------------------
def test_angles():
    print("\n[angles in the aligned frame]")
    # Torso vertical: hip below shoulder -> back angle 90
    a = back_angle_deg((100, 100), (100, 200))
    check("vertical torso is 90 degrees", abs(a - 90) < 0.01, a)
    # Torso at 45 degrees
    b = back_angle_deg((100, 100), (0, 200))
    check("45 degree torso reads 45", abs(b - 45) < 0.01, b)
    # Head pointing forward (level) -> pitch 0; nose below ear -> positive
    check("level head is 0 degrees", abs(head_pitch_deg((150, 100), (100, 100))) < 0.01)
    check("chin down is positive",
          head_pitch_deg((150, 140), (100, 100)) > 0)
    check("chin up is negative",
          head_pitch_deg((150, 60), (100, 100)) < 0)
    # Midfoot is the midpoint of heel and toe
    m = midfoot((100, 100), (200, 120))
    check("midfoot is the midpoint", m == (150, 110), m)
    # Crease apex sits below the hip joint
    c = crease_apex((100, 200), (100, 100))
    check("crease apex is below the hip joint", c[1] > 200, c)


# ---------------------------------------------------------------------------
def test_viewpoint():
    print("\n[viewpoint classifier]")
    side = []
    for _ in range(40):
        side.append({"shoulder": (300, 100), "hip": (290, 200),
                     "heel": (150, 380), "toe": (240, 380),
                     "_left_ankle": (190, 370), "_right_ankle": (194, 370)})
    v = classify_view(side, [4] * 40)
    check("side view detected", v["view"] == "side_view", v)

    front = []
    for _ in range(40):
        front.append({"shoulder": (300, 100), "hip": (290, 200),
                      "heel": (150, 380), "toe": (160, 300),
                      "_left_ankle": (170, 370), "_right_ankle": (330, 370)})
    v2 = classify_view(front, [160] * 40)
    check("front view detected", v2["view"] == "not_side_view", v2)
    check("front view gives a reason", bool(v2["reason"]), v2)

    # An oblique (rear three-quarter) view: the shoulders are well separated
    # even though the ankles are less so.
    oblique = []
    for _ in range(40):
        oblique.append({"shoulder": (300, 100), "hip": (290, 200),
                        "heel": (150, 380), "toe": (160, 330),
                        "_left_ankle": (180, 370), "_right_ankle": (230, 370)})
    v3 = classify_view(oblique, [50] * 40, [140] * 40)
    check("oblique view detected via shoulder separation",
          v3["view"] == "not_side_view", v3)


def test_out_of_frame_landmarks():
    print("\n[out-of-frame landmarks]")
    # MediaPipe extrapolates landmarks for body parts outside the picture, so
    # normalised coordinates can exceed 1.0. Those must be discarded, and the
    # occlusion detector must never index the image with them.
    from app.cv.pose_estimator import to_pixel_in_frame
    check("in-frame landmark is kept",
          to_pixel_in_frame((0.5, 0.5), 1920, 1080) == (960, 540))
    check("below the frame is discarded",
          to_pixel_in_frame((0.5, 1.22), 1920, 1080) is None)
    check("right of the frame is discarded",
          to_pixel_in_frame((1.4, 0.5), 1920, 1080) is None)
    check("negative coordinate is discarded",
          to_pixel_in_frame((-0.2, 0.5), 1920, 1080) is None)
    check("None is handled", to_pixel_in_frame(None, 1920, 1080) is None)

    # The occlusion detector must not raise on an out-of-frame point.
    det = OcclusionDetector()
    cv2 = __import__("cv2")
    frame = np.full((1080, 1920, 3), 120, dtype=np.uint8)
    cv2.circle(frame, (900, 400), 120, (10, 10, 10), -1)
    masks = det.find_occluders(frame)
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    try:
        r = det.is_occluded(masks, (1348, 1285), gray)
        check("no crash on an out-of-frame point", r is False, r)
    except Exception as exc:  # noqa: BLE001
        check("no crash on an out-of-frame point", False, repr(exc))


# ---------------------------------------------------------------------------
def test_occlusion():
    print("\n[occlusion detector]")
    det = OcclusionDetector()
    frame = np.full((480, 640, 3), 120, dtype=np.uint8)
    # A big smooth black disc (a weight plate)
    cv2 = __import__("cv2")
    cv2.circle(frame, (300, 200), 90, (10, 10, 10), -1)
    masks = det.find_occluders(frame)
    check("plate detected as an occluder", len(masks) >= 1, len(masks))
    check("point on the plate is occluded",
          det.is_occluded(masks, (300, 200), cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)))
    check("point off the plate is not occluded",
          not det.is_occluded(masks, (100, 100), cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)))

    # Dark but textured clothing should NOT be treated as an occluder.
    frame2 = np.full((480, 640, 3), 120, dtype=np.uint8)
    rng = np.random.default_rng(0)
    patch = frame2[300:400, 200:340]
    patch[:] = (18, 18, 18)
    patch = np.clip(patch.astype(int) + rng.integers(-9, 9, patch.shape), 0, 255).astype(np.uint8)
    frame2[300:400, 200:340] = patch
    masks2 = det.find_occluders(frame2)
    gray2 = cv2.cvtColor(frame2, cv2.COLOR_BGR2GRAY)
    check("textured dark clothing is not an occluder",
          not det.is_occluded(masks2, (270, 350), gray2), masks2)


# ---------------------------------------------------------------------------
def test_skill_and_evaluator():
    print("\n[skill and evaluator]")
    skill = load_skill()
    check("skill loads", isinstance(skill, dict) and "rules" in skill)
    rules = skill["rules"]
    check("skill has rules", len(rules) >= 10, len(rules))
    check("every rule cites reference pages",
          all(r.get("source_pages") for r in rules))
    check("every rule states assessability",
          all(r.get("assessable") in ("yes", "partial", "no") for r in rules))
    check("non-assessable rules give a reason",
          all(r.get("cannot_assess_reason") for r in rules if r["assessable"] == "no"))
    check("every rule discloses its threshold source",
          all(r.get("threshold_source") in ("document", "assumption") for r in rules))

    # Build a synthetic rep that satisfies the document's standards and one
    # that does not, and check the verdicts differ.
    def make_frames(deep: bool):
        frames = []
        for i in range(120):
            t = i / 120.0
            squat = math.sin(math.pi * t)
            # In a deep squat the hip crease drops below the top of the patella
            # (larger image y); in a shallow squat the hip stays above it.
            hip_y = 300 + (120 if deep else 40) * squat
            knee_y = hip_y - 30 if deep else hip_y + 40
            frames.append({
                "shoulder": (250, hip_y - 90), "hip": (240, hip_y),
                "knee": (260, knee_y), "ankle": (270, 460),
                "heel": (240, 470), "toe": (320, 470),
                "nose": (300, hip_y - 140), "ear": (280, hip_y - 130),
                "bar": (255, hip_y - 95),
            })
        return frames

    def run(frames):
        aligned, geometry = build_frame_geometry(frames, roll=0.0, facing=1.0,
                                                  center=(320, 240))
        rep = {"rep_id": 1, "start_frame": 0, "bottom_frame": 60, "end_frame": 119}
        return evaluate_rep(rep, geometry, aligned, 30.0, skill=skill)

    deep = run(make_frames(True))
    shallow = run(make_frames(False))
    d_find = {f["rule_id"]: f for f in deep["findings"]}
    s_find = {f["rule_id"]: f for f in shallow["findings"]}
    check("deep rep meets depth", d_find["DEPTH-01"]["status"] == "meets standard",
          d_find["DEPTH-01"])
    check("shallow rep fails depth",
          s_find["DEPTH-01"]["status"] == "does not meet standard",
          s_find["DEPTH-01"])
    check("depth finding cites pages", d_find["DEPTH-01"]["source_pages"] == [2, 16, 33, 35])
    check("stance is cannot assess from a side view",
          d_find["STANCE-01"]["status"] == "cannot assess")
    check("every finding carries a status",
          all(f["status"] in ("meets standard", "does not meet standard",
                               "cannot assess", "observed") for f in deep["findings"]))
    check("every finding carries feedback",
          all(f.get("feedback") for f in deep["findings"]))
    check("no finding invents a source page",
          all(all(1 <= p <= 35 for p in f["source_pages"]) for f in deep["findings"]))


# ---------------------------------------------------------------------------
def test_view_gate():
    print("\n[view gate]")
    skill = load_skill()
    frames = []
    for i in range(120):
        frames.append({"shoulder": (250, 200), "hip": (240, 300), "knee": (260, 330),
                        "ankle": (270, 460), "heel": (240, 470), "toe": (320, 470),
                        "nose": (300, 150), "ear": (280, 160), "bar": (255, 190)})
    aligned, geometry = build_frame_geometry(frames, roll=0.0, facing=1.0, center=(320, 240))
    rep = {"rep_id": 1, "start_frame": 0, "bottom_frame": 60, "end_frame": 119}
    view = {"view": "not_side_view", "reason": "synthetic front view",
            "note": "not a side view"}
    res = evaluate_rep(rep, geometry, aligned, 30.0, skill=skill, view=view)
    assessed = [f for f in res["findings"] if f["rule_id"] in
                ("DEPTH-01", "ANGLE-01", "BAR-01", "HIP-01")]
    check("side-view rules are blocked for a front view",
          all(f["status"] == "cannot assess" for f in assessed),
          [(f["rule_id"], f["status"]) for f in assessed])
    check("overall is cannot assess", res["overall"] == "cannot assess", res["overall"])


def test_video_output():
    print("\n[browser-playable video output]")
    import tempfile
    import os
    from app.cv.video_writer import open_video_writer, verify_playable

    tmp = os.path.join(tempfile.gettempdir(), "_sq_test_video.mp4")
    cv2 = __import__("cv2")
    try:
        writer, codec = open_video_writer(tmp, 25.0, (320, 240))
        check("writer opened", writer is not None, codec)
        for i in range(30):
            img = np.full((240, 320, 3), (i * 7) % 255, dtype=np.uint8)
            cv2.putText(img, str(i), (100, 130), 0, 1, (0, 255, 255), 2)
            writer.write(img)
        writer.release()
        check("file was written", os.path.getsize(tmp) > 1000,
              os.path.getsize(tmp) if os.path.exists(tmp) else 0)
        ok, detail = verify_playable(tmp)
        check("output is browser playable", ok, detail)
        if ok:
            with open(tmp, "rb") as f:
                head = f.read(65536)
            check("H.264 sample entry present", b"avc1" in head)
            check("index is at the front (faststart)",
                  head.find(b"moov") != -1 and head.find(b"moov") < head.find(b"mdat"))
        cap = cv2.VideoCapture(tmp)
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        cap.release()
        check("frames are readable", frames == 30, frames)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except OSError:
                pass


if __name__ == "__main__":
    test_rep_detection()
    test_alignment()
    test_angles()
    test_viewpoint()
    test_out_of_frame_landmarks()
    test_occlusion()
    test_skill_and_evaluator()
    test_view_gate()
    test_video_output()
    print("\n" + "=" * 60)
    if FAILURES:
        print(f"{len(FAILURES)} FAILURES: {FAILURES}")
        sys.exit(1)
    print("ALL TESTS PASSED")
