# Low-Bar Back Squat Technique Standards

**Skill id:** `low-bar-squat-standards` &nbsp;&nbsp; **Version:** `2.0.0`

**Source document:** Document_for_skill.pdf (appended to AI_Engineer_Hiring_Assignment.pdf)

**Citation scheme:** Reference pages 1-35. Reference page N == combined PDF page N+3.

Every rule below cites the reference pages it is derived from. Thresholds marked threshold_source=assumption are engineering assumptions made by this application, NOT requirements stated in the document, and are surfaced as such in the output.

> This file is **generated** from `app/skill/low_bar_squat_skill.json` by
> `tools/render_skill_md.py`. Edit the JSON, not this file.

---

## 1. Document definitions used by the rules

| Term | Definition | Source | Quote |
|---|---|---|---|
| **back_angle** | The angle formed by the plane of the torso and the floor (assumed horizontal). | p9, p22, p33 | "The back angle is formed by the plane of the torso and the floor, which is assumed to be horizontal" |
| **hip_angle** | The angle formed by the plane of the torso and the femur. | p9 | "The hip angle is formed by the plane of the torso and the femur." |
| **knee_angle** | The angle formed by the femur and the tibia. | p9 | "The knee angle is formed by the femur and the tibia" |
| **depth_landmark_a** | The top of the patella. | p2 | "The top of the patella (A)" |
| **depth_landmark_b** | The hip joint, identified by the apex in the crease of the shorts. | p2 | "the hip joint, as identified by the apex in the crease of the shorts (B)" |
| **midfoot** | The point on the sole of the foot halfway between the heel and the toe. The lifter/barbell system is in balance when the bar is directly over the midfoot. | p8, p9, p11, p33 | "the midfoot is exactly halfway between either end of the sole of the shoe" |
| **floor** | The horizontal plane the lifter stands on. The document assumes the floor is horizontal when defining the back angle, so a tilted camera must be corrected for before the back angle can be measured. | p9, p22, p33 | "" |

---

## 2. Rule set

14 rules. Each cites the reference pages it comes from, states whether it can be assessed from a side-view recording, and separates *document-stated* criteria from *application assumptions*.

### DEPTH-01 — Full depth — hip below top of patella

- **Source pages:** p2, p16, p33, p35
- **Document quote:** "Correctly is deep, with hips dropping below level with the top of the patellas"
- **Assessability:** Assessable from a side view
- **Criterion:** At the bottom of the repetition, depth landmark B (hip joint) must be lower than depth landmark A (top of patella).
- **Measurement:** `depth_px`
- **Requires visible landmarks:** hip, knee
- **Verdict:** meets standard / does not meet standard / cannot assess
- **Thresholds:** `{"tolerance_px": 8}` (assumption)
- **Threshold note:** The document states the rule as binary (below parallel) and gives no tolerance. 8 px absorbs landmark jitter at the ~600-1000 px body height typical of a side-view recording; it is NOT a document requirement.
- **Cannot assess because:** Pose landmarks for the hip or knee were not available at the bottom of the rep, so depth could not be measured.
- **Feedback when met:** Reached full depth: the hip dropped below the top of the patella at the bottom of the rep.
- **Feedback when not met:** Did not reach full depth: the hip stayed above the top of the patella at the bottom of the rep. The document treats anything short of this as a partial squat (reference p16), which stresses the knees and quadriceps without loading the hamstrings, adductors and glutes.

### ANGLE-01 — Back angle — torso inclined, not vertical

- **Source pages:** p9, p22, p33, p35
- **Document quote:** "the back is at an angle (about 45 degrees) that will place the bar over the middle of the foot"
- **Assessability:** Assessable from a side view
- **Criterion:** The back angle (torso plane against the floor) should be roughly 45 degrees at the bottom of the rep — inclined, not vertical.
- **Measurement:** `back_angle_deg`
- **Requires visible landmarks:** shoulder, hip
- **Verdict:** meets standard / does not meet standard / cannot assess
- **Thresholds:** `{"reference_deg": 45, "tolerance_deg": 15}` (assumption)
- **Threshold note:** The reference value of 45 degrees is taken directly from the document (reference p22). The +/-15 degree tolerance band is an engineering assumption, not a document requirement.
- **Cannot assess because:** Torso landmarks were not available, or the torso was occluded so the shoulder-hip vector could not be measured reliably.
- **Feedback when met:** Back angle of {measured} degrees is consistent with the inclined torso the document describes for the low-bar squat.
- **Feedback when not met:** Back angle of {measured} degrees is {direction}. The document expects an inclined back of about 45 degrees; a vertical back is the most common error and it kills hip drive.

