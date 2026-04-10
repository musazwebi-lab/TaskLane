"""TaskLane Web Dashboard — General-purpose monitoring panel.

Usage: tasklane dashboard --port 5000
"""

from __future__ import annotations

import json

from flask import Flask, jsonify, request

from .core import RedisEngine
from . import config as C

_engine: RedisEngine | None = None


def create_app(redis_url: str = "", namespace: str = "") -> Flask:
    global _engine
    _engine = RedisEngine(redis_url, namespace)
    app = Flask(__name__)

    # ── API ──

    @app.route("/api/overview")
    def api_overview():
        stats = _engine.get_stats()
        workers = _engine.get_workers()
        return jsonify({
            "queue_pending": _engine.queue_len(),
            "workers_total": len(workers),
            "workers_alive": sum(1 for w in workers if w.get("alive")),
            "success": stats.get("success", 0),
            "failed": stats.get("failed", 0),
            "retried": stats.get("retried", 0),
        })

    @app.route("/api/workers")
    def api_workers():
        workers = _engine.get_workers()
        for w in workers:
            delay = _engine.get_delay_config(w["name"])
            w["delay"] = delay
            w["has_own_delay"] = _engine.has_delay_config(w["name"])
        return jsonify(workers)

    @app.route("/api/events")
    def api_events():
        limit = int(request.args.get("limit", 50))
        return jsonify(_engine.get_events(limit))

    @app.route("/api/events/clear", methods=["POST"])
    def api_clear_events():
        _engine.clear_events()
        return jsonify({"ok": True})

    @app.route("/api/handlers")
    def api_handlers():
        return jsonify(_engine.list_handlers())

    @app.route("/api/handler/<name>", methods=["GET"])
    def api_get_handler(name):
        data = _engine.load_handler(name)
        if not data:
            return jsonify({"error": "not found"}), 404
        return jsonify(data)

    @app.route("/api/handler/<name>", methods=["POST"])
    def api_set_handler(name):
        data = request.json or {}
        source = data.get("source", "")
        deps = data.get("deps", [])
        if not source:
            return jsonify({"error": "source required"}), 400
        ver = _engine.save_handler(name, source, deps)
        return jsonify({"ok": True, "name": name, "version": ver})

    @app.route("/api/handler/<name>", methods=["DELETE"])
    def api_del_handler(name):
        _engine.remove_handler(name)
        return jsonify({"ok": True})

    @app.route("/api/delay", methods=["GET"])
    def api_get_delay():
        return jsonify(_engine.get_delay_config())

    @app.route("/api/delay", methods=["POST"])
    def api_set_delay():
        data = request.json or {}
        _engine.set_delay_config(**data)
        return jsonify(_engine.get_delay_config())

    @app.route("/api/delay/<worker>", methods=["GET"])
    def api_get_worker_delay(worker):
        return jsonify(_engine.get_delay_config(worker))

    @app.route("/api/delay/<worker>", methods=["POST"])
    def api_set_worker_delay(worker):
        data = request.json or {}
        _engine.set_delay_config(worker=worker, **data)
        return jsonify({"ok": True})

    @app.route("/api/delay/<worker>", methods=["DELETE"])
    def api_del_worker_delay(worker):
        _engine.del_delay_config(worker)
        return jsonify({"ok": True})

    @app.route("/api/queue/purge", methods=["POST"])
    def api_queue_purge():
        n = _engine.queue_purge()
        return jsonify({"ok": True, "removed": n})

    @app.route("/api/worker/<name>/pause", methods=["POST"])
    def api_worker_pause(name):
        _engine.set_control(name, "pause")
        return jsonify({"ok": True, "action": "pause"})

    @app.route("/api/worker/<name>/resume", methods=["POST"])
    def api_worker_resume(name):
        _engine.clear_control(name)
        return jsonify({"ok": True, "action": "resume"})

    @app.route("/api/worker/<name>/stop", methods=["POST"])
    def api_worker_stop(name):
        _engine.set_control(name, "stop")
        return jsonify({"ok": True, "action": "stop"})

    @app.route("/api/submit", methods=["POST"])
    def api_submit():
        from .core import TaskMessage
        data = request.json or {}
        handler = data.get("handler", "")
        params = data.get("params", {})
        if not handler:
            return jsonify({"error": "handler required"}), 400
        msg = TaskMessage(handler=handler, params=params,
                          max_retries=int(data.get("max_retries", C.RETRY_MAX)),
                          retry_delay=float(data.get("retry_delay", C.RETRY_DELAY)))
        _engine.enqueue(msg)
        return jsonify({"ok": True, "task_id": msg.task_id})

    @app.route("/api/task_config", methods=["GET"])
    def api_get_task_config():
        return jsonify(_engine.get_task_config())

    @app.route("/api/task_config", methods=["POST"])
    def api_set_task_config():
        data = request.json or {}
        _engine.set_task_config(**data)
        return jsonify(_engine.get_task_config())

    @app.route("/api/stats")
    def api_stats():
        return jsonify(_engine.get_stats())

    @app.route("/api/stats/clear", methods=["POST"])
    def api_clear_stats():
        _engine.clear_stats()
        return jsonify({"ok": True})

    @app.route("/api/results")
    def api_results():
        limit = int(request.args.get("limit", 50))
        return jsonify(_engine.list_results(limit))

    @app.route("/api/result/<task_id>")
    def api_result(task_id):
        r = _engine.get_result(task_id)
        if r is None:
            return jsonify({"error": "not found"}), 404
        return jsonify({"task_id": task_id, "result": r})

    # ── Frontend Page ──

    @app.route("/")
    def index():
        return INDEX_HTML

    return app


