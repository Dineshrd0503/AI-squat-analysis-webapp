"""Run the analysis pipeline on a video and print the findings.

Usage: python run_analysis.py <video> [output_dir]
"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.cv.pipeline import analyze_video


def main():
    video = sys.argv[1]
    outdir = sys.argv[2] if len(sys.argv) > 2 else "outputs"

    def cb(pct, stage=""):
        print(f"  [{pct:3d}%] {stage}", flush=True)

    report, annotated, reps = analyze_video(video, progress_cb=cb, output_dir=outdir)

    print("\n=== REPORT ===")
    print(f"video      : {report['source_file']}  {report['video_w']}x{report['video_h']} "
          f"{report['duration_s']}s {report['fps']}fps")
    print(f"reps       : {report['reps_detected']}")
    print(f"skill      : {report['skill']['skill_id']} v{report['skill']['version']} "
          f"({report['skill']['rules_evaluated']} rules)")
    print(f"annotated  : {annotated}")

    for rep in reps:
        print(f"\n--- REP {rep['rep_id']}  frames {rep['start_frame']}-{rep['end_frame']} "
              f"(bottom @ {rep['bottom_frame']} = {rep['bottom_timestamp_s']}s) ---")
        print(f"  overall: {rep['overall'].upper()}")
        print("  measurements: " + ", ".join(
            f"{k}={v}" for k, v in rep["measurements"].items()
            if k != "global_uncertainty" and v is not None))
        for f in rep["findings"]:
            src = f"p{f['source_pages']}" if f["source_pages"] else "n/a"
            print(f"  [{f['status']:>22}] {f['rule_id']} ({src}) {f['rule']}")
            print(f"        {f['feedback']}")
            if f.get("measurement"):
                print(f"        measured: {f['measurement']}")
            if f.get("uncertainty"):
                print(f"        ! {f['uncertainty']}")

    os.makedirs(outdir, exist_ok=True)
    with open(os.path.join(outdir, os.path.splitext(os.path.basename(video))[0] + "_report.json"),
              "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)


if __name__ == "__main__":
    main()