### ANGLE-02 — Hip and knee angles (diagnostic, observation only)

- **Source pages:** p9, p16
- **Document quote:** "The hip angle is formed by the plane of the torso and the femur. The knee angle is formed by the femur and the tibia"
- **Assessability:** Assessable from a side view
- **Criterion:** The document defines the hip angle and knee angle as diagnostic measures of the squat but states no pass/fail threshold for either. These are reported as observations.
- **Measurement:** `hip_angle_deg,knee_angle_deg`
- **Requires visible landmarks:** shoulder, hip, knee
- **Verdict:** none — the document defines this measure but sets no pass/fail threshold, so it is reported as an observation. Producing a verdict here would be an unsupported rule.
- **Threshold note:** No document threshold exists for these angles, so no meets/does-not-meet verdict is produced. Reporting a verdict here would be an unsupported rule.
- **Cannot assess because:** Landmarks required to form the hip or knee angle were not available.
- **Feedback when met:** Hip angle {hip_angle_deg} degrees, knee angle {knee_angle_deg} degrees at the bottom of the rep.
- **Feedback when not met:** Hip angle {hip_angle_deg} degrees, knee angle {knee_angle_deg} degrees at the bottom of the rep.

### BAR-01 — Bar path — bar stays over the midfoot

- **Source pages:** p8, p9, p11, p33
- **Document quote:** "good technique in barbell training is easily and understandably defined as the ability of the lifter to keep the bar vertically aligned with the balance point"
- **Assessability:** Assessable from a side view
- **Criterion:** Throughout the repetition the barbell should remain horizontally over the midfoot balance point, so that horizontal bar motion does no work against gravity.
- **Measurement:** `bar_drift_from_midfoot_px,bar_drift_samples,bar_drift_range_px`
- **Requires visible landmarks:** bar
- **Verdict:** meets standard / does not meet standard / cannot assess
- **Thresholds:** `{"tolerance_px": 25, "min_samples": 3, "min_sample_fraction": 0.2}` (assumption)
- **Threshold note:** The document requires the bar to be directly over the midfoot through the complete range of motion (reference p14) but gives no numeric tolerance. 25 px is an engineering assumption reflecting typical landmark jitter, and is NOT a document requirement. min_sample_fraction is the share of the repetition's frames in which both the bar and the midfoot must be locatable for the measurement to support a verdict at all - a verdict resting on one or two frames is not evidence. The reported figure also carries the range it takes across the camera-roll uncertainty band.
- **Cannot assess because:** The bar position or the midfoot reference point could not be determined from this recording.
- **Feedback when met:** Bar path stayed over the midfoot balance point (maximum horizontal deviation {measured} px).
- **Feedback when not met:** Bar drifted {measured} px horizontally from the midfoot. The document states that any horizontal component of bar motion is not work against gravity, and that flopping forward lets the bar drop forward of the midfoot (reference p33).

### BAR-02 — Bar placement — low bar, just below the scapular spine

- **Source pages:** p13, p29, p30
- **Document quote:** "The bar should therefore be in the lowest secure position it can occupy on the back, right below the spine of the scapula"
- **Assessability:** Partially assessable from a side view
- **Criterion:** The bar rests on the posterior deltoids, just below the spine of the scapula, not high on the traps.
- **Measurement:** `bar_height_vs_shoulder_px`
- **Requires visible landmarks:** bar, shoulder
- **Verdict:** meets standard / does not meet standard / cannot assess
- **Threshold note:** The document criterion is anatomical (just below the scapular spine). A side view cannot confirm the exact contact point on the back, so this rule can only ever be partially assessed.
- **Cannot assess because:** The bar could not be located relative to the shoulders in this recording.
- **Feedback when met:** Bar height is consistent with the low-bar position on the posterior deltoids. This is an estimate: confirming the exact contact point below the scapular spine requires a rear view.
- **Feedback when not met:** Bar appears higher than the low-bar position described in the document.

