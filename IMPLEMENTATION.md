# How to Implement This Project — Step by Step

This is the build order I used, with the reasoning behind each step and the traps I hit. It assumes
you have the assignment PDF and about 4–6 hours.

---

## Phase 0 — Read what the PDF actually asks for (30 min)

The PDF is two documents stapled together, and they have different jobs.

**Pages 1–3 are the assignment.** They define:
- the objective: a consumer app that takes a side-view squat video, annotates it, and assesses it
  against the attached reference document;
- the four requirement groups (skill extraction, video processing, movement annotation, assessment,
  consumer experience);
- what to submit (working app, source, build note, AI account, **evidence from the common sample plus
  one additional difficult or unsuitable recording**);
- how it is evaluated (accuracy and defensible evidence over visual polish).

Two instructions in there change how you build:

> "Cite its page numbers as reference pages 1-35 (combined PDF pages 4-38)."

So the reference document's page 1 is the combined PDF's page 4. Every citation you write must use the
reference numbering. Get this wrong and every finding in your app is traceable to the wrong place.

> "Do not add unsupported thresholds or rules and present them as document requirements."

This is the single most important line for the evaluation. Every numeric threshold you invent must be
labelled as yours, not the document's.

**Pages 4–38 are the reference document** — a chapter on the low-bar back squat. It is prose, not a
checklist, so the criteria have to be *extracted*, not copied. The load-bearing, measurable statements
are:

| Ref page | What it states | Becomes a rule |
|---|---|---|
| p2 (Fig 2-1) | Depth landmarks: **A** = top of the patella, **B** = hip joint at the apex of the crease of the shorts. "The B side of the plane formed by these two points must drop below parallel with the ground." | Depth |
| p8–p9 (Fig 2-5) | The **midfoot** (halfway between heel and toe) is the balance point; the bar must be over it. Three diagnostic angles: back angle (torso vs **floor**), hip angle (torso vs femur), knee angle (femur vs tibia) | Bar path, back angle |
| p11 | "Good technique ... is the ability of the lifter to keep the bar vertically aligned with the balance point" | Bar path |
| p13, p29, p30 | Low bar sits in the lowest secure position, **just below the spine of the scapula**, on the posterior delts | Bar placement |
| p16 | "Correctly is deep, with hips dropping below level with the top of the patellas"; anything shallower is a partial squat | Depth |
| p20, p22, p33 | Bottom position: feet flat, **heels about shoulder width**, **toes out about 30°**, **knees just a little forward of the toes**, **hips back**, **back at about 45°** | Stance, knee position, hips back, back angle |
| p23 | "drive your butt straight up in the air. **Up, not forward**" | Hip drive |
| p24, p26 | Look **down** at a point on the floor 4–5 feet ahead; looking up kills hip drive | Eye gaze |
| p33 | "Flopping forward allows the bar to drop forward of the midfoot"; "DO NOT ACCEPT ANYTHING LESS THAN FULL DEPTH" | Bar path, depth |
| p35 | "The Important Things You're Going to Do Wrong": depth, knee position, stance, eye gaze, back angle, hip drive, bar placement, rack height | A checklist of the failure modes |

**Also extract:** the common sample video link is embedded as a hyperlink in the PDF
(`youtube.com/shorts/TRvg083BrXY`). Get it now — it is the input every candidate is judged on.

> **Practical tip.** If your assistant cannot read PDFs directly, extract the text with a script
> (`pypdf` → text, `pymupdf` → render pages to PNG so the figures can be read as images). Figure 2-1
> and Figure 2-5 are the two that matter and they resolve several ambiguities that the prose alone
> leaves open.

---

## Phase 1 — Turn the document into a skill (1 h)

**Do this before any computer vision.** If you cannot state the criteria precisely, you cannot decide
what to measure, and you will end up measuring the wrong thing and justifying it afterwards.

**Store the skill as data, not code.** A JSON file with one entry per rule:

