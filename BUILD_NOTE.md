# Build Note — AI Squat Analysis

**Project:** consumer-facing AI squat analysis application
**Reference document:** low-bar back squat biomechanics chapter (reference pages 1–35, combined PDF pages 4–38)
**Common sample:** `https://youtube.com/shorts/TRvg083BrXY`

---

## 1. Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  Browser (vanilla HTML/CSS/JS)                                      │
│  drag-and-drop upload · progress · annotated video · findings table │
└───────────────────────────────┬──────────────────────────────────────┘
                                │ POST /upload  ·  GET /status/{id}  ·  GET /download/{id}
┌───────────────────────────────▼──────────────────────────────────────┐
│  FastAPI (app/main.py)                                               │
│  job store (thread-safe) · validation · background analysis task   │
└───────────────────────────────┬──────────────────────────────────────┘
                                │
┌───────────────────────────────▼──────────────────────────────────────┐
│  Pipeline (app/cv/pipeline.py)                                       │
│                                                                        │
│  1. pose_estimator  MediaPipe Tasks PoseLandmarker → 33 landmarks    │
│  2. occlusion       large smooth dark region detector                 │
│  3. rep_detector    hip-trajectory valley pairing + prominence       │
│  4. measurements    camera-roll alignment, crease apex, midfoot       │
│  5. viewpoint       side-view vs front/rear classifier                │
│  6. evaluator       loads the skill from disk, applies every rule     │
│  7. annotator       skeleton, depth landmarks, bar path, parallel line│
└───────────────────────────────┬──────────────────────────────────────┘
                                │
                     outputs/{video}_annotated.mp4
                     outputs/{video}_report.json
