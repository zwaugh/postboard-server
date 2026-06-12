#!/usr/bin/env python3
"""
Postboard Notice Server  —  with web UI at http://localhost:5000

pip install flask
python server.py
"""

from flask import Flask, request, jsonify
import time
import collections

app = Flask(__name__)

_notice = None   # dict of content fields + internal _ metadata
_logs   = collections.deque(maxlen=100)  # ring buffer of TX log lines


# ─── API ──────────────────────────────────────────────────────────────────────

@app.get("/poll")
def poll():
    if _notice and not _notice["confirmed"]:
        return jsonify({"pending": True, "notice_id": _notice["id"]})
    return jsonify({"pending": False})


@app.get("/notice")
def get_notice():
    if not _notice:
        return jsonify({"error": "no active notice"}), 404
    payload = {k: v for k, v in _notice.items() if not k.startswith("_") and k != "confirmed"}
    return jsonify(payload)


@app.post("/submit")
def submit():
    global _notice
    body = request.get_json(silent=True)
    if not body:
        return jsonify({"error": "expected JSON body"}), 400
    required = {"title", "sub", "date", "time", "body", "em", "f1"}
    missing = required - body.keys()
    if missing:
        return jsonify({"error": f"missing fields: {sorted(missing)}"}), 400

    notice_id = f"n{int(time.time())}"
    _notice = {
        "id":            notice_id,
        **{k: v for k, v in body.items()},
        "confirmed":     False,
        "_submitted_at": time.time(),
        "_delivered_at": None,
    }
    print(f"[server] Notice queued: {notice_id}")
    return jsonify({"ok": True, "notice_id": notice_id})


@app.post("/confirm")
def confirm():
    global _notice
    body      = request.get_json(silent=True) or {}
    notice_id = body.get("notice_id")
    success   = body.get("success", True)

    if not _notice or notice_id != _notice["id"]:
        return jsonify({"error": "notice_id mismatch or no active notice"}), 400

    _notice["confirmed"]     = success
    _notice["_delivered_at"] = time.time()
    elapsed = _notice["_delivered_at"] - _notice["_submitted_at"]
    print(f"[server] Notice {notice_id} {'confirmed' if success else 'failed'}. Elapsed: {elapsed:.1f}s")
    return jsonify({"ok": True})


@app.post("/clear")
def clear():
    global _notice
    _notice = None
    print("[server] State cleared")
    return jsonify({"ok": True})


@app.post("/log")
def log_line():
    body = request.get_json(silent=True) or {}
    msg  = str(body.get("msg", ""))[:300]
    if msg:
        _logs.appendleft({"t": round(time.time(), 1), "msg": msg})
    return jsonify({"ok": True})


@app.get("/logs")
def get_logs():
    return jsonify(list(_logs))


@app.get("/status")
def status():
    if not _notice:
        return jsonify({"active": False})
    sub   = _notice["_submitted_at"]
    deliv = _notice["_delivered_at"]
    return jsonify({
        "active":       True,
        "notice_id":    _notice["id"],
        "confirmed":    _notice["confirmed"],
        "submitted_at": sub,
        "delivered_at": deliv,
        "elapsed_s":    round(deliv - sub, 1) if deliv else None,
    })


# ─── Web UI ───────────────────────────────────────────────────────────────────

@app.get("/")
def index():
    return UI_HTML, 200, {"Content-Type": "text/html"}


@app.get("/board")
def board():
    return BOARD_HTML, 200, {"Content-Type": "text/html"}