```json
{
  "id": "DEPTH-01",
  "name": "Full depth — hip below top of patella",
  "source_pages": [2, 16, 33, 35],
  "quote": "Correctly is deep, with hips dropping below level with the top of the patellas",
  "criterion": "At the bottom of the repetition, landmark B (crease apex) must be lower than landmark A (top of patella).",
  "assessable": "yes",
  "measure": "depth_px",
  "requires_landmarks": ["hip", "knee"],
  "thresholds": { "tolerance_px": 8 },
  "threshold_source": "assumption",
  "threshold_note": "The document states the rule as binary and gives no tolerance. 8 px absorbs landmark jitter; it is NOT a document requirement.",
  "cannot_assess_reason": "Pose landmarks for the hip or knee were not available at the bottom of the rep."
}
```

Three fields carry the whole design:

- **`source_pages`** — the citation.
- **`assessable`** — `yes` / `partial` / `no`. This is the answer to "which criteria can be assessed
  from a side-view video and which cannot". Stance width, toe angle and knee valgus are `no`; bar
  placement and knee position are `partial`; the rest are `yes`.
- **`threshold_source`** — `document` vs `assumption`. Only the ~45° back angle from p22 is a document
  threshold. Everything else is our engineering choice and must say so.

**Two rules deserve special care.**

*The hip and knee angles.* The document defines them as diagnostic measures but sets **no** pass/fail
threshold. Inventing one would be exactly the "unsupported threshold presented as a document
requirement" the assignment forbids. Give the rule a `observation_only` flag and report the angle
without a verdict.

*Grip width and rack height.* Both are real document criteria (p28, p27) and both are unobservable
from a side view. Include them as rules so the coverage is honest, mark them `assessable: "no"`, and
return `cannot assess` with a reason. Do not silently drop them — a user comparing the app against the
document should see that you know they exist.

**Keep the skill out of the application code.** The evaluator loads the JSON at runtime. The
requirement is "separate enough to update without rewriting the application", and during the review
they may change a rule in the source document and ask how the assessment changes. If your rules live
in code, that question is expensive; if they live in a file, it is a one-line edit.

Generate a readable Markdown mirror from the JSON so the two cannot drift apart.

---

## Phase 2 — Ingestion (30 min)

Accept the upload, validate it, and run the analysis as a background job with progress the UI can
poll.

- `POST /upload` → `{job_id}`, job queued.
- `GET /status/{job_id}` → `{status, progress, error, reps, viewpoint, ...}`.
- `GET /download/{job_id}/video|report` → the outputs.

State the limits **in the interface**, not just in the code: max 60 seconds, max 100 MB, supported
formats, and the recording requirements (camera to the side, whole body and the floor under the feet
in frame, the bar not hidden behind a plate). The last one is not obvious to a user and it is the
single biggest determinant of whether the result is any good.

Validate before spending CPU: extension, size, and — importantly — duration, which needs the video
opened first. A two-minute clip should fail fast with a clear message, not after two minutes of
processing.

---

## Phase 3 — Track the movement (1.5 h)

### Pose landmarks

MediaPipe Tasks `PoseLandmarker` is the right default: 33 landmarks including hips, knees, ankles,
shoulders, **wrists, heels and foot indices**, runs on CPU, needs no training data.

```python
base_options = python.BaseOptions(model_asset_path="app/models/pose_landmarker_lite.task")
options = vision.PoseLandmarkerOptions(base_options=base_options,
                                        running_mode=vision.RunningMode.VIDEO)
detector = vision.PoseLandmarker.create_from_options(options)
```

Note the MediaPipe version trap: the old `mp.solutions.pose` API was removed in MediaPipe 1.x. Pin
your version and use the Tasks API. Also note the heel and toe landmarks are frequently absent or
misplaced when the lifter wears shoes — treat them as optional, never as a hard requirement.

### Repetitions and bottom positions

Detect the **hip's vertical position over time** and find the bottoms as local maxima (the hip is
lowest in the image). Getting this right took three attempts; learn from them:

1. **Compare prominence against the adjacent valleys, not against a window that includes the bottom.**
   Including the bottom makes the prominence zero and you detect nothing.
2. **Handle bottom plateaus.** A lifter who pauses at the bottom produces a flat stretch. Pair each
   bottom with the standing valleys either side of it, and de-duplicate bottoms that share a valley
   pair.
