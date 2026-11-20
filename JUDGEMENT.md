# How the judgement is made

Every finding in the report comes from the same pipeline of gates. This document
sets out exactly what is measured, what it is compared against, and where the
threshold came from.

---

## 1. The decision cascade

For each repetition, for each rule in the skill, the gates are applied **in order**.
The first gate that applies decides the verdict.

| # | Gate | Result when it fires |
|---|---|---|
| 1 | **Rule is not observable from this viewpoint** (`assessable: "no"`) | `cannot assess` |
| 2 | **Recording is not a side view** (viewpoint classifier) | `cannot assess` |
| 3 | **A required landmark is hidden** by a large dark object | `cannot assess` |
| 4 | **The measurement is missing**, or rests on too few frames | `cannot assess` |
| 5 | **The verdict is not robust** to the camera-roll uncertainty | `cannot assess` |
| 6 | **Otherwise** | `meets standard` or `does not meet standard` |

Gates 1–5 all produce `cannot assess`. Only gate 6 produces a verdict, and a
verdict is only issued when the measurement is an observation, is supported by
enough frames, and survives the uncertainty in the camera-roll reference.

**Why gates come before thresholds.** The assignment says an unassessable result
is preferable to invented precision. A rule that is measured badly should say so
rather than produce a confident number built on a guess.

---

## 2. The rules, their measurements and their thresholds

`document` = stated in the supplied reference document.
`assumption` = our engineering choice, not a document requirement.

| Rule | Measurement | Pass condition | Threshold | Source |
|---|---|---|---|---|
| **DEPTH-01** depth | `depth_px` — crease apex (B\*) below top of patella (A), in a gravity-aligned frame | B\* below A | tolerance 8 px, plus the range across the roll band must not straddle parallel | assumption (document is binary) |
| **ANGLE-01** back angle | `back_angle_deg` — torso plane against the floor | 45° ± 15° | reference 45° is **document** (p22); the ±15° band is an assumption |
| **ANGLE-02** hip & knee angles | `hip_angle_deg`, `knee_angle_deg` | *none* | — | document defines the measures but sets no threshold, so this is reported as **observed**, with no verdict |
| **BAR-01** bar over midfoot | `bar_drift_from_midfoot_px` — largest horizontal distance between the tracked bar and the midfoot balance point | ≤ 25 px | assumption (document states the rule qualitatively, p8/p11/p14/p33) |
| **BAR-02** low-bar placement | `bar_height_vs_shoulder_px` — bar height relative to the shoulder | always "meets", with an estimate caveat | — | partial — a side view cannot confirm the contact point (p29, p30) |
| **HIP-01** hip drive | `hip_drive_ratio` — vertical hip travel ÷ forward hip travel during the ascent | ≥ 1.0 | assumption (document says "up, not forward", p23) |
| **KNEE-01** knee position | `knee_forward_of_toe_px` — knee ahead of the toe line at the bottom | between −10 px and 120 px | assumption (document says "just a little forward of the toes", p22) |
| **HIP-02** hips back | `hip_behind_ankle_px` — hip behind the ankle at the bottom | ≥ −10 px | assumption (document says "the hips are back", p22) |
| **EYE-01** eye gaze | `head_pitch_deg` — chin-down angle | ≥ 10° down | assumption (document says look down at the floor 4–5 ft ahead, p24) |
| **STANCE-01** stance width | — | — | — | **not observable** in a side view (p13, p19, p33) |
| **STANCE-02** toe angle | — | — | — | **not observable** in a side view (p13, p19, p33) |
| **KNEE-02** knee tracking | — | — | — | **not observable** in a side view (p13, p33, p35) |
| **GRIP-01** grip and wrists | — | — | — | **not observable** in a side view (p28, p29) |
| **RACK-01** rack height | — | — | — | **not observable** during the squat (p27) |

### The measurements in detail

**Depth (`depth_px`).** The document defines depth with two landmarks: A = the
top of the patella, B = the hip joint at the apex of the crease of the shorts
(p2). MediaPipe reports the *anatomical hip joint*, which sits above the crease
apex, so B\* is estimated as the joint plus `0.16 × torso length` along gravity.
The raw joint-based value is reported alongside it as `depth_px_raw_hip_joint`.