UI_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Postboard Server</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #f5f5f7;
    color: #1d1d1f;
    min-height: 100vh;
    padding: 32px 16px;
  }

  h1 {
    font-size: 22px;
    font-weight: 700;
    letter-spacing: -0.3px;
    margin-bottom: 24px;
  }

  .layout {
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 20px;
    max-width: 960px;
    margin: 0 auto;
  }
  @media (max-width: 680px) { .layout { grid-template-columns: 1fr; } }

  .card {
    background: #fff;
    border-radius: 14px;
    padding: 22px 24px;
    box-shadow: 0 1px 4px rgba(0,0,0,.08);
  }

  .card h2 {
    font-size: 13px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: .6px;
    color: #6e6e73;
    margin-bottom: 16px;
  }

  /* Status */
  .badge {
    display: inline-block;
    padding: 3px 10px;
    border-radius: 20px;
    font-size: 13px;
    font-weight: 600;
    margin-bottom: 14px;
  }
  .badge.idle      { background: #e5e5ea; color: #6e6e73; }
  .badge.pending   { background: #fff3cd; color: #856404; }
  .badge.confirmed { background: #d1f5d3; color: #1a7f37; }
  .badge.failed    { background: #fde8e8; color: #c0392b; }

  .stat-row {
    display: flex;
    justify-content: space-between;
    font-size: 13px;
    padding: 5px 0;
    border-bottom: 1px solid #f0f0f0;
  }
  .stat-row:last-child { border-bottom: none; }
  .stat-row .label { color: #6e6e73; }
  .stat-row .value { font-weight: 500; font-variant-numeric: tabular-nums; }

  /* Form */
  .field { margin-bottom: 14px; }
  .field label {
    display: block;
    font-size: 12px;
    font-weight: 600;
    color: #6e6e73;
    text-transform: uppercase;
    letter-spacing: .5px;
    margin-bottom: 5px;
  }
  .field label .opt {
    font-weight: 400;
    text-transform: none;
    letter-spacing: 0;
    color: #aaa;
    font-size: 11px;
  }
  .field input,
  .field textarea {
    width: 100%;
    padding: 9px 12px;
    border: 1.5px solid #d2d2d7;
    border-radius: 8px;
    font-size: 14px;
    font-family: inherit;
    transition: border-color .15s;
    outline: none;
    background: #fff;
    resize: vertical;
  }
  .field input:focus,
  .field textarea:focus { border-color: #0071e3; }

  .btn-row { display: flex; gap: 10px; margin-top: 6px; }

  button {
    flex: 1;
    padding: 11px 0;
    border: none;
    border-radius: 10px;
    font-size: 14px;
    font-weight: 600;
    cursor: pointer;
    transition: opacity .15s;
  }
  button:active { opacity: .75; }
  .btn-submit { background: #0071e3; color: #fff; }
  .btn-clear  { background: #e5e5ea; color: #1d1d1f; }

  #msg {
    margin-top: 12px;
    font-size: 13px;
    min-height: 20px;
    color: #6e6e73;
  }
  #msg.ok  { color: #1a7f37; }
  #msg.err { color: #c0392b; }

  .log-panel {
    background: #1d1d1f;
    border-radius: 10px;
    padding: 14px 16px;
    max-height: 280px;
    overflow-y: auto;
    font-family: "SF Mono", "Fira Code", monospace;
    font-size: 12px;
    line-height: 1.6;
    color: #f5f5f7;
  }
  .log-panel .log-empty { color: #48484a; }
  .log-panel .log-ts    { color: #48484a; margin-right: 10px; user-select: none; }
</style>
</head>
<body>

<div style="max-width:960px;margin:0 auto;">
  <h1>📋 Postboard Server</h1>
</div>

<div class="layout">

  <!-- ── Status card ─────────────────────────────────────────────────── -->
  <div class="card">
    <h2>Status</h2>
    <div id="badge" class="badge idle">Idle</div>
    <div id="stats"></div>
  </div>

  <!-- ── Notice form ─────────────────────────────────────────────────── -->
  <div class="card">
    <h2>Queue a Notice</h2>
    <div class="field">
      <label>Template <span class="opt">optional</span></label>
      <select id="templatePicker" onchange="applyTemplate(this.value)" style="width:100%;padding:9px 12px;border:1.5px solid #d2d2d7;border-radius:8px;font-size:14px;font-family:inherit;background:#fff;outline:none;">
        <option value="">— Select a template —</option>
        <option value="fire_alarm">Fire Alarm Testing</option>
        <option value="elevator">Elevator Out of Service</option>
        <option value="maintenance">Building Maintenance</option>
        <option value="water">Water Shutoff</option>
        <option value="package">Package Delivery Available</option>
      </select>
    </div>
    <form id="noticeForm">

      <div class="field">
        <label>Title</label>
        <input name="title" value="NOTICE" required>
      </div>

      <div class="field">
        <label>Subtitle</label>
        <input name="sub" value="FIRE ALARM SYSTEM TESTING" required>
      </div>

      <div class="field">
        <label>Date</label>
        <input name="date" value="Thursday, June 11, 2026" required>
      </div>

      <div class="field">
        <label>Time</label>
        <input name="time" value="9:00 AM  -  12:00 PM" required>
      </div>

      <div class="field">
        <label>Body <span class="opt">RX wraps to fit</span></label>
        <textarea name="body" rows="3" required>Fire alarm systems in this building will undergo scheduled maintenance and testing. The alarm may sound intermittently throughout this period.</textarea>
      </div>

      <div class="field">
        <label>Emphasis line</label>
        <input name="em" value="NO EVACUATION IS REQUIRED." required>
      </div>

      <div class="field">
        <label>Footer line 1</label>
        <input name="f1" value="Questions? Contact Building Management" required>
      </div>

      <div class="field">
        <label>Footer line 2 <span class="opt">optional</span></label>
        <input name="f2" value="Tel: (555) 123-4567   |   mgmt@example.com">
      </div>

      <div class="btn-row">
        <button type="submit" class="btn-submit">Send Notice</button>
        <button type="button" class="btn-clear" onclick="clearNotice()">Clear</button>
      </div>
      <div id="msg"></div>
    </form>
  </div>

</div>

<div style="max-width:960px;margin:20px auto 0;">
  <div class="card">
    <h2>TX Log</h2>
    <div id="logPanel" class="log-panel">
      <span class="log-empty">No messages yet — TX will post here when active.</span>
    </div>
  </div>
</div>

<script>
  // ── Templates ─────────────────────────────────────────────────────────────
  const TEMPLATES = {
    fire_alarm: {
      title: "NOTICE",
      sub:   "FIRE ALARM SYSTEM TESTING",
      date:  "Thursday, June 11, 2026",
      time:  "9:00 AM  -  12:00 PM",
      body:  "Fire alarm systems in this building will undergo scheduled maintenance and testing. The alarm may sound intermittently throughout this period.",
      em:    "NO EVACUATION IS REQUIRED.",
      f1:    "Questions? Contact Building Management",
      f2:    "Tel: (555) 123-4567   |   mgmt@example.com",
    },
    elevator: {
      title: "NOTICE",
      sub:   "ELEVATOR OUT OF SERVICE",
      date:  "Thursday, June 11, 2026",
      time:  "8:00 AM  -  5:00 PM",
      body:  "The main elevator will be temporarily out of service for scheduled maintenance. Please use the stairwell located near the east entrance.",
      em:    "WE APOLOGIZE FOR THE INCONVENIENCE.",
      f1:    "Questions? Contact Building Management",
      f2:    "Tel: (555) 123-4567   |   mgmt@example.com",
    },
    maintenance: {
      title: "NOTICE",
      sub:   "SCHEDULED BUILDING MAINTENANCE",
      date:  "Thursday, June 11, 2026",
      time:  "7:00 AM  -  3:00 PM",
      body:  "Routine building maintenance will be conducted. Contractors may be present in common areas and hallways. We appreciate your patience.",
      em:    "THANK YOU FOR YOUR COOPERATION.",
      f1:    "Questions? Contact Building Management",
      f2:    "Tel: (555) 123-4567   |   mgmt@example.com",
    },
    water: {
      title: "NOTICE",
      sub:   "TEMPORARY WATER SHUTOFF",
      date:  "Thursday, June 11, 2026",
      time:  "10:00 AM  -  2:00 PM",
      body:  "Water service to the building will be temporarily shut off to allow for emergency plumbing repairs. Please plan accordingly.",
      em:    "WE EXPECT SERVICE TO RESUME BY 2:00 PM.",
      f1:    "Questions? Contact Building Management",
      f2:    "Tel: (555) 123-4567   |   mgmt@example.com",
    },
    package: {
      title: "NOTICE",
      sub:   "PACKAGE DELIVERY AVAILABLE",
      date:  "Thursday, June 11, 2026",
      time:  "9:00 AM  -  6:00 PM",
      body:  "Packages are available for pick-up at the front desk. Please bring photo ID. Unclaimed packages will be held for 5 business days.",
      em:    "FRONT DESK HOURS: 9:00 AM - 6:00 PM",
      f1:    "Questions? Contact Building Management",
      f2:    "Tel: (555) 123-4567   |   mgmt@example.com",
    },
  };

  function applyTemplate(key) {
    if (!key) return;
    const t = TEMPLATES[key];
    const form = document.getElementById("noticeForm");
    for (const [field, value] of Object.entries(t)) {
      const el = form.elements[field];
      if (el) el.value = value;
    }
    document.getElementById("templatePicker").value = "";
  }

  // ── Status polling ────────────────────────────────────────────────────────
  function fmt(ts) {
    if (!ts) return "—";
    return new Date(ts * 1000).toLocaleTimeString();
  }

  async function refreshStatus() {
    const r = await fetch("/status");
    const s = await r.json();
    const badge = document.getElementById("badge");
    const stats = document.getElementById("stats");

    if (!s.active) {
      badge.className = "badge idle";
      badge.textContent = "Idle";
      stats.innerHTML = '<div class="stat-row"><span class="label">No active notice</span></div>';
      return;
    }

    if (s.confirmed) {
      badge.className = "badge confirmed";
      badge.textContent = "Confirmed ✓";
    } else {
      badge.className = "badge pending";
      badge.textContent = "Pending — waiting for TX";
    }

    stats.innerHTML = `
      <div class="stat-row"><span class="label">Notice ID</span><span class="value">${s.notice_id}</span></div>
      <div class="stat-row"><span class="label">Submitted</span><span class="value">${fmt(s.submitted_at)}</span></div>
      <div class="stat-row"><span class="label">Delivered</span><span class="value">${fmt(s.delivered_at)}</span></div>
      <div class="stat-row"><span class="label">Round-trip</span><span class="value">${s.elapsed_s != null ? s.elapsed_s + " s" : "—"}</span></div>
    `;
  }

  refreshStatus();
  setInterval(refreshStatus, 3000);

  // ── TX Log ────────────────────────────────────────────────────────────────
  async function refreshLogs() {
    const r = await fetch("/logs");
    const logs = await r.json();
    const panel = document.getElementById("logPanel");
    if (!logs.length) {
      panel.innerHTML = '<span class="log-empty">No messages yet — TX will post here when active.</span>';
      return;
    }
    panel.innerHTML = logs.map(e => {
      const t = new Date(e.t * 1000).toLocaleTimeString();
      return `<div><span class="log-ts">${t}</span>${e.msg}</div>`;
    }).join('');
  }

  refreshLogs();
  setInterval(refreshLogs, 2000);

  // ── Form submit ───────────────────────────────────────────────────────────
  document.getElementById("noticeForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const msg = document.getElementById("msg");
    msg.className = "";
    msg.textContent = "Sending…";

    const fd = new FormData(e.target);
    const body = {};
    for (const [k, v] of fd.entries()) {
      if (v.trim()) body[k] = v.trim();
    }

    try {
      const r = await fetch("/submit", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await r.json();
      if (r.ok) {
        msg.className = "ok";
        msg.textContent = `Queued: ${data.notice_id} — TX will pick it up within 30 s.`;
        refreshStatus();
      } else {
        msg.className = "err";
        msg.textContent = "Error: " + (data.error || r.status);
      }
    } catch (err) {
      msg.className = "err";
      msg.textContent = "Request failed: " + err.message;
    }
  });

  // ── Clear ─────────────────────────────────────────────────────────────────
  async function clearNotice() {
    await fetch("/clear", { method: "POST" });
    document.getElementById("msg").textContent = "";
    refreshStatus();
  }
</script>
</body>
</html>
"""


BOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Postboard</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

  body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    background: #f0ede8;
    min-height: 100vh;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: 32px 16px;
  }

  .board {
    background: #fff;
    border: 4px solid #1d1d1f;
    border-radius: 4px;
    width: 100%;
    max-width: 760px;
    box-shadow: 6px 6px 0 #1d1d1f;
    overflow: hidden;
  }

  .board-header {
    background: #1d1d1f;
    color: #fff;
    text-align: center;
    padding: 28px 24px 24px;
  }
  .board-header h1 {
    font-size: clamp(28px, 5vw, 42px);
    font-weight: 800;
    letter-spacing: 1px;
  }

  .board-body { padding: 0 40px 32px; }

  .board-subtitle {
    text-align: center;
    font-size: clamp(16px, 3vw, 22px);
    font-weight: 700;
    letter-spacing: .4px;
    padding: 22px 0 18px;
  }

  .divider {
    border: none;
    border-top: 2px solid #1d1d1f;
    margin: 0 0 6px;
  }
  .divider + .divider { margin-top: 4px; margin-bottom: 0; }

  .meta {
    padding: 18px 0 6px;
    font-size: 15px;
    color: #1d1d1f;
  }
  .meta-row { margin-bottom: 8px; }
  .meta-row span { font-weight: 600; margin-right: 8px; }

  hr.rule {
    border: none;
    border-top: 1px solid #1d1d1f;
    margin: 12px 0 20px;
  }

  .body-text {
    font-size: 15px;
    line-height: 1.65;
    color: #1d1d1f;
    margin-bottom: 20px;
  }

  .emphasis {
    text-align: center;
    font-size: clamp(16px, 2.5vw, 20px);
    font-weight: 800;
    letter-spacing: .3px;
    margin: 8px 0 24px;
  }

  .footer {
    border-top: 1px solid #1d1d1f;
    padding-top: 14px;
    font-size: 13px;
    color: #3a3a3a;
  }
  .footer p { margin-bottom: 4px; }

  /* Empty state */
  .empty {
    text-align: center;
    padding: 60px 24px;
    color: #6e6e73;
    font-size: 16px;
  }
  .empty h2 { font-size: 22px; font-weight: 700; margin-bottom: 10px; color: #1d1d1f; }

  /* Status dot */
  .status-bar {
    display: flex;
    align-items: center;
    justify-content: flex-end;
    gap: 6px;
    padding: 8px 12px 0;
    font-size: 11px;
    color: #aaa;
  }
  .dot {
    width: 7px; height: 7px;
    border-radius: 50%;
    background: #34c759;
  }
  .dot.stale { background: #ff9500; }
</style>
</head>
<body>

<div style="width:100%;max-width:760px;">
  <div class="status-bar">
    <span class="dot" id="dot"></span>
    <span id="statusTxt">Loading…</span>
  </div>

  <div class="board" id="board">
    <div class="empty"><h2>Postboard</h2><p>No active notice.</p></div>
  </div>
</div>

<script>
  let currentId = null;

  function render(n) {
    if (!n) {
      document.getElementById("board").innerHTML =
        '<div class="empty"><h2>Postboard</h2><p>No active notice.</p></div>';
      return;
    }
    const row = (label, val) => val
      ? `<div class="meta-row"><span>${label}</span>${val}</div>` : "";
    document.getElementById("board").innerHTML = `
      <div class="board-header"><h1>${n.title || "NOTICE"}</h1></div>
      <div class="board-body">
        ${n.sub  ? `<div class="board-subtitle">${n.sub}</div>` : ""}
        <hr class="divider"><hr class="divider">
        <div class="meta">
          ${row("Date", n.date)}
          ${row("Time", n.time)}
        </div>
        <hr class="rule">
        ${n.body ? `<p class="body-text">${n.body}</p>` : ""}
        ${n.em   ? `<p class="emphasis">${n.em}</p>`   : ""}
        <div class="footer">
          ${n.f1 ? `<p>${n.f1}</p>` : ""}
          ${n.f2 ? `<p>${n.f2}</p>` : ""}
        </div>
      </div>`;
  }

  async function refresh() {
    try {
      const s = await (await fetch("/status")).json();
      if (!s.active) {
        if (currentId !== null) { render(null); currentId = null; }
        document.getElementById("statusTxt").textContent = "No active notice";
        document.getElementById("dot").className = "dot stale";
        return;
      }
      if (s.notice_id !== currentId) {
        const n = await (await fetch("/notice")).json();
        render(n);
        currentId = s.notice_id;
      }
      const confirmed = s.confirmed;
      document.getElementById("dot").className = "dot" + (confirmed ? "" : " stale");
      document.getElementById("statusTxt").textContent = confirmed
        ? "Displayed on board · " + new Date(s.delivered_at * 1000).toLocaleTimeString()
        : "Pending delivery…";
    } catch(e) {
      document.getElementById("statusTxt").textContent = "Offline";
    }
  }

  refresh();
  setInterval(refresh, 5000);
</script>
</body>
</html>
"""


if __name__ == "__main__":
    print("[server] Postboard Notice Server — http://0.0.0.0:8080")
    app.run(host="0.0.0.0", port=8080, debug=True)