### HIP-01 — Hip drive — hips go up, not forward

- **Source pages:** p23, p35
- **Document quote:** "come up out of the bottom by driving your butt straight up in the air. Up, not forward."
- **Assessability:** Assessable from a side view
- **Criterion:** During the ascent the hips should rise more than they travel forward.
- **Measurement:** `hip_drive_ratio`
- **Requires visible landmarks:** hip
- **Verdict:** meets standard / does not meet standard / cannot assess
- **Thresholds:** `{"min_ratio": 1.0}` (assumption)
- **Threshold note:** The document requires 'up, not forward' but gives no numeric ratio. A ratio of 1.0 (as much vertical as horizontal hip travel) is an engineering assumption, not a document requirement.
- **Cannot assess because:** Hip trajectory during the ascent could not be measured.
- **Feedback when met:** Hips drove up and back rather than forward out of the bottom, matching the document's 'up, not forward' instruction.
- **Feedback when not met:** Hips travelled forward as much as they travelled up out of the bottom. The document is explicit that the lifter must come up out of the bottom driving the hips straight up, not forward, and that lifting the chest instead of driving the hips kills power out of the bottom.

### KNEE-01 — Knee position — knees just forward of the toes

- **Source pages:** p22, p33, p35
- **Document quote:** "the knees are just a little forward of the toes"
- **Assessability:** Partially assessable from a side view
- **Criterion:** At the bottom of the rep the knee should be forward of the toe line by a small amount, and the hips should be back. The sagittal (forward/back) component is assessable; the knees-tracking-parallel-to-the-feet component is not.
- **Measurement:** `knee_forward_of_toe_px`
- **Requires visible landmarks:** knee, toe
- **Verdict:** meets standard / does not meet standard / cannot assess
- **Thresholds:** `{"min_px": -10, "max_px": 120}` (assumption)
- **Threshold note:** The document describes the knees as just a little forward of the toes but gives no measurement. The -10 px lower bound allows for knee and toe landmark noise and the 120 px upper bound is sized against typical shin length. Both are engineering assumptions, not document requirements.
- **Cannot assess because:** Knee or toe landmarks were not available, so knee position relative to the toes could not be measured.
- **Feedback when met:** Knees are forward of the toes by {measured} px, consistent with the bottom position the document describes.
- **Feedback when not met:** Knees sit {measured} px relative to the toe line. The document expects the knees just a little forward of the toes with the hips back.

### HIP-02 — Hips back at the bottom

- **Source pages:** p22
- **Document quote:** "the hips are back"
- **Assessability:** Assessable from a side view
- **Criterion:** At the bottom of the rep the hip should sit behind the ankle line, shifting load to the posterior chain rather than the knees.
- **Measurement:** `hip_behind_ankle_px`
- **Requires visible landmarks:** hip, ankle
- **Verdict:** meets standard / does not meet standard / cannot assess
- **Thresholds:** `{"min_px": -10}` (assumption)
- **Threshold note:** The document states the hips are back at the bottom without giving a measurement. The -10 px bound allows for hip and ankle landmark noise and is an engineering assumption, not a document requirement.
- **Cannot assess because:** Hip or ankle landmarks were not available at the bottom of the rep.
- **Feedback when met:** Hips are back over the heels at the bottom, as the document's bottom position describes.
- **Feedback when not met:** Hips are not back behind the ankles at the bottom. The document's bottom position has the hips back with the knees just a little forward of the toes.

### EYE-01 — Eye gaze down

