"""Summarise the JSON reports produced for the sample recordings."""
import json
import os

names = ["common_sample", "side_view_clean", "occluded_side_view"]
for n in names:
    p = f"outputs/{n}_report.json"
    if not os.path.exists(p):
        print(f"{n}: MISSING")
        continue
    r = json.load(open(p, encoding="utf-8"))
    vp = r.get("viewpoint", {})
    print(f'{n}: reps={r["reps_detected"]} view={vp.get("view")} roll={r.get("camera_roll_deg")}')
    for rep in r["reps"]:
        st = {}
        for x in rep["findings"]:
            st[x["status"]] = st.get(x["status"], 0) + 1
        m = rep["measurements"]
        ba = m.get("back_angle_deg")
        ba = round(ba, 1) if ba is not None else None
        occ = {k: v for k, v in (m.get("occlusion") or {}).items() if v}
        print(f'   rep{rep["rep_id"]} bottom@{rep["bottom_frame"]} -> {rep["overall"]}  {st}')
        print(f'      depth={m.get("depth_px")} back_angle={ba} '
              f'bar_drift={m.get("bar_drift_from_midfoot_px")} occluded={occ}')
    print()