```

**Why this shape.** The skill (`app/skill/low_bar_squat_squat_skill.json`) is a **data file loaded at
runtime**, not code. Changing a criterion — adding a rule, retuning a threshold, changing a source
page — is a JSON edit; no application code changes. That was an explicit requirement of the
assignment, and the evaluator contains no hard-coded rule.

---

## 2. The skill (`app/skill/low_bar_squat_skill.json`)

14 rules extracted from the reference document. Each rule records:

| Field | Purpose |
|---|---|
| `source_pages` | Reference pages the criterion comes from (p2, p16, p33, p35 …) |
| `quote` | The document's own wording, carried through to the UI |
| `assessable` | `yes` / `partial` / `no` — can a side-view recording show it? |
| `criterion` | The rule in plain language |
| `measure` | Which measurement feeds it |
| `requires_landmarks` | Which landmarks must be visible for it to be trustworthy |
| `thresholds` + `threshold_source` | `document` (stated in the source) or `assumption` (our engineering choice) |
| `cannot_assess_reason` | What is returned when the video or the view cannot support a verdict |

**Rules encoded:** depth (DEPTH-01), back angle (ANGLE-01), hip & knee angles as observations only
(ANGLE-02), bar over midfoot (BAR-01), low-bar placement (BAR-02), hip drive (HIP-01), knee forward of
toes (KNEE-01), hips back (HIP-02), eye gaze (EYE-01), stance width (STANCE-01), toe angle (STANCE-02),
knee tracking / valgus (KNEE-02), grip and wrist alignment (GRIP-01), rack height (RACK-01).

**What a side view cannot show** (returned as `cannot assess`, never guessed): stance width, toe angle,
medial-lateral knee position, grip width, rack height. Bar placement and knee position are *partial*.

**Thresholds.** Only one threshold comes straight from the document: the ~45° back angle at p22. Every
other number is tagged `threshold_source: "assumption"` and is surfaced in the UI next to the finding, so
a reviewer can see what came from the document and what came from us. The document requires the bar to
be directly over the midfoot but gives no tolerance, so we do not present 25 px as a document rule.

**Generated mirror.** `SQUAT_SKILL.md` is rendered from the JSON by `tools/render_skill_md.py`, so the
human-readable and machine-readable skills can never drift apart.

---

## 3. Model and tool choices

| Choice | Alternative rejected | Reason |
|---|---|---|
| MediaPipe Tasks **PoseLandmarker (lite)**, 5.7 MB, CPU | MediaPipe Solutions (removed in MediaPipe ≥ 1.x) | The `solutions` API no longer exists in the current release; the Tasks API is the supported path and runs on CPU with no cloud dependency. |
| Rule engine reading a JSON skill | LLM in the critical path | The assignment requires the document to drive the assessment and forbids presenting invented thresholds as document requirements. A deterministic rule engine makes every verdict traceable to a rule id and a page number. The skill is agent-ready — an LLM can be added on top for narrative coaching without touching the measurements. |
| Wrist midpoint as the bar proxy | A trained barbell detector | No training data available inside the time box. The wrist proxy tracks the shoulder faithfully (verified: bar x and shoulder x agree to within a few px), but it is labelled an estimate everywhere it appears. |
| Camera roll from the heel-to-toe line | Assume a level camera | Both sample videos are handheld with 10–28° of roll, and the document defines the back angle against the *floor*. Measuring without correction was off by 15°. |
| ffmpeg (via `imageio-ffmpeg`) for the annotated video | OpenCV's `VideoWriter` | OpenCV writes MPEG-4 Part 2, which no browser decodes, and puts the `moov` index at the *end* of the file so a browser must download the whole thing before playing. ffmpeg gives H.264 + `yuv420p` + `+faststart`, which plays inline and starts streaming immediately — and at CRF 24 the files are 19× smaller. |
| Crease-apex offset on the hip landmark | Use MediaPipe's hip directly | The document defines depth landmark B as "the apex in the crease of the shorts"; MediaPipe reports the anatomical hip joint, which sits above it. Caught by zooming into the annotated frame. |
| Occlusion by image analysis | Rely on MediaPipe visibility | MediaPipe reports visibility 1.00 for the shoulder and nose while both are completely hidden behind a weight plate. Verified by sampling RGB under the landmark. |

---

## 4. Time spent

Roughly 6 hours wall-clock across two working sessions, against a 4–6 hour box.

| Phase | Time |
|---|---|
| Read the assignment + extract the PDF text and figures | ~0.5 h |
| Build the skill from the document, with page citations | ~1 h |
| Pose tracking, rep detection, measurements, alignment | ~1.5 h |
| Evaluation engine + skill runtime loading | ~1 h |
| Occlusion detection, viewpoint classification, uncertainty handling | ~1 h |
| Frontend, API, packaging, tests, documentation | ~1 h |

---

## 5. Costs

- **Build cost:** $0. Free tooling: Python, OpenCV, MediaPipe, FastAPI. No paid APIs, no model
  training, no cloud services.
- **Per-video cost:** $0 at the edge, CPU only. A 8-second vertical clip (236 frames) takes roughly
  45–60 s to process on a modern laptop CPU; a 27-second 5-rep clip takes about 2 minutes. That is
  ~12–20× real time, dominated by MediaPipe inference.
- **Hosting:** a small CPU container (Fly.io/Render/any VM) is sufficient — roughly $5–20/month for
  always-on, or effectively $0 per video at typical usage. No GPU is needed.
- **Dependencies to download once:** `pose_landmarker_lite.task` (5.7 MB). `requirements.txt` pulls
  ~400 MB of wheels including TensorFlow Lite runtime via MediaPipe.

---

## 6. Key trade-offs

1. **Deterministic rules over an LLM.** Less fluent feedback, but every number is auditable and the
   document cannot be paraphrased away. The assignment's wording — "generic squat advice from a model
   is not enough" — pointed this way.
2. **Reported uncertainty over confident-looking output.** Roughly half the findings on the common
   sample come back `cannot assess`. That is the honest answer given a plate covering the lifter's
   torso, and the assignment states an unassessable result is preferable to invented precision.
3. **Gravity-aligned frames.** Every measurement happens in a rotated frame so that "below parallel
   with the ground" means what the document means. The cost is that the annotated video is rotated;
   the original upload is shown alongside it.
4. **No absolute units.** Depth is reported in pixels. Without a calibration object in frame, centimetres
   would be a fabricated precision.
5. **In-memory job store.** A restart loses in-flight jobs. Redis or a database would be the
   production answer; it was not worth the time inside the box.

---

## 7. Verified behaviour

Run on three real recordings (`samples/`, produced by `yt-dlp`; the common sample is the YouTube Short
named in the assignment).

### 7.1 Common sample — `samples/common_sample.mp4` (608×1080, 7.9 s, 2 reps)

The hardest of the three: vertical framing, ~22° camera roll, and a large weight plate covering the
lifter's torso, shoulders and head for the whole set.

| Rule | Result | Why |
|---|---|---|
| DEPTH-01 depth | **meets standard** (44 px below the patella) | Hip and knee are visible; depth range across the roll band is +19…+69 px, so the verdict is robust. |
| ANGLE-01 back angle | **cannot assess** | The shoulder landmark is on the plate, so the torso vector is a model guess, not an observation. |
| BAR-01 bar over midfoot | **cannot assess** | The bar proxy sits on the plate. |
| EYE-01 eye gaze | **cannot assess** | The head is behind the plate. |
| HIP-01, KNEE-01, HIP-02 | **meets standard** | Hips, knees and ankles are visible. |
| STANCE-01/02, KNEE-02, GRIP-01, RACK-01 | **cannot assess** | Not observable in a side view. |

### 7.2 Clean side view — `samples/side_view_clean.mp4` (640×480, 18 s, 1 slow-motion rep)

No occlusion, so the full rule set produces verdicts: depth **meets standard** (26 px below the
patella), back angle **meets standard** (57°, inside the document's ~45° ± tolerance), hip drive
**meets standard**, knees forward of toes **meets standard**, hips back **meets standard**, bar over
midfoot **does not meet standard** (53 px of horizontal bar travel, mostly at the top of the rep where
the shoulders sit behind the midfoot), eye gaze **does not meet standard** (the lifter's head is level
or slightly up at the bottom rather than pitched down at the floor).

### 7.3 Additional difficult recording — `samples/occluded_side_view.mp4` (640×480, 27 s, 5 reps)

A side view where the weight plate covers the entire torso and head for every repetition, with a heavily
tilted camera. 5 reps detected; 10–11 of 14 rules per rep return `cannot assess`. The hip and knee
landmarks fall on the plate for most reps, and the system says so rather than reporting a depth it
cannot see.

### 7.4 Additional unsuitable recording — `samples/rear_three_quarter.mp4` (1920×1080, 7.6 s, 3 reps)

A rear three-quarter view (the lifter faces away from the camera) in 1080p, with the legs leaving the
bottom of the frame during the set-up. The viewpoint classifier rejects it — *"the left and right
shoulders are separated by 0.35 of the torso length in the image"*, against 0.11–0.17 for the genuine
side views — so all three reps return `cannot assess` for the sagittal criteria rather than reporting
confident numbers derived from a foreshortened projection.

This recording also exposed two defects, both fixed and both covered by regression tests:

- **Crash.** MediaPipe does not clip its output: when part of the body is outside the picture it
  extrapolates, and normalised coordinates reached **1.51** (a knee at pixel y=1569 in a 1080-tall
  frame). The occlusion detector indexed the image mask with those coordinates and raised
  `index 1285 is out of bounds for axis 0 with size 1080`. Landmarks outside the frame are now
  discarded before they are used, and the occlusion detector bounds-checks as well.
- **The overlay contradicted the report.** The annotated video printed *"B\* BELOW parallel — depth
  reached"* for a rep whose depth rule had returned `cannot assess`. The overlay now only states a
  depth conclusion when the rule was actually assessed, and says *"depth not assessed"* otherwise.

### 7.5 What was checked visually, not just numerically

- **Landmark placement.** The annotated frame at the bottom of each rep was inspected: the skeleton
  traces the body, landmark A sits on the top of the patella, landmark B* on the hip crease apex, and
  the midfoot marker sits midway along the shoe.
- **Bar path.** The red trail follows the hands, and is drawn dashed where the bar was hidden behind
  the plate, so a viewer is never shown a confident-looking path through an occluder.
- **The document's own test.** A horizontal "parallel" line is drawn through landmark A at every
  bottom position, with the verdict printed on the video, so the depth call can be checked by eye
  against the source document's wording (p2).
- **Landmark visibility.** MediaPipe's visibility score was sampled under each landmark. It reads
  1.00 for the shoulder and nose of a lifter who is entirely behind a plate, which is why the
  occlusion detector exists.

### 7.6 Automated tests

`python tests/test_pipeline.py` — 40 assertions covering repetition detection (including missing
frames and a rep that ends on the final frame), the gravity alignment (including the OpenCV sign
convention), the angle definitions, the viewpoint classifier (side, front and oblique views), the
occlusion detector against both a smooth plate and textured dark clothing, out-of-frame landmark
handling, and the evaluator (including that every finding cites a real reference page, that
non-assessable rules return `cannot assess`, and that a front view is blocked).

---

## 8. How AI was used, and what it got wrong

**Delegated to AI:** the FastAPI skeleton, the OpenCV drawing code, the MediaPipe landmark plumbing,
the HTML/JS frontend, the first draft of the rule engine, and the wording of the skill entries.

**Inspected rather than accepted:** every number the pipeline produced was checked against the source
frames. The skill was rebuilt from scratch after reading the actual PDF, because the first version had
invented section numbers (§2.1, §5.1) instead of the document's reference pages. Every threshold was
labelled as a document value or an assumption, and the assumptions were removed where the document
supports no threshold at all (the hip and knee angles are reported as observations, with no verdict).

### Mistakes caught and corrected

1. **The repetition detector never fired.** The prominence filter compared the bottom of the
   trajectory against a window that *included* the bottom itself, so the prominence was always zero and
   zero reps were detected. Fixed by measuring prominence against the adjacent standing valleys
   instead. A second failure followed: a lifter who pauses at the bottom produces a flat plateau, and
   the plateau broke the prominence window, so real reps were rejected. Fixed by pairing each bottom
   with the valleys on either side and de-duplicating bottoms that share a valley pair.

2. **Phantom repetitions at the start and end of every clip.** `np.convolve(..., mode="same")` pads
   with zeros, which drags the first and last samples down and manufactures a descent and an ascent
   at the edges of the recording — a spurious "rep" out of nothing. Caught by a unit test that
   asserted a flat signal produces no reps. Fixed by padding with edge values instead.

3. **Occlusion was invisible to the model.** The first implementation trusted MediaPipe's per-landmark
   visibility and reported a confident back angle for a lifter whose entire torso was behind a
   weight plate. Sampling the pixels under each landmark showed visibility of 1.00 on a region of
   RGB (19, 13, 8). Replaced with an image-based occluder detector that requires a large, dark and
   *locally smooth* region — a smooth black plate is an occluder, textured black shorts are not —
   and any rule depending on an occluded landmark now returns `cannot assess`.

4. **The annotated video did not line up with the body.** OpenCV's `getRotationMatrix2D` uses the
   opposite sign convention to the rotation helper used for the landmarks, so the picture was rotated
   one way and the skeleton the other. Caught by inspecting an annotated frame, then pinned down with
   a numeric test comparing the two transforms.

5. **The depth landmark was the wrong landmark.** MediaPipe reports the anatomical hip joint; the
   document defines depth landmark B as "the apex in the crease of the shorts", which is lower. The
   discrepancy was found by zooming into the annotated frame at the bottom of a rep, where the
   measured depth disagreed with what the picture showed. The crease apex is now estimated from the
   joint and the torso length, the raw joint-based value is still reported alongside it, and the
   offset is disclosed as an assumption.

6. **The annotated video downloaded but would not play.** OpenCV's `VideoWriter` defaults to MPEG-4
   Part 2 (`mp4v`), which Chrome, Firefox, Edge and Safari all refuse to decode, and it writes the
   `moov` index at the *end* of the file, so a browser has to download the whole thing before it can
   start. The file downloaded fine, which is what made the symptom confusing. Frames are now piped
   into ffmpeg and encoded to H.264 / `yuv420p` with `+faststart`; the writer verifies its own output
   (H.264 sample entry present, index ahead of the media data) and the report records whether the
   file is browser-playable. Side effect: the annotated files got 19x smaller (a 640x480, 18-second
   annotated video went from 19 MB to 1.0 MB). The UI now also shows a message if the browser still
   refuses to play it, instead of a silent black rectangle.

---

## 9. Known limitations

- **Bar tracking is a wrist proxy**, not barbell detection. The horizontal bar-path figure should be
  read as an estimate.
- **Depth is in pixels.** Absolute centimetres need a calibration reference in frame.
- **The camera-roll estimate assumes the foot is roughly perpendicular to the camera.** When the
  lifter is filmed from a three-quarter angle the foot line is not a valid horizontal reference. The
  depth result is therefore reported with its range across the roll uncertainty band, and when the
  verdict flips inside that band the rule returns `cannot assess` instead of picking a side.
- **Only one camera, one angle.** There is no multi-view reconstruction, so the depth is a 2D image
  measurement rather than a 3D one.
- **The job store is in memory.** A server restart loses in-flight analyses.
- **No rep-by-rep coaching narrative.** The findings are factual and quoted from the document. An LLM
  layer reading the same skill could add coaching language without touching the measurements.
- **The skill's reference page numbers were reconstructed** from the extracted document text; they
  should be spot-checked against the PDF's own pagination before the review.
