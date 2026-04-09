"""TaskLane Core Engine — Task messages, Redis queue operations, and state management."""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field, asdict

import redis

from . import config as C


# ── Task Message ──────────────────────────────────────────────────

@dataclass
class TaskMessage:
    handler: str
    params: dict
    task_id: str = field(default_factory=lambda: uuid.uuid4().hex[:12])
    retries: int = 0
    max_retries: int = C.RETRY_MAX
    retry_delay: float = C.RETRY_DELAY
    submitted_at: str = field(default_factory=lambda: time.strftime("%Y-%m-%d %H:%M:%S"))

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_json(cls, raw: str) -> TaskMessage:
        return cls(**json.loads(raw))


# ── Redis Engine ────────────────────────────────────────────────

class RedisEngine:
    """Encapsulates all Redis operations: queue, handler storage, state, events, and stats."""

    def __init__(self, redis_url: str = "", namespace: str = ""):
        self._r = redis.Redis.from_url(
            redis_url or C.REDIS_URL, decode_responses=True
        )
        self._ns = namespace or C.NAMESPACE

    def _k(self, *parts: str) -> str:
        return C.key(*parts, ns=self._ns)

    # ── Queue Operations ──

    def enqueue(self, msg: TaskMessage, queue: str = "default"):
        self._r.lpush(self._k("queue", queue), msg.to_json())

    def dequeue(self, queue: str = "default", timeout: int = C.BRPOP_TIMEOUT
                ) -> TaskMessage | None:
        result = self._r.brpop(self._k("queue", queue), timeout=timeout)
        if result is None:
            return None
        return TaskMessage.from_json(result[1])

    def enqueue_delayed(self, msg: TaskMessage, delay: float):
        due = time.time() + delay
        self._r.zadd(self._k("delayed"), {msg.to_json(): due})

    def promote_delayed(self, queue: str = "default") -> int:
        """Move due delayed tasks back to the main queue. Returns the number moved."""
        key_delayed = self._k("delayed")
        due = self._r.zrangebyscore(key_delayed, 0, time.time())
        if not due:
            return 0
        pipe = self._r.pipeline()
        for raw in due:
            pipe.lpush(self._k("queue", queue), raw)
            pipe.zrem(key_delayed, raw)
        pipe.execute()
        return len(due)

    def queue_len(self, queue: str = "default") -> int:
        return self._r.llen(self._k("queue", queue))

    def queue_purge(self, queue: str = "default") -> int:
        n = self.queue_len(queue)
        self._r.delete(self._k("queue", queue))
        return n

    # ── Handler Storage ──

    def save_handler(self, name: str, source: str,
                     deps: list[str] | None = None,
                     display_fields: list[str] | None = None) -> int:
        """Save handler source code to Redis. Returns the new version number."""
        k = self._k("handler", name)
        version = self._r.hincrby(k, "version", 1)
        self._r.hset(k, mapping={
            "source": source,
            "deps": json.dumps(deps or []),
            "display_fields": json.dumps(display_fields or []),
            "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        return version

    def load_handler(self, name: str) -> dict | None:
        """Load handler info: {source, deps, display_fields, version, updated}."""
        data = self._r.hgetall(self._k("handler", name))
        if not data:
            return None
        data["deps"] = json.loads(data.get("deps", "[]"))
        data["display_fields"] = json.loads(data.get("display_fields", "[]"))
        data["version"] = int(data.get("version", 0))
        return data

    def handler_version(self, name: str) -> int:
        v = self._r.hget(self._k("handler", name), "version")
        return int(v) if v else 0

    def list_handlers(self) -> list[dict]:
        keys = self._r.keys(self._k("handler", "*"))
        result = []
        for k in sorted(keys):
            name = k.split(":")[-1]
            data = self._r.hgetall(k)
            result.append({
                "name": name,
                "version": int(data.get("version", 0)),
                "deps": json.loads(data.get("deps", "[]")),
                "display_fields": json.loads(data.get("display_fields", "[]")),
                "updated": data.get("updated", ""),
            })
        return result

    def remove_handler(self, name: str):
        self._r.delete(self._k("handler", name))

    # ── Worker State ──

    def update_state(self, worker: str, status: str,
                     last_task: str = "", count: int = 0, error: str = "",
                     handler: str = ""):
        self._r.hset(self._k("worker", worker), mapping={
            "status": status,
            "last_task": last_task,
            "last_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            "count": str(count),
            "error": error,
            "handler": handler,
        })
        self._r.expire(self._k("worker", worker), C.WORKER_STATE_TTL)

    def heartbeat(self, worker: str):
        self._r.set(self._k("heartbeat", worker),
                    time.strftime("%Y-%m-%d %H:%M:%S"), ex=C.HEARTBEAT_TTL)

    def clear_heartbeat(self, worker: str):
        self._r.delete(self._k("heartbeat", worker))

    def get_workers(self) -> list[dict]:
        keys = self._r.keys(self._k("worker", "*"))
        workers = []
        for k in sorted(keys):
            name = k.replace(self._k("worker", ""), "")
            state = self._r.hgetall(k)
            alive = self._r.exists(self._k("heartbeat", name))
            workers.append({"name": name, "alive": bool(alive), **state})
        return workers

    # ── Delay Config ──

    def get_delay_config(self, worker: str = "") -> dict:
        conf = {}
        if worker:
            conf = self._r.hgetall(self._k("delay", worker))
        if not conf:
            conf = self._r.hgetall(self._k("delay_config"))
        return {
            "min_delay": float(conf.get("min_delay", C.MIN_DELAY)),
            "max_delay": float(conf.get("max_delay", C.MAX_DELAY)),
            "batch_size": int(conf.get("batch_size", C.BATCH_SIZE)),
            "batch_pause": float(conf.get("batch_pause", C.BATCH_PAUSE)),
        }

    def set_delay_config(self, worker: str = "", **kwargs):
        k = self._k("delay", worker) if worker else self._k("delay_config")
        mapping = {k_: str(v) for k_, v in kwargs.items()
                   if k_ in ("min_delay", "max_delay", "batch_size", "batch_pause")}
        if mapping:
            self._r.hset(k, mapping=mapping)

    def del_delay_config(self, worker: str):
        self._r.delete(self._k("delay", worker))

    # ── Event Log ──

    def log_event(self, worker: str, task_id: str, status: str,
                  detail: str = ""):
        event = json.dumps({
            "worker": worker, "task_id": task_id,
            "event": status, "detail": detail,
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, ensure_ascii=False)
        pipe = self._r.pipeline()
        pipe.lpush(self._k("events"), event)
        pipe.ltrim(self._k("events"), 0, C.EVENT_MAX - 1)
        pipe.execute()

    def get_events(self, limit: int = 50) -> list[dict]:
        raw = self._r.lrange(self._k("events"), 0, limit - 1)
        return [json.loads(r) for r in raw]

    # ── Stats ──

    def incr_stat(self, field: str, n: int = 1):
        self._r.hincrby(self._k("stats"), field, n)

    def get_stats(self) -> dict:
        raw = self._r.hgetall(self._k("stats"))
        return {k: int(v) for k, v in raw.items()}

    # ── Task Results ──

    def save_result(self, task_id: str, result: dict):
        self._r.set(self._k("results", task_id),
                    json.dumps(result, ensure_ascii=False), ex=C.RESULT_TTL)

    def get_result(self, task_id: str) -> dict | None:
        raw = self._r.get(self._k("results", task_id))
        return json.loads(raw) if raw else None

    def list_results(self, limit: int = 50) -> list[dict]:
        """Scan result keys and return a list of {task_id, result}."""
        prefix = self._k("results", "")
        results = []
        cursor = 0
        while len(results) < limit:
            cursor, keys = self._r.scan(cursor, match=prefix + "*", count=100)
            for k in keys:
                task_id = k[len(prefix):]
                raw = self._r.get(k)
                if raw:
                    results.append({"task_id": task_id, "result": json.loads(raw)})
                if len(results) >= limit:
                    break
            if cursor == 0:
                break
        return results

    # ── Control Signals ──

    def set_control(self, worker: str, signal: str):
        self._r.set(self._k("control", worker), signal, ex=300)

    def get_control(self, worker: str) -> str:
        return self._r.get(self._k("control", worker)) or ""

    def clear_control(self, worker: str):
        self._r.delete(self._k("control", worker))

    # ── Pub/Sub ──

    def publish(self, channel: str, data: dict):
        self._r.publish(self._k(channel),
                        json.dumps(data, ensure_ascii=False))

    # ── Batch Count ──

    def incr_batch(self, worker: str) -> int:
        k = self._k("batch", worker)
        count = self._r.incr(k)
        self._r.expire(k, 3600)
        return count

    # ── Task Config ──

    def set_task_config(self, **kwargs):
        mapping = {k: str(v) for k, v in kwargs.items()}
        if mapping:
            self._r.hset(self._k("task_config"), mapping=mapping)

    def get_task_config(self) -> dict:
        return self._r.hgetall(self._k("task_config"))