- **Source pages:** p24, p26, p35
- **Document quote:** "look down at a point on the floor 4-5 feet in front of you"
- **Assessability:** Partially assessable from a side view
- **Criterion:** The head should be pitched down (chin toward chest) throughout the rep. The document links an upward gaze to lost hip drive and to an unsafe cervical position.
- **Measurement:** `head_pitch_deg`
- **Requires visible landmarks:** head
- **Verdict:** meets standard / does not meet standard / cannot assess
- **Thresholds:** `{"min_deg": 10}` (assumption)
- **Threshold note:** The document requires looking down at a point on the floor 4-5 feet ahead but does not specify a head angle. The 10 degree chin-down threshold is an engineering assumption, not a document requirement.
- **Cannot assess because:** Head landmarks were not available, or the head was outside the frame.
- **Feedback when met:** Head is pitched down {measured} degrees, consistent with the document's chin-down position.
- **Feedback when not met:** Head is pitched {measured} degrees. The document is explicit that failing to look down kills hip drive, and that an upward gaze puts the cervical spine in an unsafe position under load.

### STANCE-01 — Stance width — heels about shoulder width

- **Source pages:** p13, p19, p33, p35
- **Document quote:** "heels about shoulder width apart"
- **Assessability:** Not assessable from a side view
- **Criterion:** The heels are about shoulder width apart. A stance that is too narrow or too wide prevents proper depth.
- **Verdict:** meets standard / does not meet standard / cannot assess
- **Threshold note:** Left-right foot spacing cannot be determined from a side-view recording. A front or rear view is required.
- **Cannot assess because:** Stance width is not observable in a side view; a front or rear view is required.
- **Feedback when met:** Stance width cannot be assessed from a side-view recording. The document requires the heels about shoulder width apart.
- **Feedback when not met:** Stance width cannot be assessed from a side-view recording.

### STANCE-02 — Toe angle — about 30 degrees out

- **Source pages:** p13, p19, p33, p35
- **Document quote:** "toes pointed out at about 30 degrees"
- **Assessability:** Not assessable from a side view
- **Criterion:** The toes point outward by about 30 degrees.
- **Verdict:** meets standard / does not meet standard / cannot assess
- **Threshold note:** Toe rotation is only observable from a front or rear view.
- **Cannot assess because:** Toe angle is not observable in a side view; a front or rear view is required.
- **Feedback when met:** Toe angle cannot be assessed from a side-view recording. The document specifies about 30 degrees of toe-out.
- **Feedback when not met:** Toe angle cannot be assessed from a side-view recording.

### KNEE-02 — Knees tracking parallel to the feet (no valgus)

- **Source pages:** p13, p33, p35
- **Document quote:** "the knees are shoved out so that the thighs stay parallel to the feet"
- **Assessability:** Not assessable from a side view
- **Criterion:** The thighs should stay parallel to the feet, meaning the knees are shoved out and do not collapse inward.
- **Verdict:** meets standard / does not meet standard / cannot assess
- **Threshold note:** Medial-lateral knee position is not observable in a side view. This is the single most common cause of depth failure according to the document, so it is reported as cannot assess rather than silently passing.
- **Cannot assess because:** Medial-lateral knee position is not observable in a side view; a front or rear view is required.
- **Feedback when met:** Whether the knees stay parallel to the feet (knees shoved out, no inward collapse) cannot be assessed from a side-view recording.
- **Feedback when not met:** Whether the knees stay parallel to the feet cannot be assessed from a side-view recording.

### GRIP-01 — Grip width and wrist alignment

- **Source pages:** p28, p29
- **Document quote:** "16-17 inches between the ends of the outside knurl, and 32 inches between the finger marks"
- **Assessability:** Not assessable from a side view
- **Criterion:** The hands sit between the finger marks of the bar (narrower grip), the thumbs wrap on top, and the wrists stay in line with the forearms so the bar's weight sits on the back.
- **Verdict:** meets standard / does not meet standard / cannot assess
- **Threshold note:** Grip width cannot be measured reliably from a side view at typical recording distance.
- **Cannot assess because:** Grip width and wrist alignment are not reliably observable in a side view.
- **Feedback when met:** Grip width and wrist alignment cannot be assessed from a side-view recording.
- **Feedback when not met:** Grip width and wrist alignment cannot be assessed from a side-view recording.

### RACK-01 — Rack height at mid-sternum

