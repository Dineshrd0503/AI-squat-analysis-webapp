"""Repetition detection from hip vertical trajectory.

Detects squat bottoms as local maxima of hip pixel-y (down in image = larger y).
Applies prominence and minimum-dwell filtering to suppress jitter and pauses.
"""

from __future__ import annotations

from typing import List, Tuple, Dict
import numpy as np


def detect_reps(
    hip_y: List[Optional[float]],
    min_rep_frames: int = 15,
    prominence_px: float = 40.0,
    min_gap_frames: int = 8,
    max_rep_span_frames: Optional[int] = None,
) -> List[Dict[str, int]]:
    """Detect squat repetitions.

    Parameters
    ----------
    hip_y : list of float or None
        Hip pixel-y per frame (larger = lower in image). None = missing pose.
    min_rep_frames : int
        Minimum frames between the start of one rep and the start of the next.
    prominence_px : float
        How far (px) the hip must descend below the surrounding local max to
        count as a real bottom.
    min_gap_frames : int
        Minimum frames between two detected bottoms (merge closer detections).

    Returns
    -------
    list of dicts with keys: start_frame, bottom_frame, end_frame
    """
    n = len(hip_y)
    if n < 3:
        return []

    # Fill missing values by linear interpolation so the signal is continuous.
    y = np.array([v if v is not None else np.nan for v in hip_y], dtype=float)
    nan_mask = np.isnan(y)
    if nan_mask.all():
        return []
    if nan_mask.any():
        idx = np.arange(n)
        y[nan_mask] = np.interp(idx[nan_mask], idx[~nan_mask], y[~nan_mask])

    # Smooth lightly to kill high-frequency jitter. Pad with edge values rather
    # than zeros: zero padding drags the first and last samples down and
    # manufactures a phantom descent and ascent at the edges of the clip,
    # which shows up as a spurious repetition.
    kernel = np.ones(5) / 5.0
    padded = np.pad(y, (2, 2), mode="edge")
    y_smooth = np.convolve(padded, kernel, mode="valid")

    # Local maxima = squat bottoms (hip lowest in image). Local minima = standing
    # valleys between reps. Pair each bottom with adjacent valleys to compute a
    # true prominence that survives bottom plateaus.
    bottoms: List[int] = []
    valleys: List[int] = []
    for i in range(1, n - 1):
        if y_smooth[i] >= y_smooth[i - 1] and y_smooth[i] >= y_smooth[i + 1]:
            bottoms.append(i)
        if y_smooth[i] <= y_smooth[i - 1] and y_smooth[i] <= y_smooth[i + 1]:
            valleys.append(i)

    # One-sided tests at the edges. A repetition whose ascent finishes on the
    # final frame of the recording has no two-sided local minimum there, and
    # would otherwise be missed entirely.
    if n >= 2:
        if y_smooth[0] <= y_smooth[1]:
            valleys.append(0)
        if y_smooth[0] >= y_smooth[1]:
            bottoms.append(0)
        if y_smooth[n - 1] <= y_smooth[n - 2]:
            valleys.append(n - 1)
        if y_smooth[n - 1] >= y_smooth[n - 2]:
            bottoms.append(n - 1)
    bottoms.sort()
    valleys.sort()

    # Filter bottoms by prominence relative to adjacent valleys.
    kept: List[Tuple[int, int, int]] = []  # (bottom, left_valley, right_valley)
    for b in bottoms:
        # nearest valley to the left that is genuinely lower than the bottom
        left_valleys = [v for v in valleys if v < b and y_smooth[v] <= y_smooth[b] - prominence_px]
        right_valleys = [v for v in valleys if v > b and y_smooth[v] <= y_smooth[b] - prominence_px]
        if not left_valleys or not right_valleys:
            continue  # bottom at edge or no full descent/ascent around it
        lv = max(left_valleys)
        rv = min(right_valleys)
        # Only consider valleys within a plausible rep length window. A slow
        # low-bar squat can easily take 4-6 seconds, so this has to be
        # generous or genuine reps get rejected.
        span_limit = max_rep_span_frames or max(min_rep_frames * 10, 300)
        if b - lv > span_limit or rv - b > span_limit:
            continue
        prominence = y_smooth[b] - min(y_smooth[lv], y_smooth[rv])
        if prominence >= prominence_px:
            kept.append((b, lv, rv))

    # Dedup bottoms that share the same valley pair (same rep, e.g. a bottom
    # plateau). Keep the deepest bottom per unique (left_valley, right_valley).
    best: Dict[Tuple[int, int], Tuple[int, int, int]] = {}
    for item in kept:
        b, lv, rv = item
        key = (lv, rv)
        if key not in best or y_smooth[b] > y_smooth[best[key][0]]:
            best[key] = item
    merged = sorted(best.values(), key=lambda t: t[0])

    # Build rep windows between the kept valleys.
    reps: List[Dict[str, int]] = []
    for b, lv, rv in merged:
        start = lv
        end = rv
        if end - start >= min_rep_frames:
            reps.append({"start_frame": int(start), "bottom_frame": int(b), "end_frame": int(end)})

    return reps
