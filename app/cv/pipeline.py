"""End-to-end squat analysis pipeline.

Runs the full flow: pose tracking -> rep detection -> skill evaluation ->
annotated video + JSON report. Kept separate from the HTTP layer so the same
code path can be exercised from a script or a test.
"""

from __future__ import annotations

import json
import math
import os
from typing import Any, Callable, Dict, List, Optional, Tuple

import cv2
import numpy as np

from .pose_estimator import PoseEstimator, to_pixel, to_pixel_in_frame, pick_side
from .rep_detector import detect_reps
from .evaluator import evaluate_rep, build_frame_geometry, load_skill
from .annotator import annotate_frame, build_uncertainty_notes
from .occlusion import OcclusionDetector
from .measurements import estimate_roll
from .viewpoint import classify_view
from .video_writer import open_video_writer, verify_playable

MAX_DURATION_SECONDS = 60


def analyze_video(
    video_path: str,
    progress_cb: Optional[Callable[[int, str], None]] = None,
    output_dir: Optional[str] = None,
    max_duration_s: int = MAX_DURATION_SECONDS,
    write_video: bool = True,
) -> Dict[str, Any]:
    """Analyze a squat video and return the full report.

    progress_cb(percent, stage) is called during processing.
    """
    def progress(pct: int, stage: str = ""):
        if progress_cb:
            progress_cb(pct, stage)

    progress(5, "opening video")
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError("Could not open video file")

    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    duration_s = frame_count / fps if fps else 0

    if duration_s > max_duration_s:
        cap.release()
        raise RuntimeError(
            f"Video too long: {duration_s:.1f}s (max {max_duration_s}s)")

    progress(10, "tracking pose")
    estimator = PoseEstimator()
    if not estimator.available:
        cap.release()
        raise RuntimeError(
            "Pose model unavailable. Place pose_landmarker_lite.task in app/models/.")

    frames_px: List[dict] = []
    hip_y_px: List[Optional[float]] = []
    bar_path_px: List[Optional[Tuple[int, int]]] = []
    draw_frames: List[Optional[dict]] = []
    occluded_px: List[Dict[str, bool]] = []
    occluder_counts: List[int] = []

    occluder = OcclusionDetector()

    frame_idx = 0
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        pose = estimator.estimate(frame, timestamp_ms=frame_idx * 1000.0 / fps)
        entry: Dict[str, Any] = {}
        draw: Dict[str, Any] = {}
        bar_pt: Optional[Tuple[int, int]] = None

        if pose:
            lw = to_pixel_in_frame(pose.get("left_wrist"), width, height)
            rw = to_pixel_in_frame(pose.get("right_wrist"), width, height)
            sh = pick_side(pose, "left_shoulder", "right_shoulder", width)
            hip = pick_side(pose, "left_hip", "right_hip", width)
            knee = pick_side(pose, "left_knee", "right_knee", width)
            ankle = pick_side(pose, "left_ankle", "right_ankle", width)
            heel = pick_side(pose, "left_heel", "right_heel", width)
            toe = pick_side(pose, "left_foot_index", "right_foot_index", width)
            nrm = pose.get("nose")
            ear = pick_side(pose, "left_ear", "right_ear", width)

            px = lambda t: to_pixel_in_frame(t, width, height)
            entry = {
                "shoulder": px(sh), "hip": px(hip), "knee": px(knee),
                "ankle": px(ankle), "heel": px(heel), "toe": px(toe),
                "nose": px(nrm), "ear": px(ear),
                # Raw per-side landmarks, used only for the viewpoint check.
                "_left_ankle": px(pose.get("left_ankle")),
                "_right_ankle": px(pose.get("right_ankle")),
                "_left_shoulder": px(pose.get("left_shoulder")),
                "_right_shoulder": px(pose.get("right_shoulder")),
            }
            draw = {"shoulder": entry["shoulder"], "hip": entry["hip"],
                    "knee": entry["knee"], "ankle": entry["ankle"],
                    "heel": entry["heel"], "toe": entry["toe"],
                    "nose": entry["nose"], "ear": entry["ear"]}

            pts = [p for p in [lw, rw] if p is not None]
            if pts:
                bar_pt = (int(sum(p[0] for p in pts) / len(pts)),
                          int(sum(p[1] for p in pts) / len(pts)))
            entry["bar"] = bar_pt
            hip_y_px.append(entry["hip"][1] if entry["hip"] else None)

            # --- Occlusion: which tracked landmarks are hidden by a large
            # dark object (weight plate, bench, rack, dark clothing)? ---
            occ = occluder.frame_flags(frame, {
                "shoulder": entry["shoulder"],
                "head": entry["nose"] if entry["nose"] else entry["ear"],
                "hip": entry["hip"],
                "knee": entry["knee"],
                "ankle": entry["ankle"],
                "bar": bar_pt,
            })
            occluded_px.append(occ)
        else:
            hip_y_px.append(None)
            occluded_px.append({})
            occluder_counts.append(0)

        frames_px.append(entry)
        draw_frames.append(draw)
        bar_path_px.append(bar_pt)
        frame_idx += 1
        if frame_idx % 10 == 0:
            progress(10 + int(50 * frame_idx / max(frame_count, 1)), "tracking pose")

    cap.release()
    estimator.close()

    progress(60, "detecting repetitions")
    reps_raw = detect_reps(
        hip_y_px,
        min_rep_frames=int(fps * 0.6),
        prominence_px=35.0,
        max_rep_span_frames=int(fps * 12),
    )
    reps = [{"rep_id": i + 1, **r} for i, r in enumerate(reps_raw)]

    progress(65, "aligning to the floor")
    # --- Camera roll and viewpoint -------------------------------------
    roll, facing, roll_spread = estimate_roll(frames_px)
    # The floor reference is only as good as the foot line. Allow a band of
    # at least 4 degrees, widened when the foot line itself is inconsistent.
    roll_uncertainty = max(math.radians(4.0), roll_spread * 1.5)
    ankle_sep = []
    shoulder_sep = []
    for f in frames_px:
        la, ra = f.get("_left_ankle"), f.get("_right_ankle")
        ankle_sep.append(abs(la[0] - ra[0]) if (la and ra) else None)
        ls, rs = f.get("_left_shoulder"), f.get("_right_shoulder")
        shoulder_sep.append(abs(ls[0] - rs[0]) if (ls and rs) else None)
    view = classify_view(frames_px, ankle_sep, shoulder_sep)

    progress(70, "evaluating against skill")
    aligned_frames, geometry = build_frame_geometry(
        frames_px, roll=roll, facing=facing, center=(width / 2.0, height / 2.0))
    skill = load_skill()
    rep_results = []
    bottom_frames = set()
    for r in reps:
        res = evaluate_rep(
            rep=r, geometry=geometry, frames=aligned_frames, fps=fps,
            skill=skill, occluded=occluded_px, roll=roll, facing=facing, view=view,
            roll_uncertainty=roll_uncertainty,
        )
        rep_results.append(res)
        bottom_frames.add(r["bottom_frame"])

    rep_labels: Dict[int, str] = {}
    for r in rep_results:
        rep_labels[r["start_frame"]] = f"Rep {r['rep_id']} start"
        rep_labels[r["bottom_frame"]] = f"Rep {r['rep_id']} BOTTOM"
        rep_labels[r["end_frame"]] = f"Rep {r['rep_id']} end"

    annotated_path = None
    video_info: Dict[str, Any] = {}
    if write_video:
        progress(78, "rendering annotated video")
        # Draw the aligned frames so the on-screen geometry matches the
        # numbers in the report (the whole frame is rotated by -roll).
        aligned_draw = []
        for i, d in enumerate(draw_frames):
            a = aligned_frames[i] if i < len(aligned_frames) else {}
            g = dict(d)
            for k in ("shoulder", "hip", "knee", "ankle", "heel", "toe", "nose", "ear"):
                if a.get(k) is not None:
                    g[k] = a[k]
            aligned_draw.append(g)
        annotated_path = _render_annotated(
            video_path, output_dir, fps, (width, height),
            aligned_draw, aligned_frames, geometry,
            [a.get("bar") for a in aligned_frames],
            bottom_frames, rep_labels, rep_results,
            lambda p: progress(78 + int(15 * p), "rendering annotated video"),
            occluded_px=occluded_px, roll=roll,
        )
        playable, detail = verify_playable(annotated_path)
        video_info = {
            "file": os.path.basename(annotated_path),
            "bytes": os.path.getsize(annotated_path),
            "browser_playable": playable,
            "format": detail,
        }

    report = {
        "source_file": os.path.basename(video_path),
        "fps": fps,
        "frame_count": frame_count,
        "duration_s": round(duration_s, 3),
        "video_w": width,
        "video_h": height,
        "reps_detected": len(rep_results),
        "viewpoint": view,
        "camera_roll_deg": round(math.degrees(roll), 2),
        "camera_roll_uncertainty_deg": round(math.degrees(roll_uncertainty), 2),
        "reps": rep_results,
        "skill": {
            "skill_id": skill.get("skill_id"),
            "version": skill.get("version"),
            "title": skill.get("title"),
            "source": skill.get("source"),
            "rules_evaluated": len(skill.get("rules", [])),
        },
        "annotated_video": os.path.basename(annotated_path) if annotated_path else None,
        "annotated_video_info": video_info,
        "notes": [
            "Every finding cites the reference pages of the supplied document "
            "(reference page N == combined PDF page N+3).",
            "Thresholds marked threshold_source=assumption are application "
            "engineering assumptions, not document requirements.",
            "Criteria the document requires but a side view cannot reveal are "
            "returned as 'cannot assess'.",
            "Depth is measured from the estimated crease apex (document landmark B) "
            "against the top of the patella (landmark A) in a gravity-aligned frame; "
            "the crease offset is an application assumption.",
        ],
    }
    return report, annotated_path, rep_results


