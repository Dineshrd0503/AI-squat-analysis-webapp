"""End-to-end HTTP test: upload a video, poll, download both outputs."""
import json
import os
import sys
import time
import urllib.request

BASE = "http://127.0.0.1:8000"
video = sys.argv[1] if len(sys.argv) > 1 else "samples/common_sample.mp4"

# wait for the server
for _ in range(40):
    try:
        with urllib.request.urlopen(BASE + "/", timeout=2) as r:
            print("server up:", r.read().decode().strip())
            break
    except Exception:
        time.sleep(1)
else:
    print("server never came up")
    sys.exit(1)

boundary = "----WebKitFormBoundaryxyz"
with open(video, "rb") as f:
    payload = f.read()
name = os.path.basename(video)
data = (
    f"--{boundary}\r\n".encode()
    + f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'.encode()
    + b"Content-Type: video/mp4\r\n\r\n" + payload + b"\r\n"
    + f"--{boundary}--\r\n".encode()
)
req = urllib.request.Request(
    BASE + "/upload", data=data,
    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    method="POST")
with urllib.request.urlopen(req, timeout=60) as r:
    job = json.loads(r.read().decode())
print("upload ->", job)
job_id = job["job_id"]

for i in range(90):
    with urllib.request.urlopen(f"{BASE}/status/{job_id}", timeout=30) as r:
        s = json.loads(r.read().decode())
    if i % 5 == 0 or s["status"] in ("completed", "failed"):
        print(f"  poll {i}: {s['status']} {s['progress']}%")
    if s["status"] in ("completed", "failed"):
        break
    time.sleep(2)

print("\nfinal status:", s["status"], "| error:", s.get("error"))
if s["status"] == "completed":
    print("viewpoint :", (s.get("viewpoint") or {}).get("view"))
    print("roll deg  :", s.get("camera_roll_deg"))
    print("skill     :", (s.get("skill") or {}).get("title"))
    print("reps      :", len(s.get("reps") or []))
    for kind, ext in (("video", ".mp4"), ("report", ".json")):
        with urllib.request.urlopen(f"{BASE}/download/{job_id}/{kind}", timeout=120) as r:
            blob = r.read()
        out = f"outputs/http_{job_id[:8]}_{kind}{ext}"
        with open(out, "wb") as f:
            f.write(blob)
        print(f"download {kind}: {r.status} {len(blob)} bytes -> {out}")
    # check the frontend is served
    with urllib.request.urlopen(BASE + "/", timeout=10) as r:
        print("index page:", r.status, len(r.read()), "bytes")
    with urllib.request.urlopen(BASE + "/static/app.js", timeout=10) as r:
        print("app.js    :", r.status, len(r.read()), "bytes")