3. **Pad your smoothing with edge values.** `np.convolve(..., mode="same")` zero-pads, which drags
   the first and last samples down and manufactures a descent and an ascent at the edges of the clip
   — a phantom repetition out of nothing. Use `mode="edge"` padding. A unit test asserting "a flat
   signal produces zero reps" catches this immediately.

Also: a rep whose ascent finishes on the **final frame** has no two-sided local minimum, so include
one-sided extremum tests at the endpoints or you lose the last rep of every clip.

### The barbell

Do not build a barbell detector inside the time box. Use the **midpoint of the wrists** as a proxy for
the bar's centre of mass, and label it an estimate everywhere it appears. Verify the proxy is
faithful: if the bar's x and the shoulder's x track each other across the clip, the proxy is measuring
the body, not the hands.

---

## Phase 4 — Get the geometry right (1 h) — this is where the real work is

This is the phase most likely to make your numbers wrong, and the assignment's evaluation criteria
("do annotations match the video", "are limitations represented honestly") live here.

### Correct for camera roll

The document defines the back angle against the **floor** and depth against "parallel with the
ground". Both sample videos are handheld with 10–28° of roll. Measuring in the raw image frame is
wrong by that much.

Estimate the roll from the **heel-to-toe line** (the document says the feet are flat on the ground,
p22), take the median over the recording, and rotate every landmark so that image-down equals
gravity-down. Then a difference in y *is* a difference in height.

This is not cosmetic. A vertical line in the world projects to a tilted line in a rolled image, so
comparing the bar's x to the midfoot's x in the raw frame is meaningless — the two points are hundreds
of pixels apart vertically. The rotation is what makes the "bar over midfoot" test meaningful at all.

Watch the sign conventions: OpenCV's `getRotationMatrix2D` uses the **opposite** sign to the usual
rotation matrix. Get it wrong and the annotated video's skeleton will not sit on the body. Verify it
numerically rather than by eye.

### Use the document's landmarks, not the model's

The document's depth landmark B is "the apex in the crease of the shorts". MediaPipe reports the
**anatomical hip joint**, which sits above it. Estimate the crease apex from the joint and the torso
length, keep the raw joint-based number alongside it, and disclose the offset as an assumption.

Likewise, MediaPipe's knee is the knee joint; the document wants the **top of the patella**. It is
close enough to use, but say which one you used.

### Detect occlusion yourself

**MediaPipe's per-landmark visibility does not detect occlusion by an external object.** In the
common sample it reports visibility **1.00** for the shoulder and nose of a lifter who is entirely
behind a weight plate. Check this by sampling the pixels under the landmark — you will find
RGB (19, 13, 8), a black plate.

So detect occluders in the image: large, dark, **locally smooth** regions. The smoothness test is what
separates a plate from a lifter in black shorts (measured: plate = 6.2% of frame with local std 0.9;
shorts = 1.1% with local std 3.5). Any rule whose landmarks are hidden returns `cannot assess`.

### Classify the viewpoint

If the recording is not a side view, every sagittal criterion is meaningless — but the app will not
know that and will happily report confident nonsense. Two signals: the **horizontal separation of the
two ankles** relative to torso length (small in a side view, large from the front), and the
**direction of the heel-to-toe line** (roughly horizontal in a side view, pointing at the camera from
the front). Block the sagittal rules when the recording is not side-on.

### Quantify what you are unsure about

For any measurement whose value depends on an estimate you are not certain of, report the range. The
depth measurement is sensitive to the camera-roll estimate; compute it at the ends of the roll
uncertainty band and, **if the verdict flips inside that band, return `cannot assess`** rather than
picking whichever side of the uncertainty you land on. This is the difference between an assessment and
a guess, and it is exactly what the assignment asks for.

---

## Phase 5 — Evaluate against the skill (1 h)

For each rep, for each rule in the loaded skill:

1. If the rule is `assessable: "no"` → `cannot assess`, with the reason.
2. If the recording is not a side view → `cannot assess`, for the sagittal rules.
3. If a required landmark is occluded → `cannot assess`, naming the hidden landmark.
4. If the measurement is missing → `cannot assess`.
5. Otherwise apply the rule's thresholds → `meets standard` / `does not meet standard`.