- **Source pages:** p27
- **Document quote:** "Set the rack height so that the bar in the rack is at about the level of your mid-sternum"
- **Assessability:** Not assessable from a side view
- **Criterion:** The rack is set so the bar sits at mid-sternum height, which is below the top of the traps because this is a low-bar position.
- **Verdict:** meets standard / does not meet standard / cannot assess
- **Threshold note:** A rack height measurement requires the lifter to be seen unracking in a rack with a known reference; it is not part of the squat itself.
- **Cannot assess because:** Rack height is a setup measurement, not observable during the squat itself.
- **Feedback when met:** Rack height cannot be assessed from a side-view recording of the squat.
- **Feedback when not met:** Rack height cannot be assessed from a side-view recording of the squat.

---

## 3. Assessability summary for a side-view recording

| Assessable | Partially assessable | Not assessable |
|---|---|---|
| DEPTH-01, ANGLE-01, ANGLE-02, BAR-01, HIP-01, HIP-02 | BAR-02, KNEE-01, EYE-01 | STANCE-01, STANCE-02, KNEE-02, GRIP-01, RACK-01 |

The application returns `cannot assess` for the rules in the right-hand column and marks the middle column with an explicit uncertainty note, rather than guessing.

---

## 4. Document summary (the claims the skill encodes)

| Ref page | Claim |
|---|---|
| p1 | The squat is the only weighted movement that directly trains the posterior chain (hip drive); a low-bar back squat is the way to recruit the most of it. |
| p2 | Depth is judged from two landmarks: the top of the patella (A) and the hip joint at the apex of the crease of the shorts (B). B must drop below parallel with the ground. |
| p8 | The midfoot, halfway between heel and toe, is the balance point; the lifter/barbell system is in balance when the bar is directly over it. |
| p9 | The three diagnostic angles are the back angle (torso vs floor), the hip angle (torso vs femur) and the knee angle (femur vs tibia). |
| p11 | Good technique is defined as keeping the bar vertically aligned with the balance point; horizontal bar motion is not work against gravity. |
| p13 | The low-bar squat is the preferred form: bar in the lowest secure position just below the scapular spine, heels about shoulder width, toes out about 30 degrees, knees shoved out so the thighs stay parallel to the feet. |
| p16 | Correct squatting is deep, with the hips dropping below the top of the patellas; anything shallower is a partial squat that stresses the knees and quadriceps without the hamstrings, adductors and glutes. |
| p22 | The bottom position: feet flat, femurs parallel to the feet, hips back, knees just a little forward of the toes, back at about 45 degrees so the bar is over the middle of the foot. |
| p23 | Come out of the bottom driving the hips straight up, not forward. Hip extension is the first part of the upward drive. |
| p24 | Look down at a point on the floor 4-5 feet in front of you; an upward gaze kills hip drive and puts the cervical spine in an unsafe position. |
| p29 | Place the bar just under the spine of the scapula; it should feel like a shelf under the traps on top of the posterior deltoids. |
| p33 | The back angle during the drive up is critical; flopping forward lets the bar drop forward of the midfoot. Accept nothing less than full depth. |
| p35 | The eight things lifters get wrong: depth, knee position, stance, eye gaze, back angle, hip drive, bar placement, rack height. |

---

## 5. Output schema

```json
{
  "rep_id": 1,
  "start_frame": 13, "bottom_frame": 61, "end_frame": 108,
  "bottom_timestamp_s": 2.033,
  "overall": "does not meet standard",
  "measurements": {
    "depth_px": -21.0,
    "back_angle_deg": 89.9,
    "bar_drift_from_midfoot_px": 75.5,
    "hip_drive_ratio": 4.9,
    "camera_roll_deg": -21.8,
    "occlusion": { "shoulder": true, "head": true, "hip": false }
  },
  "findings": [
    {
      "rule_id": "DEPTH-01",
      "rule": "Full depth - hip below top of patella",
      "source_pages": [2, 16, 33, 35],
      "source_quote": "Correctly is deep, with hips dropping below level with the top of the patellas",
      "status": "does not meet standard",
      "measurement": { "depth_px": -21.0 },
      "frame": 61,
      "timestamp_s": 2.033,
      "feedback": "Did not reach full depth ...",
      "uncertainty": null
    }
  ],
  "uncertainty_notes": ["..."]
}
```
