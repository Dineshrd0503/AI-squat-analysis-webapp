# AI Squat Analysis

A consumer-facing application that takes a **side-view video of a barbell squat**, tracks the
movement, annotates it, and assesses each repetition against the supplied low-bar squat reference
document.

Every finding cites the reference page it comes from and is labelled one of
**meets standard** / **does not meet standard** / **cannot assess**. Criteria a side view cannot
reveal come back as `cannot assess` rather than being guessed.

---

## Quick start

```powershell
cd "D:\Ai assignment novilus"

# 1. Dependencies (Python 3.10+)
python -m pip install -r requirements.txt

# 2. Pose model (5.7 MB, downloaded once)
python -c "import urllib.request; urllib.request.urlretrieve(
  'https://storage.googleapis.com/mediapipe-models/pose_landmarker/pose_landmarker_lite/float16/latest/pose_landmarker_lite.task',
  'app/models/pose_landmarker_lite.task')"

# 3. Run
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>, drop in a video, and press **Analyze squat**.

### No server needed

Analyse a file straight from the command line:

```powershell
python run_analysis.py samples/common_sample.mp4 outputs
```

This prints the full report and writes `outputs/<name>_annotated.mp4` and `outputs/<name>_report.json`.

### Tests

```powershell
python tests/test_pipeline.py
```

---

## Layout

```
app/
  main.py                     FastAPI app: upload, status, download
  static/                     Frontend (vanilla HTML/CSS/JS, no build step)
  skill/
    low_bar_squat_skill.json  THE SKILL — rules, page citations, thresholds
  models/
    pose_landmarker_lite.task MediaPipe pose model
  cv/
    pipeline.py               end-to-end flow
    pose_estimator.py         MediaPipe landmark extraction
    rep_detector.py           repetition and bottom-position detection
    measurements.py           camera-roll alignment, angles, crease apex
    evaluator.py              loads the skill, applies every rule
    annotator.py              draws the annotated video
    occlusion.py              detects landmarks hidden behind objects
    viewpoint.py              side-view vs front/rear classifier
    video_writer.py           H.264 output the browser can actually play
tools/
  render_skill_md.py          regenerates SQUAT_SKILL.md from the JSON
  summarize_reports.py        summary of the sample reports
tests/
  test_pipeline.py            assertions over the CV, evaluation and output
samples/                      the four recordings used as evidence
outputs/                      annotated videos and JSON reports
evidence/                     extracted reference document text, annotated frames
SQUAT_SKILL.md                human-readable skill (generated from the JSON)
JUDGEMENT.md                  exactly how each verdict is reached
BUILD_NOTE.md                 architecture, time, costs, trade-offs, AI usage
IMPLEMENTATION.md             step-by-step build guide
```

---

## The annotated video plays in the browser

The annotated video is encoded as **H.264 in an MP4 container with `yuv420p`**, and the
index is written to the front of the file (`+faststart`), so the browser can start
playing immediately instead of downloading the whole file first. OpenCV's own video
writer cannot do this: it defaults to MPEG-4 Part 2, which browsers refuse to decode.

`imageio-ffmpeg` supplies a static ffmpeg binary. If it is unavailable the app falls
back to OpenCV's H.264 writer, and the report records whether the output is
browser-playable.

---

## The skill is a data file

`app/skill/low_bar_squat_skill.json` holds every criterion, its reference pages, the document's own
quotation, whether a side view can show it, and the thresholds. The evaluator loads it at runtime and
contains no hard-coded rule.

To change a rule — retune a threshold, add a criterion, correct a page number — edit the JSON and
restart the server. Then regenerate the readable mirror:

```powershell
python tools/render_skill_md.py
```

A threshold is tagged either `document` (stated in the source document) or `assumption` (our
engineering choice). Assumptions are surfaced in the UI beside the finding so nothing of ours is
presented as the document's requirement.

---

## Configuration

There are no secrets and no environment variables are required. The settings that exist are constants
at the top of `app/main.py`:

| Setting | Default | Meaning |
|---|---|---|
| `MAX_DURATION_SECONDS` | 60 | Longest accepted video |
| `MAX_FILE_MB` | 100 | Largest accepted upload |
| `SUPPORTED_EXTENSIONS` | mp4, mov, avi, mkv, webm | Accepted formats |

---

## Recording requirements (shown in the app)

- Camera **to the side** of the lifter, level with the hip.
- The **whole body and the floor under the feet** in frame.
- The **bar not hidden behind a plate** — otherwise the torso and head landmarks are model guesses
  and the affected rules are reported as `cannot assess`.
- 60 seconds or less.

---

## API

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/upload` | Multipart video upload; returns `{job_id}` |
| `GET` | `/status/{job_id}` | Progress, status, reps, viewpoint, skill info |
| `GET` | `/download/{job_id}/video` | Annotated MP4 |
| `GET` | `/download/{job_id}/report` | JSON report |
| `GET` | `/uploads/{filename}` | Original upload (for preview) |

---

## Sources

- Reference document: the low-bar squat chapter appended to the assignment PDF (reference pages
  1–35). Text extracted to `evidence/reference_document_text.txt`.
- Common sample: <https://youtube.com/shorts/TRvg083BrXY>
- Additional recordings: <https://youtu.be/u5rz6q0Uynw> (clean side view),
  <https://youtu.be/vQJ6OWJjvow> (heavily occluded). Both downloaded with `yt-dlp`.
