import json
import sys

r = json.load(open('outputs/occluded_side_view_report.json', encoding='utf-8'))
print('view:', r['viewpoint']['view'], '| roll', r['camera_roll_deg'], '+/-', r.get('camera_roll_uncertainty_deg'))
for rep in r['reps']:
    m = rep['measurements']
    occ = {k: v for k, v in (m.get('occlusion') or {}).items() if v}
    print(f"rep{rep['rep_id']}: frames {rep['start_frame']}-{rep['end_frame']} bottom@{rep['bottom_frame']}")
    print(f"   depth_px={m.get('depth_px')} raw_joint={m.get('depth_px_raw_hip_joint')} "
          f"range={m.get('depth_px_range')} unc={m.get('depth_uncertainty_px')}")
    print(f"   occ={occ}")
    print(f"   bar_drift={m.get('bar_drift_from_midfoot_px')} "
          f"bar_h_vs_sh={m.get('bar_height_vs_shoulder_px')} hip_drive={m.get('hip_drive_ratio')}")
    print(f"   back_angle={m.get('back_angle_deg')} head_pitch={m.get('head_pitch_deg')}")