The measurement is a **height** difference, so it is only meaningful once the
camera roll is removed. The camera roll is estimated from the heel-to-toe line
(the document says the feet are flat on the ground, p22) and the median over the
recording is used. Because a roll error mixes horizontal separation into the
vertical difference, the depth is also computed at the ends of the roll
uncertainty band. If the verdict flips inside that band, the rule returns
`cannot assess` instead of picking a side.

**Back angle (`back_angle_deg`).** The angle of the shoulder→hip vector against
the floor, in the gravity-aligned frame. 90° is a vertical torso, 45° is the
inclined torso the document describes (p22). Unlike depth, this one is robust to
roll: the torso and the floor reference rotate together.

**Bar over midfoot (`bar_drift_from_midfoot_px`).** The midfoot is the
document's balance point — halfway between heel and toe (p8). The bar is
tracked through a wrist proxy. The figure is the largest horizontal distance
between the two across the repetition.

This is the most fragile measurement in the system, because the bar sits at
shoulder height and the midfoot is on the floor — hundreds of pixels apart
vertically — so a small error in the horizontal reference moves the result a long
way. Three guards apply:
- the bar and midfoot must be locatable on at least **20% of the repetition's
  frames** (and at least 3), otherwise the verdict is `cannot assess`;
- the verdict must hold across the **camera-roll uncertainty band**;
- the reported figure is shown **with the range it takes across that band**.

**Hip drive (`hip_drive_ratio`).** Vertical hip travel divided by forward hip
travel from the bottom of the rep to the top. The document says to come out of
the bottom driving the hips straight up, not forward (p23), so a ratio of 1.0
means as much up as forward.

---

## 3. The overall verdict for a repetition

```
if any rule failed          -> "does not meet standard"
else if any rule unassessable -> "cannot assess"
else                         -> "meets standard"
```

Rules that are structurally unobservable from a side view (stance width, toe
angle, knee tracking, grip, rack height) are **excluded** from the aggregation.
Otherwise no side-view recording could ever produce "meets standard", because
those five rules can never be assessed.

The badge at the top of the results panel aggregates across reps the same way.

---

## 4. Worked example — `samples/occluded_side_view.mp4`

This recording has the weight plate covering the lifter's torso for the whole
set, and the camera is tilted about 37°.

| Rep | Frames with bar+midfoot | BAR-01 verdict | Overall |
|---|---|---|---|
| 1 | 9 of 83 (11%) | `cannot assess` — too few frames | cannot assess |
| 2 | 6 of 90 (7%) | `cannot assess` — too few frames | cannot assess |
| 3 | 8 of 78 (10%) | `cannot assess` — too few frames | cannot assess |
| 4 | 5 of 79 (6%) | `cannot assess` — too few frames | cannot assess |
| 5 | 21 of 87 (24%) | `does not meet standard` — 143 px vs a 25 px tolerance | does not meet standard |

In every rep the **hip landmark is hidden by the plate**, so DEPTH-01, ANGLE-01,
ANGLE-02, HIP-01 and HIP-02 all return `cannot assess` — their measurements
would be model guesses rather than observations. The only rules that could be
judged were BAR-02 (bar placement, from the bar's height relative to the
shoulder) and EYE-01 (head pitch, since the head clears the plate at some
angles).

Rep 5 is the only rep where the bar path had enough usable frames to judge,
and it fails: the bar is 143 px from the midfoot. The figure's plausible range
across the roll band is 71–216 px, which is reported alongside it — the verdict
holds across that whole range, but the magnitude is imprecise.

---

## 5. What flips each verdict

| To move from `does not meet standard` to `meets standard` | To move to `cannot assess` |
|---|---|
| Lower the bar toward the midfoot (BAR-01) | Move the camera so the bar is not behind a plate |
| Pitch the head further down (EYE-01) | Frame the whole body including the feet |
| Tuck the knees further over the toes (KNEE-01) | Use a true side-on camera position |
| Lower the bar height relative to the shoulders (BAR-02) | Lower the camera roll below ~10° |
| | Point the camera at the lifter's side, not behind them |
| | Increase the resolution or move closer so the body fills the frame |

---

## 6. Changing a rule

The skill is data, not code. Edit `app/skill/low_bar_squat_skill.json`, then:

```powershell
python tools/render_skill_md.py     # regenerate the readable mirror
# restart the server
```

Changing a threshold, a reference page or adding a criterion needs no change to
the evaluator.
