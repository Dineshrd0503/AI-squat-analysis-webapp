"use strict";

const API = window.location.origin;

const $ = (id) => document.getElementById(id);

const dropZone = $("dropZone");
const fileInput = $("fileInput");
const formActions = $("formActions");
const btnAnalyze = $("btnAnalyze");

const progressCard = $("progressCard");
const statusText = $("statusText");
const statusBadge = $("statusBadge");
const progressBar = $("progressBar");
const progressDetail = $("progressDetail");
const errorMsg = $("errorMsg");

const previewCard = $("previewCard");
const origVideo = $("origVideo");

const resultsCard = $("resultsCard");
const annVideo = $("annVideo");
const dlVideo = $("dlVideo");
const dlReport = $("dlReport");
const uncertaintyList = $("uncertaintyList");
const repsTbody = $("repsTbody");

const statReps = $("statReps");
const statDuration = $("statDuration");
const statOverall = $("statOverall");
const statView = $("statView");
const viewNote = $("viewNote");
const skillInfo = $("skillInfo");

let selectedFile = null;
let jobId = null;
let pollTimer = null;

wireVideoDiagnostics();

// ---------- helpers ----------
function show(el) { el.style.display = ""; }
function hide(el) { el.style.display = "none"; }
function setProgress(pct, text) {
  progressBar.style.width = pct + "%";
  progressDetail.textContent = pct + "%";
  if (text) statusText.textContent = text;
}
function setError(msg) {
  errorMsg.textContent = msg;
  errorMsg.style.display = "block";
  statusBadge.textContent = "failed";
  statusBadge.className = "badge failed";
  statusText.textContent = "Analysis failed";
}
function esc(s) {
  return String(s == null ? "" : s).replace(/[&<>"']/g, (c) => (
    { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

// ---------- Drag & drop ----------
dropZone.addEventListener("click", () => fileInput.click());
["dragenter", "dragover"].forEach(ev => dropZone.addEventListener(ev, (e) => {
  e.preventDefault(); dropZone.classList.add("dragover");
}));
["dragleave", "drop"].forEach(ev => dropZone.addEventListener(ev, (e) => {
  e.preventDefault(); dropZone.classList.remove("dragover");
}));
dropZone.addEventListener("drop", (e) => {
  if (e.dataTransfer.files.length) handleFile(e.dataTransfer.files[0]);
});
fileInput.addEventListener("change", (e) => {
  if (e.target.files.length) handleFile(e.target.files[0]);
});

function handleFile(file) {
  const valid = /\.(mp4|mov|avi|mkv|webm)$/i.test(file.name);
  if (!valid) { alert("Please select a video file (mp4, mov, avi, mkv, webm)."); return; }
  if (file.size > 100 * 1024 * 1024) { alert("File too large (max 100 MB)."); return; }
  selectedFile = file;
  formActions.style.display = "";
  dropZone.querySelector(".dz-title").textContent = file.name;
  dropZone.querySelector(".dz-hint").textContent = "Click to change file";
  origVideo.src = URL.createObjectURL(file);
  show(previewCard);
}

// ---------- Analyze ----------
btnAnalyze.addEventListener("click", async () => {
  if (!selectedFile) return;
  resetUI();
  const fd = new FormData();
  fd.append("file", selectedFile);
  try {
    const res = await fetch(`${API}/upload`, { method: "POST", body: fd });
    if (!res.ok) {
      const err = await res.text().catch(() => res.statusText);
      throw new Error(err || `Upload failed (${res.status})`);
    }
    const data = await res.json();
    jobId = data.job_id;
    pollStatus();
  } catch (e) {
    setError(e.message);
  }
});

function resetUI() {
  hide(errorMsg); hide(resultsCard);
  show(progressCard);
  setProgress(0, "Queued…");
  statusBadge.textContent = "processing";
  statusBadge.className = "badge processing";
  repsTbody.innerHTML = "";
  uncertaintyList.innerHTML = "";
}

// ---------- Poll ----------
async function pollStatus() {
  while (jobId) {
    try {
      const res = await fetch(`${API}/status/${jobId}`);
      if (!res.ok) throw new Error("Status request failed");
      const job = await res.json();

      setProgress(job.progress || 0, statusTextFor(job.status));
      statusBadge.textContent = job.status;
      statusBadge.className = "badge " + job.status;

      if (job.status === "completed") {
        showResults(job);
        jobId = null;
        return;
      }
      if (job.status === "failed") {
        setError(job.error || "Unknown error");
        jobId = null;
        return;
      }
    } catch (e) { console.error("poll error", e); }
    await new Promise((r) => setTimeout(r, 1500));
  }
}

function statusTextFor(s) {
  if (s === "queued") return "Waiting to start…";
  if (s === "processing") return "Tracking pose, detecting reps, evaluating against the skill…";
  if (s === "completed") return "Complete";
  if (s === "failed") return "Failed";
  return s;
}

// ---------- Results ----------
function showResults(job) {
  hide(progressCard);
  show(resultsCard);

  statReps.textContent = job.reps ? job.reps.length : "-";
  statDuration.textContent = job.duration_s != null ? Number(job.duration_s).toFixed(1) : "-";

  const overall = (job.reps && job.reps.length)
    ? worstStatus(job.reps.map((r) => r.overall))
    : "cannot assess";
  statOverall.textContent = overall;
  statOverall.className = "stat-badge " + classForStatus(overall);

  // Viewpoint
  const vp = job.viewpoint || {};
  statView.textContent = vp.view === "side_view" ? "side view"
    : vp.view === "not_side_view" ? "not side view" : "unknown";
  statView.className = "stat-badge " + (vp.view === "side_view" ? "side-view"
    : vp.view === "not_side_view" ? "not-side-view" : "cannot-assess");
  if (vp.view && vp.view !== "side_view" && vp.note) {
    viewNote.innerHTML = `<strong>Viewpoint check:</strong> ${esc(vp.reason || "")}. ${esc(vp.note)}`;
    viewNote.style.display = "";
  } else {
    viewNote.style.display = "none";
  }

  // Skill provenance
  const sk = job.skill || {};
  skillInfo.textContent = sk.title
    ? `${sk.title} (${sk.skill_id} v${sk.version}) — ${sk.rules_evaluated} rules, loaded from ` +
      `app/skill/low_bar_squat_skill.json. Reference pages ${sk.source ? sk.source.citation_scheme : ""}`
    : "-";

  dlVideo.style.display = "inline-flex";
  dlReport.style.display = "inline-flex";
  dlVideo.href = `${API}/download/${jobId}/video`;
  dlReport.href = `${API}/download/${jobId}/report`;
  annVideo.src = `${API}/download/${jobId}/video?t=${Date.now()}`;
  annVideo.load();

  const notes = [
    "Barbell position is tracked with a wrist proxy and is approximate; segments where the bar was hidden are drawn dashed in the annotated video.",
    "Depth is reported in pixels; absolute centimetres require a calibration reference.",
    "Stance width, toe angle and medial-lateral knee position cannot be assessed from a side view.",
    "The camera is tilted in many recordings; the floor reference is estimated from the heel-to-toe line and reported per rep.",
    "Landmarks hidden behind a large object (for example a weight plate) are model estimates, not observations; any rule that depends on them is reported as cannot assess.",
  ];
  uncertaintyList.innerHTML = notes.map((n) => `<li>${esc(n)}</li>`).join("");

  if (job.reps && job.reps.length) {
    repsTbody.innerHTML = job.reps.map(repRow).join("");
  } else {
    repsTbody.innerHTML = `<tr><td colspan="5" style="text-align:center;color:#6b7280">No repetitions detected.</td></tr>`;
  }
}

function repRow(r) {
  const findings = r.findings.map((f) => {
    const pages = f.source_pages && f.source_pages.length ? `p${f.source_pages.join(", p")}` : "";
    const meas = f.measurement && Object.keys(f.measurement).length
      ? `<div class="f-meas">measured: ${Object.entries(f.measurement)
          .map(([k, v]) => `${k}=${typeof v === "number" ? Number(v.toFixed(2)) : v}`).join(", ")}</div>`
      : "";
    const quote = f.source_quote ? `<div class="f-quote">“${esc(f.source_quote)}” <span class="f-src">(${esc(pages)})</span></div>` : "";
    const unc = f.uncertainty ? `<div class="f-unc">! ${esc(f.uncertainty)}</div>` : "";
    return `
      <div class="finding">
        <div class="f-head">
          <span class="status-pill ${classForStatus(f.status)}">${esc(f.status)}</span>
          <span class="f-rule">${esc(f.rule_id)} — ${esc(f.rule)}</span>
          <span class="f-src">${esc(pages)}</span>
        </div>
        <div class="f-body">${esc(f.feedback)}</div>
        ${meas}${quote}${unc}
      </div>`;
  }).join("");

  const ts = r.bottom_timestamp_s != null ? Number(r.bottom_timestamp_s).toFixed(2) : "-";
  const mm = r.measurements || {};

  // Only show a measurement next to a rule that was actually assessed,
  // otherwise the summary line contradicts the verdict below it.
  const assessed = {};
  r.findings.forEach((f) => {
    assessed[f.rule_id] = f.status;
  });
  const keyM = [];
  // Rule ids in the skill are hyphenated (e.g. "DEPTH-01"), so they must be
  // looked up as strings. Dot notation with underscores never matched, which
  // silently emptied this summary line.
  const isAssessed = (id) => {
    const s = assessed[id];
    return s === "meets standard" || s === "does not meet standard";
  };
  if (isAssessed("DEPTH-01") && mm.depth_px != null) {
    keyM.push(`depth ${Number(mm.depth_px).toFixed(0)}px`);
  }
  if (isAssessed("ANGLE-01") && mm.back_angle_deg != null) {
    keyM.push(`back angle ${Number(mm.back_angle_deg).toFixed(0)}°`);
  }
  if (isAssessed("BAR-01") && mm.bar_drift_from_midfoot_px != null) {
    keyM.push(`bar drift ${Number(mm.bar_drift_from_midfoot_px).toFixed(0)}px`);
  }
  if (isAssessed("HIP-01") && mm.hip_drive_ratio != null) {
    keyM.push(`hip drive ${Number(mm.hip_drive_ratio).toFixed(2)}`);
  }
  const nAssessed = r.findings.filter((f) => f.status === "meets standard" || f.status === "does not meet standard").length;
  keyM.push(`${nAssessed}/${r.findings.length} criteria assessed`);

  return `
    <tr>
      <td><strong>Rep ${r.rep_id}</strong></td>
      <td>${r.bottom_frame}</td>
      <td>${ts}s</td>
      <td><span class="status-pill ${classForStatus(r.overall)}">${esc(r.overall)}</span></td>
      <td class="f-cell">
        <div class="f-key">${esc(keyM.join(" · "))}</div>
        ${findings}
      </td>
    </tr>`;
}

function worstStatus(statuses) {
  const order = ["does not meet standard", "cannot assess", "meets standard", "observed"];
  return statuses.slice().sort((a, b) => order.indexOf(a) - order.indexOf(b))[0] || "cannot assess";
}
function classForStatus(s) {
  if (s === "meets standard") return "pill-meets";
  if (s === "does not meet standard") return "pill-fail";
  if (s === "observed") return "pill-observed";
  return "pill-cannot";
}

// ---------- Playback diagnostics ----------
// If the browser cannot decode the annotated video, say so instead of
// showing an empty black player.
function wireVideoDiagnostics() {
  const v = $("annVideo");
  if (!v) return;
  v.addEventListener("error", () => {
    const note = $("videoNote");
    note.style.display = "";
    note.textContent =
      "The browser could not play the annotated video inline. The file is still available to " +
      "download above (it is H.264/MP4). If it does not play after downloading either, try a " +
      "different browser.";
  });
  v.addEventListener("loadeddata", () => { $("videoNote").style.display = "none"; });
}