Each finding carries: the rule id and name, the **reference pages**, the **document's own quote**, the
status, the **frame and timestamp**, the **measured value**, the feedback, and any uncertainty that
affects the conclusion.

The overall verdict for a rep: any rule failed → *does not meet standard*; otherwise any rule
unassessable → *cannot assess*; otherwise *meets standard*.

**Show the quote.** Putting the document's wording next to the verdict is what makes the result
defensible and shows the assessment is genuinely document-driven rather than generic model advice.

---

## Phase 6 — Annotate the video (45 min)

A playable annotated video is required, and the markings must follow the actual movement.

Draw: the skeleton; **landmark A** (top of patella) and **landmark B\*** (crease apex); the **midfoot**
balance point; the **floor line**; the **bar path**; a marker at each bottom position; a rep label;
and the uncertainty banner.

Two things that make the annotation trustworthy rather than decorative:

- **Draw the document's own test.** At each bottom position, draw a horizontal line through landmark
  A labelled "parallel", and print whether B\* is below it. The reviewer can then check the depth
  verdict by eye against p2.
- **Mark what you could not see.** Draw the bar path dashed where the bar was hidden behind an
  occluder, and say "bar occluded" at that point. A confident solid line through a weight plate is
  worse than no line.

Rotate the picture so the floor is horizontal, matching the frame the measurements were taken in, and
show the original next to it.

---

## Phase 7 — Consumer experience (45 min)

The user has to end up understanding: what happened, where the evidence is, what to do next.

Upload with drag and drop, a progress bar with a real percentage, a clear error message when
something fails. Then results: rep count, duration, an overall badge, the viewpoint check, the
annotated video, the downloadable report, the uncertainty notes, and a per-rep findings table showing
every rule, its status, the pages it came from, the quote, the measurement, and the uncertainty.

Use plain language for the verdict and the document's language for the standard. A non-technical user
should be able to see that "the hip crease apex was 26 px below the top of the patella" is the
evidence for "reached full depth".

---

## Phase 8 — Evidence, tests and the build note (1 h)

The assignment asks for **evidence from the common sample and at least one additional difficult or
unsuitable recording**, showing what you verified about landmark placement, bar path, source grounding
and final feedback.

- Run the common sample and **inspect the annotated frames yourself**. This is where the landmark
  errors surface.
- Find a second recording that stresses the system — heavily occluded, badly tilted, or not a side
  view. Download with `yt-dlp`.
- Write unit tests for the parts that are easy to get subtly wrong: repetition detection (missing
  frames, a rep ending on the last frame, a flat signal), the roll alignment and its sign convention,
  the angle definitions, the viewpoint classifier, the occlusion detector against both a smooth plate
  and textured clothing, and the evaluator (every finding cites a real page; non-assessable rules
  return `cannot assess`; a front view is blocked).
- Write the build note: architecture, model and tool choices, **actual** time spent, build and
  per-video costs, key trade-offs, known limitations, and the AI account with at least one real
  mistake you caught and corrected.

---

## Phase 9 — Prepare for the review (30 min)

The reviewers may supply a new video or change a rule in the source document.

- Changing a rule must be a **JSON edit and a restart**. Nothing in the evaluator should need
  changing. Verify this before the review.
- Be ready to walk the critical path: upload → pose tracking → alignment → measurement → rule → verdict.
- Be ready to investigate an incorrect result. The best defence is that every finding names the rule,
  the pages, the measurement and the uncertainty, so you can re-derive it.

---

## Summary of the order that matters

1. **Extract the criteria before writing any CV.** Otherwise you measure the wrong things.
2. **Make the skill a data file.** It is the requirement and it is also what makes the review question
   ("show how a change to the skill affects the assessment") cheap.
3. **Correct the geometry before trusting any number.** Camera roll, the document's own landmarks,
   occlusion, and viewpoint each independently produce confident wrong answers.
4. **Prefer `cannot assess` to a plausible number.** The assignment says so explicitly, and the
   evaluation weights evidence and reliability above polish.
5. **Verify visually, not just numerically.** Every real bug above was found by looking at an
   annotated frame, not by reading a log.
