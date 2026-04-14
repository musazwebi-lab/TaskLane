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
            w["stats"] = _engine.get_worker_stats(w["name"])
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
body { font-family: -apple-system, 'Segoe UI', Roboto, sans-serif; background: #f5f6fa; color: #2d3436; font-size: 14px; }
.container { max-width: 1280px; margin: 0 auto; padding: 24px; }
header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 24px; }
header h1 { font-size: 22px; font-weight: 700; color: #2d3436; }
.header-actions { display: flex; gap: 8px; }
.cards { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap: 12px; margin-bottom: 24px; }
.card { background: #fff; border-radius: 10px; padding: 16px; box-shadow: 0 1px 4px rgba(0,0,0,.06); }
.card .label { font-size: 11px; color: #999; text-transform: uppercase; letter-spacing: .5px; margin-bottom: 6px; }
.card .value { font-size: 26px; font-weight: 700; }
.card .sub { font-size: 11px; color: #999; margin-top: 4px; }
.ok { color: #00b894; } .err { color: #d63031; } .pending { color: #0984e3; }
.panel { background: #fff; border-radius: 10px; box-shadow: 0 1px 4px rgba(0,0,0,.06); margin-bottom: 20px; overflow: hidden; }
.panel-header { display: flex; align-items: center; justify-content: space-between; padding: 14px 18px; border-bottom: 1px solid #f0f0f0; }
.panel-header h2 { font-size: 15px; font-weight: 600; }
table { width: 100%; border-collapse: collapse; }
th, td { padding: 9px 14px; text-align: left; border-bottom: 1px solid #f5f5f5; font-size: 13px; }
th { font-weight: 600; color: #666; font-size: 11px; text-transform: uppercase; letter-spacing: .3px; }
.badge { display: inline-block; padding: 2px 8px; border-radius: 10px; font-size: 11px; font-weight: 500; }
.badge-ok { background: #e8f8f5; color: #00b894; }
.badge-running { background: #e3f2fd; color: #0984e3; }
.badge-idle { background: #f5f5f5; color: #999; }
.badge-paused { background: #fff9e6; color: #e17055; }
.badge-error { background: #ffeef0; color: #d63031; }
.badge-retrying { background: #fff3e0; color: #e17055; }
.badge-stopped { background: #f0f0f0; color: #666; }
.badge-waiting { background: #f3e5f5; color: #6c5ce7; }
.btn { padding: 5px 12px; border: none; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: 500; transition: opacity .15s; }
.btn:hover { opacity: .8; }
.btn-primary { background: #0984e3; color: #fff; }
.btn-danger { background: #d63031; color: #fff; }
.btn-ghost { background: transparent; border: 1px solid #ddd; color: #666; }
.btn-sm { padding: 3px 8px; font-size: 11px; }
.delay-form { display: flex; gap: 10px; padding: 14px 18px; flex-wrap: wrap; align-items: end; }
.delay-form .field { display: flex; flex-direction: column; }
.delay-form label { font-size: 11px; color: #999; margin-bottom: 3px; }
.delay-form input { width: 90px; padding: 5px 8px; border: 1px solid #e0e0e0; border-radius: 6px; font-size: 13px; }
.events-wrap { max-height: 280px; overflow-y: auto; }
.handler-card { padding: 12px 18px; border-bottom: 1px solid #f5f5f5; }
.handler-card:last-child { border-bottom: none; }
.handler-meta { font-size: 11px; color: #999; margin-bottom: 6px; }
.worker-sub { font-size: 11px; color: #999; }
.grid-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 20px; }
@media (max-width: 768px) { .grid-2 { grid-template-columns: 1fr; } }
</style>
</head>
<body>
<div class="container">
<header>
  <h1>TaskLane</h1>
  <div class="header-actions">
    <button class="btn btn-primary" onclick="refresh()">Refresh</button>
    <button class="btn btn-ghost" onclick="showSubmit()">Submit Task</button>
    <button class="btn btn-danger" onclick="purgeQueue()">Purge</button>
    <button class="btn btn-danger" onclick="clearStats()">Reset</button>
  </div>
</header>

<div class="cards" id="cards"></div>

<div class="panel"><div class="panel-header"><h2>Workers</h2></div>
<table><thead><tr>
  <th>Name</th><th>Status</th><th>Handler</th><th>Completed</th><th>Speed</th><th>Delay</th><th>Last Task</th><th>Error</th><th>Actions</th>
</tr></thead><tbody id="workers"></tbody></table></div>

<div class="grid-2">
<div>
<div class="panel"><div class="panel-header"><h2>Handlers</h2>
  <button class="btn btn-ghost btn-sm" onclick="showUploadHandler()">Upload</button>
</div><div id="handlers"></div></div>

<div class="panel"><div class="panel-header"><h2>Global Delay</h2></div>
<div class="delay-form">
  <div class="field"><label>min</label><input id="d-min" type="number" step="0.1"></div>
  <div class="field"><label>max</label><input id="d-max" type="number" step="0.1"></div>
  <div class="field"><label>batch</label><input id="d-bs" type="number"></div>
  <div class="field"><label>pause</label><input id="d-bp" type="number" step="0.1"></div>
  <button class="btn btn-primary btn-sm" onclick="saveDelay()">Save</button>
</div></div>
</div>

<div class="panel"><div class="panel-header"><h2>Event Log</h2>
  <button class="btn btn-danger btn-sm" onclick="clearEvents()">Clear</button>
</div><div class="events-wrap">
<table><thead><tr><th>Time</th><th>Worker</th><th>Task</th><th>Event</th><th>Detail</th></tr></thead>
<tbody id="events"></tbody></table></div></div>
</div>

</div>
<script>
const F = (u, o) => fetch(u, o).then(r => r.json());
let _samples = [];
let _wSamples = {};

function wSpeed(name, success) {
  if (!_wSamples[name]) _wSamples[name] = [];
  const now = Date.now();
  _wSamples[name].push({time: now, s: success});
  _wSamples[name] = _wSamples[name].filter(x => x.time >= now - 120000);
  const arr = _wSamples[name];
  if (arr.length < 2) return 0;
  const dt = (arr[arr.length-1].time - arr[0].time) / 60000;
  return dt > 0 ? (arr[arr.length-1].s - arr[0].s) / dt : 0;
}

async function refresh() {
  const [ov, ws, evs, hs, dl] = await Promise.all([
    F('/api/overview'), F('/api/workers'), F('/api/events'),
    F('/api/handlers'), F('/api/delay')
  ]);
  const now = Date.now();
  _samples.push({time: now, success: ov.success});
  _samples = _samples.filter(s => s.time >= now - 120000);
  let _speed = 0;
  if (_samples.length >= 2) {
    const f = _samples[0], l = _samples[_samples.length-1];
    const dt = (l.time - f.time) / 60000;
    if (dt > 0) _speed = (l.success - f.success) / dt;
  }
  let eta = '-', speedStr = _speed > 0 ? _speed.toFixed(1) + '/min' : '-';
  if (_speed > 0 && ov.queue_pending > 0) {
    const m = ov.queue_pending / _speed;
    eta = m < 60 ? Math.ceil(m) + 'm' : (m/60).toFixed(1) + 'h';
  }
  document.getElementById('cards').innerHTML = [
    card('Queue', ov.queue_pending, 'pending', eta !== '-' ? 'ETA: '+eta : ''),
    card('Workers', ov.workers_alive+'/'+ov.workers_total, '', ''),
    card('Success', ov.success, 'ok', speedStr !== '-' ? speedStr : ''),
    card('Failed', ov.failed, 'err', ''),
    card('Retried', ov.retried, 'pending', ''),
  ].join('');

  document.getElementById('workers').innerHTML = ws.map(w => {
    const d = w.delay, st = w.stats || {};
    const completed = (st.success||0);
    const spd = wSpeed(w.name, completed);
    const spdStr = spd > 0 ? spd.toFixed(1)+'/min' : '-';
    const badge = w.alive
      ? (w.status==='running' ? 'badge-running' : w.status==='paused' ? 'badge-paused' : w.status==='error' ? 'badge-error' : w.status==='waiting' ? 'badge-waiting' : w.status==='retrying' ? 'badge-retrying' : 'badge-ok')
      : (w.status==='stopped' ? 'badge-stopped' : 'badge-idle');
    const dlabel = w.has_own_delay
      ? d.min_delay+'-'+d.max_delay+'s / '+d.batch_size+'\\u00d7'+d.batch_pause+'s'
      : '<span style="color:#bbb">global</span>';
    return '<tr>'
      +'<td><b>'+w.name+'</b></td>'
      +'<td><span class="badge '+badge+'">'+(w.status||'idle')+'</span></td>'
      +'<td>'+(w.handler||'-')+'</td>'
      +'<td>'+completed+(st.failed?' <span style="color:#d63031;font-size:11px">('+st.failed+' err)</span>':'')+'</td>'
      +'<td>'+spdStr+'</td>'
      +'<td>'+dlabel
      +' <button class="btn btn-ghost btn-sm" onclick="setWorkerDelay(\\x27'+w.name+'\\x27,'+d.min_delay+','+d.max_delay+','+d.batch_size+','+d.batch_pause+')">Set</button>'
      +(w.has_own_delay?'<button class="btn btn-ghost btn-sm" onclick="resetWorkerDelay(\\x27'+w.name+'\\x27)">Reset</button>':'')
      +'</td>'
      +'<td style="max-width:120px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="'+(w.last_task||'')+'">'+(w.last_task||'-')+'</td>'
      +'<td style="color:#d63031">'+(w.error||'-')+'</td>'
      +'<td>'
      +'<button class="btn btn-ghost btn-sm" onclick="ctrlWorker(\\x27'+w.name+'\\x27,\\x27pause\\x27)">Pause</button> '
      +'<button class="btn btn-ghost btn-sm" onclick="ctrlWorker(\\x27'+w.name+'\\x27,\\x27resume\\x27)">Resume</button>'
      +'</td></tr>';
  }).join('');

  document.getElementById('handlers').innerHTML = hs.length ? hs.map(h =>
    '<div class="handler-card"><b>'+h.name+'</b>'
    +'<div class="handler-meta">v'+h.version+' | deps: '+(h.deps.join(', ')||'none')+' | '+h.updated+'</div>'
    +'<button class="btn btn-ghost btn-sm" onclick="viewHandler(\\x27'+h.name+'\\x27)">View</button> '
    +'<button class="btn btn-danger btn-sm" onclick="delHandler(\\x27'+h.name+'\\x27)">Delete</button>'
    +'</div>').join('') : '<p style="padding:14px;color:#999">No handlers</p>';

  document.getElementById('events').innerHTML = evs.map(e => {
    const cls = e.event==='error'?'badge-error':e.event==='retrying'?'badge-retrying':e.event==='ok'?'badge-ok':'badge-idle';
    return '<tr><td>'+e.time+'</td><td>'+e.worker+'</td><td>'+e.task_id+'</td>'
      +'<td><span class="badge '+cls+'">'+e.event+'</span></td>'
      +'<td>'+( e.detail||'-')+'</td></tr>';
  }).join('');

  document.getElementById('d-min').value = dl.min_delay;
  document.getElementById('d-max').value = dl.max_delay;
  document.getElementById('d-bs').value = dl.batch_size;
  document.getElementById('d-bp').value = dl.batch_pause;
}

function card(l, v, cls, sub) {
  return '<div class="card"><div class="label">'+l+'</div><div class="value '+cls+'">'+v+'</div>'+(sub?'<div class="sub">'+sub+'</div>':'')+'</div>';
}

async function ctrlWorker(n, a) {
  await F('/api/worker/'+encodeURIComponent(n)+'/'+a, {method:'POST'});
  refresh();
}
async function purgeQueue() {
  if (!confirm('Purge all tasks in queue?')) return;
  const r = await F('/api/queue/purge', {method:'POST'});
  alert('Purged '+r.removed+' tasks'); refresh();
}
async function saveDelay() {
  await F('/api/delay', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({
      min_delay: parseFloat(document.getElementById('d-min').value),
      max_delay: parseFloat(document.getElementById('d-max').value),
      batch_size: parseInt(document.getElementById('d-bs').value),
      batch_pause: parseFloat(document.getElementById('d-bp').value),
    })}); alert('Saved'); refresh();
}
async function viewHandler(n) {
  const h = await F('/api/handler/'+encodeURIComponent(n));
  alert(h.source);
}
async function delHandler(n) {
  if (!confirm('Delete handler: '+n+'?')) return;
  await F('/api/handler/'+encodeURIComponent(n), {method:'DELETE'}); refresh();
}

function showUploadHandler() {
  const n = prompt('Handler name'); if (!n) return;
  const s = prompt('Paste handler source (must contain def handle(params))'); if (!s) return;
  const d = prompt('Dependencies (comma separated)', '');
  F('/api/handler/'+encodeURIComponent(n), {method:'POST',
    headers:{'Content-Type':'application/json'},
    body: JSON.stringify({source:s, deps:d?d.split(',').map(x=>x.trim()):[]})
  }).then(()=>{ alert('Uploaded'); refresh(); });
}
function showSubmit() {
  const h = prompt('Handler name'); if (!h) return;
  const p = prompt('Params JSON', '{}'); if (p===null) return;
  F('/api/submit', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({handler:h, params:JSON.parse(p)})
  }).then(r=>{ alert('Submitted: '+r.task_id); refresh(); });
}
async function setWorkerDelay(name, cMin, cMax, cBs, cBp) {
  const mi=prompt('min_delay (s)',cMin); if(mi===null)return;
  const ma=prompt('max_delay (s)',cMax); if(ma===null)return;
  const bs=prompt('batch_size (0=off)',cBs); if(bs===null)return;
  const bp=prompt('batch_pause (s)',cBp); if(bp===null)return;
  await F('/api/delay/'+encodeURIComponent(name), {method:'POST',
    headers:{'Content-Type':'application/json'},
    body:JSON.stringify({min_delay:+mi,max_delay:+ma,batch_size:+bs,batch_pause:+bp})});
  refresh();
}
async function resetWorkerDelay(n) {
  if (!confirm('Reset '+n+' to global delay?')) return;
  await F('/api/delay/'+encodeURIComponent(n), {method:'DELETE'}); refresh();
}
async function clearEvents() {
  if (!confirm('Clear all event logs?')) return;
  await F('/api/events/clear', {method:'POST'}); refresh();
}
async function clearStats() {
  if (!confirm('Reset all stats?')) return;
  _wSamples = {};
  await F('/api/stats/clear', {method:'POST'}); refresh();
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