# ── Embedded Frontend ──────────────────────────────────────────────────

INDEX_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>TaskLane Dashboard</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { font-family: -apple-system, 'Segoe UI', sans-serif; background: #f0f2f5; color: #333; }
.container { max-width: 1200px; margin: 0 auto; padding: 20px; }
h1 { font-size: 24px; margin-bottom: 20px; }
h2 { font-size: 18px; margin-bottom: 12px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 16px; margin-bottom: 24px; }
.card { background: #fff; border-radius: 8px; padding: 20px; box-shadow: 0 1px 3px rgba(0,0,0,.1); }
.card .label { font-size: 13px; color: #888; margin-bottom: 4px; }
.card .value { font-size: 28px; font-weight: 600; }
.ok { color: #52c41a; } .err { color: #f5222d; } .pending { color: #1890ff; }
table { width: 100%; border-collapse: collapse; background: #fff; border-radius: 8px;
  overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,.1); margin-bottom: 24px; }
th, td { padding: 10px 14px; text-align: left; border-bottom: 1px solid #f0f0f0; font-size: 14px; }
th { background: #fafafa; font-weight: 600; }
.status { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 12px; }
.status-ok { background: #f6ffed; color: #52c41a; }
.status-running { background: #e6f7ff; color: #1890ff; }
.status-idle { background: #f5f5f5; color: #999; }
.status-paused { background: #fffbe6; color: #faad14; }
.status-error { background: #fff1f0; color: #f5222d; }
.status-retrying { background: #fff7e6; color: #fa8c16; }
.status-stopped { background: #f5f5f5; color: #666; }
.section { margin-bottom: 24px; }
.actions { display: flex; gap: 8px; margin-bottom: 24px; flex-wrap: wrap; }
.btn { padding: 6px 16px; border: none; border-radius: 4px; cursor: pointer; font-size: 13px; }
.btn-primary { background: #1890ff; color: #fff; }
.btn-danger { background: #f5222d; color: #fff; }
.btn-default { background: #fff; border: 1px solid #d9d9d9; }
.btn:hover { opacity: .85; }
.events { max-height: 300px; overflow-y: auto; }
.delay-form { display: flex; gap: 12px; flex-wrap: wrap; align-items: end; }
.delay-form .field { display: flex; flex-direction: column; }
.delay-form label { font-size: 12px; color: #888; margin-bottom: 4px; }
.delay-form input { width: 100px; padding: 6px 8px; border: 1px solid #d9d9d9; border-radius: 4px; }
textarea { width: 100%; min-height: 120px; padding: 8px; border: 1px solid #d9d9d9;
  border-radius: 4px; font-family: monospace; font-size: 13px; }
.handler-card { background: #fff; border-radius: 8px; padding: 16px;
  box-shadow: 0 1px 3px rgba(0,0,0,.1); margin-bottom: 12px; }
.handler-card h3 { font-size: 15px; margin-bottom: 8px; }
.handler-meta { font-size: 12px; color: #888; margin-bottom: 8px; }
pre { background: #f5f5f5; padding: 12px; border-radius: 4px; font-size: 13px;
  overflow-x: auto; max-height: 200px; }
</style>
</head>
<body>
<div class="container">
<h1>TaskLane Dashboard</h1>
<div class="cards" id="cards"></div>

<div class="actions">
  <button class="btn btn-primary" onclick="refresh()">Refresh</button>
  <button class="btn btn-danger" onclick="purgeQueue()">Purge Queue</button>
  <button class="btn btn-danger" onclick="clearStats()">Reset Stats</button>
  <button class="btn btn-default" onclick="showSubmit()">Submit Task</button>
</div>

<div class="section"><h2>Workers</h2>
<table><thead><tr>
  <th>Name</th><th>Status</th><th>Heartbeat</th><th>Handler</th><th>Delay</th><th>Last Task</th><th>Time</th><th>Error</th><th>Actions</th>
</tr></thead><tbody id="workers"></tbody></table></div>

<div class="section"><h2>Handlers</h2>
<div id="handlers"></div>
<button class="btn btn-default" style="margin-top:8px" onclick="showUploadHandler()">Upload Handler</button>
</div>

<div class="section"><h2>Delay Config</h2>
<div class="delay-form" id="delay-form">
  <div class="field"><label>min_delay</label><input id="d-min" type="number" step="0.1"></div>
  <div class="field"><label>max_delay</label><input id="d-max" type="number" step="0.1"></div>
  <div class="field"><label>batch_size</label><input id="d-bs" type="number"></div>
  <div class="field"><label>batch_pause</label><input id="d-bp" type="number" step="0.1"></div>
  <button class="btn btn-primary" onclick="saveDelay()">Save</button>
</div></div>

<div class="section events"><h2 style="display:inline">Event Log</h2> <button class="btn btn-danger" style="margin-left:12px;vertical-align:middle" onclick="clearEvents()">Clear</button>
<table><thead><tr><th>Time</th><th>Worker</th><th>Task</th><th>Event</th><th>Detail</th></tr></thead>
<tbody id="events"></tbody></table></div>

</div>
<script>
const F = (u, o) => fetch(u, o).then(r => r.json());

let _samples = []; // [{time, success}]

async function refresh() {
  const [ov, ws, evs, hs, dl] = await Promise.all([
    F('/api/overview'), F('/api/workers'), F('/api/events'),
    F('/api/handlers'), F('/api/delay')
  ]);

  // Track samples for speed calculation (sliding window, last 2 minutes)
  const now = Date.now();
  _samples.push({time: now, success: ov.success});
  const cutoff = now - 120000;
  _samples = _samples.filter(s => s.time >= cutoff);

  let _speed = 0;
  if (_samples.length >= 2) {
    const first = _samples[0];
    const last = _samples[_samples.length - 1];
    const dt = (last.time - first.time) / 60000;
    if (dt > 0) _speed = (last.success - first.success) / dt;
  }

  let eta = '-';
  let speedStr = _speed > 0 ? _speed.toFixed(1) + '/min' : '-';
  if (_speed > 0 && ov.queue_pending > 0) {
    const mins = ov.queue_pending / _speed;
    if (mins < 60) eta = Math.ceil(mins) + 'm';
    else eta = (mins / 60).toFixed(1) + 'h';
  }

  document.getElementById('cards').innerHTML = [
    card('Queue', ov.queue_pending, 'pending', eta !== '-' ? 'ETA: ' + eta : ''),
    card('Workers', ov.workers_alive + '/' + ov.workers_total, '', ''),
    card('Success', ov.success, 'ok', speedStr !== '-' ? speedStr : ''),
    card('Failed', ov.failed, 'err', ''),
    card('Retried', ov.retried, 'pending', ''),
  ].join('');

  document.getElementById('workers').innerHTML = ws.map(w => {
    const d = w.delay;
    const dlabel = w.has_own_delay
      ? `${d.min_delay}-${d.max_delay}s / ${d.batch_size}×${d.batch_pause}s`
      : '<span style="color:#999">global</span>';
    return `<tr>
    <td>${w.name}</td>
    <td><span class="status status-${w.status||'idle'}">${w.status||'idle'}</span></td>
    <td>${w.alive ? '🟢' : '⚫'}</td>
    <td>${w.handler||'-'}</td>
    <td>${dlabel}
      <button class="btn btn-default" style="margin-left:4px;padding:2px 6px;font-size:11px" onclick="setWorkerDelay('${w.name}',${d.min_delay},${d.max_delay},${d.batch_size},${d.batch_pause})">Set</button>${
      w.has_own_delay ? `<button class="btn btn-default" style="margin-left:2px;padding:2px 6px;font-size:11px" onclick="resetWorkerDelay('${w.name}')">Reset</button>` : ''}
    </td>
    <td>${w.last_task||'-'}</td><td>${w.last_time||'-'}</td>
    <td>${w.error||'-'}</td>
    <td>
      <button class="btn btn-default" onclick="ctrlWorker('${w.name}','pause')">Pause</button>
      <button class="btn btn-default" onclick="ctrlWorker('${w.name}','resume')">Resume</button>
    </td></tr>`;
  }).join('');

  document.getElementById('handlers').innerHTML = hs.length ? hs.map(h => `
    <div class="handler-card"><h3>${h.name}</h3>
    <div class="handler-meta">v${h.version} | deps: ${h.deps.join(', ')||'none'} | ${h.updated}</div>
    <button class="btn btn-default" onclick="viewHandler('${h.name}')">View Source</button>
    <button class="btn btn-danger" onclick="delHandler('${h.name}')">Delete</button>
    </div>`).join('') : '<p style="color:#999">No handlers</p>';

  document.getElementById('events').innerHTML = evs.map(e => `<tr class="${
    e.event==='error'?'event-error':e.event==='blocked'?'event-blocked':''}">
    <td>${e.time}</td><td>${e.worker}</td><td>${e.task_id}</td>
    <td><span class="status status-${e.event}">${e.event}</span></td>
    <td>${e.detail||'-'}</td></tr>`).join('');

  document.getElementById('d-min').value = dl.min_delay;
  document.getElementById('d-max').value = dl.max_delay;
  document.getElementById('d-bs').value = dl.batch_size;
  document.getElementById('d-bp').value = dl.batch_pause;
}

function card(label, value, cls, sub) {
  return `<div class="card"><div class="label">${label}</div><div class="value ${cls}">${value}</div>${sub ? `<div style="font-size:12px;color:#999;margin-top:4px">${sub}</div>` : ''}</div>`;
}

async function ctrlWorker(name, action) {
  await F('/api/worker/' + encodeURIComponent(name) + '/' + action, {method:'POST'});
  refresh();
}

async function purgeQueue() {
  if (!confirm('Purge all tasks in queue?')) return;
  const r = await F('/api/queue/purge', {method:'POST'});
  alert('Purged ' + r.removed + ' tasks');
  refresh();
}

async function saveDelay() {
  await F('/api/delay', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({
      min_delay: parseFloat(document.getElementById('d-min').value),
      max_delay: parseFloat(document.getElementById('d-max').value),
      batch_size: parseInt(document.getElementById('d-bs').value),
      batch_pause: parseFloat(document.getElementById('d-bp').value),
    })});
  alert('Saved'); refresh();
}

async function viewHandler(name) {
  const h = await F('/api/handler/' + encodeURIComponent(name));
  alert(h.source);
}

async function delHandler(name) {
  if (!confirm('Delete handler: ' + name + '?')) return;
  await F('/api/handler/' + encodeURIComponent(name), {method:'DELETE'});
  refresh();
}

function showUploadHandler() {
  const name = prompt('Handler name');
  if (!name) return;
  const source = prompt('Paste handler source (must contain def handle(params))');
  if (!source) return;
  const deps = prompt('Dependencies (comma separated, leave empty if none)', '');
  F('/api/handler/' + encodeURIComponent(name), {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({source, deps: deps ? deps.split(',').map(s=>s.trim()) : []})
  }).then(() => { alert('Uploaded'); refresh(); });
}

function showSubmit() {
  const handler = prompt('Handler name');
  if (!handler) return;
  const params = prompt('Params JSON', '{}');
  if (params === null) return;
  F('/api/submit', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({handler, params: JSON.parse(params)})
  }).then(r => { alert('Submitted: ' + r.task_id); refresh(); });
}

async function setWorkerDelay(name, curMin, curMax, curBs, curBp) {
  const min = prompt('min_delay (seconds)', curMin);
  if (min === null) return;
  const max = prompt('max_delay (seconds)', curMax);
  if (max === null) return;
  const bs = prompt('batch_size (0=disabled)', curBs);
  if (bs === null) return;
  const bp = prompt('batch_pause (seconds)', curBp);
  if (bp === null) return;
  await F('/api/delay/' + encodeURIComponent(name), {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({min_delay:parseFloat(min),max_delay:parseFloat(max),
      batch_size:parseInt(bs),batch_pause:parseFloat(bp)})});
  refresh();
}

async function resetWorkerDelay(name) {
  if (!confirm('Reset ' + name + ' to global delay?')) return;
  await F('/api/delay/' + encodeURIComponent(name), {method:'DELETE'});
  refresh();
}

async function clearEvents() {
  if (!confirm('Clear all event logs?')) return;
  await F('/api/events/clear', {method:'POST'});
  refresh();
}

async function clearStats() {
  if (!confirm('Reset all stats (success/failed/retried)?')) return;
  await F('/api/stats/clear', {method:'POST'});
  refresh();
}

refresh();
setInterval(refresh, 5000);
</script>
</body></html>"""

def main():
    import argparse
    parser = argparse.ArgumentParser(description="TaskLane Dashboard")
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--redis", default="")
    parser.add_argument("--ns", default="")
    args = parser.parse_args()
    app = create_app(args.redis, args.ns)
    print(f"TaskLane Dashboard: http://localhost:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)