def _open_video_writer(path: str, fps: float, size):
    """Deprecated shim kept for compatibility; see video_writer.open_video_writer."""
    return open_video_writer(path, fps, size)


def _render_annotated(video_path, output_dir, fps, size, draw_frames, frames_px,
                       geometry, bar_path_px, bottom_frames, rep_labels, rep_results,
                       progress_cb, occluded_px=None, roll=0.0):
    out_dir = output_dir or "outputs"
    os.makedirs(out_dir, exist_ok=True)
    base = os.path.splitext(os.path.basename(video_path))[0]
    out_path = os.path.join(out_dir, f"{base}_annotated.mp4")
    writer, codec = open_video_writer(out_path, fps, size)
    if writer is None:
        raise RuntimeError("Could not open a video writer for the annotated output")

    notes = build_uncertainty_notes([f for r in rep_results for f in r["findings"]])
    # Map each bottom frame to the depth verdict, so the overlay only claims a
    # depth conclusion where the rule was actually assessed.
    depth_status: Dict[int, str] = {}
    for r in rep_results:
        for f in r["findings"]:
            if f["rule_id"] == "DEPTH-01":
                depth_status[r["bottom_frame"]] = f["status"]
    cap = cv2.VideoCapture(video_path)
    cx, cy = size[0] / 2.0, size[1] / 2.0
    # OpenCV's getRotationMatrix2D uses the opposite sign convention to
    # measurements.rotate_point, so the angle is negated to rotate the picture
    # the same way the landmarks were rotated.
    M = cv2.getRotationMatrix2D((cx, cy), math.degrees(roll), 1.0)
    fi = 0
    total = max(len(draw_frames), 1)
    while True:
        ret, frame = cap.read()
        if not ret:
            break
        # Rotate the picture so the floor is horizontal, matching the frame the
        # measurements were taken in. A viewer can then check the drawn angles
        # directly against a horizontal floor.
        if abs(roll) > 1e-4:
            frame = cv2.warpAffine(frame, M, size, borderMode=cv2.BORDER_REPLICATE)
        d = draw_frames[fi] if fi < len(draw_frames) else {}
        bar_pt = bar_path_px[fi] if fi < len(bar_path_px) else None
        g = geometry[fi] if fi < len(geometry) else {}
        annotated = annotate_frame(
            frame, d, bar_pt, bar_path_px[: fi + 1], fi,
            bottom_frames, rep_labels, notes[:3],
            midfoot=g.get("midfoot"), floor=(1.0, 0.0),
            bar_visible=True,
            occluded=(occluded_px[fi] if fi < len(occluded_px) else {}),
            crease=g.get("hip_crease"),
            depth_status=depth_status.get(fi),
        )
        writer.write(annotated)
        fi += 1
        if fi % 10 == 0:
            progress_cb(fi / total)
    cap.release()
    writer.release()
    ok, detail = verify_playable(out_path)
    if not ok:
        print("WARNING: annotated video may not play in a browser:", detail)
    return out_path
