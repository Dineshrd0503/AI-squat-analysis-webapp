"""Render the human-readable skill document from the machine-readable skill.

The JSON file is the single source of truth. This script regenerates
SQUAT_SKILL.md from it so the two can never drift apart.

Usage: python tools/render_skill_md.py
"""

from __future__ import annotations

import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_JSON = os.path.join(ROOT, "app", "skill", "low_bar_squat_skill.json")
OUT_MD = os.path.join(ROOT, "SQUAT_SKILL.md")

ASSESS_LABEL = {
    "yes": "Assessable from a side view",
    "partial": "Partially assessable from a side view",
    "no": "Not assessable from a side view",
}


def render() -> str:
    with open(SKILL_JSON, encoding="utf-8") as f:
        s = json.load(f)

    L: list[str] = []
    a = L.append

    a(f"# {s['title']}")
    a("")
    a(f"**Skill id:** `{s['skill_id']}` &nbsp;&nbsp; **Version:** `{s['version']}`")
    a("")
    a("**Source document:** " + s["source"]["document"])
    a("")
    a(f"**Citation scheme:** {s['source']['citation_scheme']}")
    a("")
    a(s["source"]["note"])
    a("")
    a("> This file is **generated** from `app/skill/low_bar_squat_skill.json` by")
    a("> `tools/render_skill_md.py`. Edit the JSON, not this file.")
    a("")

    a("---")
    a("")
    a("## 1. Document definitions used by the rules")
    a("")
    a("| Term | Definition | Source | Quote |")
    a("|---|---|---|---|")
    for key, d in s["definitions"].items():
        pages = ", ".join(f"p{p}" for p in d.get("source_pages", [])) or "-"
        a(f"| **{key}** | {d['definition']} | {pages} | \"{d.get('quote', '')}\" |")
    a("")

    a("---")
    a("")
    a("## 2. Rule set")
    a("")
    a(f"{len(s['rules'])} rules. Each cites the reference pages it comes from, states "
      "whether it can be assessed from a side-view recording, and separates "
      "*document-stated* criteria from *application assumptions*.")
    a("")

    for r in s["rules"]:
        pages = ", ".join(f"p{p}" for p in r["source_pages"])
        a(f"### {r['id']} — {r['name']}")
        a("")
        a(f"- **Source pages:** {pages}")
        a(f"- **Document quote:** \"{r.get('quote', '')}\"")
        a(f"- **Assessability:** {ASSESS_LABEL.get(r['assessable'], r['assessable'])}")
        a(f"- **Criterion:** {r['criterion']}")
        if r.get("measure"):
            a(f"- **Measurement:** `{r['measure']}`")
        if r.get("requires_landmarks"):
            a(f"- **Requires visible landmarks:** {', '.join(r['requires_landmarks'])}")
        if r.get("observation_only"):
            a("- **Verdict:** none — the document defines this measure but sets no "
              "pass/fail threshold, so it is reported as an observation. Producing a "
              "verdict here would be an unsupported rule.")
        else:
            a(f"- **Verdict:** meets standard / does not meet standard / cannot assess")
        if r.get("thresholds"):
            a(f"- **Thresholds:** `{json.dumps(r['thresholds'])}` "
              f"({r.get('threshold_source', 'assumption')})")
        if r.get("threshold_note"):
            a(f"- **Threshold note:** {r['threshold_note']}")
        if r.get("cannot_assess_reason"):
            a(f"- **Cannot assess because:** {r['cannot_assess_reason']}")
        a(f"- **Feedback when met:** {r.get('feedback_meets', '')}")
        a(f"- **Feedback when not met:** {r.get('feedback_fails', '')}")
        a("")

    a("---")
    a("")
    a("## 3. Assessability summary for a side-view recording")
    a("")
    yes = [r["id"] for r in s["rules"] if r["assessable"] == "yes"]
    partial = [r["id"] for r in s["rules"] if r["assessable"] == "partial"]
    no = [r["id"] for r in s["rules"] if r["assessable"] == "no"]
    a("| Assessable | Partially assessable | Not assessable |")
    a("|---|---|---|")
    a(f"| {', '.join(yes)} | {', '.join(partial)} | {', '.join(no)} |")
    a("")
    a("The application returns `cannot assess` for the rules in the right-hand "
      "column and marks the middle column with an explicit uncertainty note, "
      "rather than guessing.")
    a("")

    a("---")
    a("")
    a("## 4. Document summary (the claims the skill encodes)")
    a("")
    a("| Ref page | Claim |")
    a("|---|---|")
    for c in s["document_summary"]["core_claims"]:
        a(f"| p{c['ref']} | {c['text']} |")
    a("")

    a("---")
    a("")
    a("## 5. Output schema")
    a("")
    a("```json")
    a("""{
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
}""")
    a("```")
    a("")
    return "\n".join(L)


if __name__ == "__main__":
    md = render()
    with open(OUT_MD, "w", encoding="utf-8") as f:
        f.write(md)
    print(f"wrote {OUT_MD} ({len(md)} chars)")
