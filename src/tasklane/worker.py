"""TaskLane Worker — Pure execution engine; handler code is dynamically loaded from Redis."""

from __future__ import annotations

import importlib
import logging
import random
import signal
import subprocess
import sys
import time
from typing import Callable

from .core import RedisEngine, TaskMessage

log = logging.getLogger("tasklane.worker")


class Worker:
    """Distributed task Worker.

    After starting, enters a BRPOP loop to fetch tasks from the Redis queue,
    dynamically loads handler code for execution, and reports state and results.
    """

    def __init__(self, redis_url: str = "", namespace: str = "",
                 name: str = "worker"):
        self._engine = RedisEngine(redis_url, namespace)
        self.name = name
        self._running = False
        self._handler_cache: dict[str, tuple[int, Callable]] = {}
        self._on_success: Callable | None = None
        self._on_failure: Callable | None = None
        self._last_task_id: str = ""
        self._last_handler: str = ""

    # ── Callback Decorators ──

    def on_success(self, fn: Callable) -> Callable:
        self._on_success = fn
        return fn

    def on_failure(self, fn: Callable) -> Callable:
        self._on_failure = fn
        return fn

    # ── Dynamic Handler Loading ──

    def _load_handler(self, name: str) -> Callable:
        """Load handler from Redis with local caching and version checking."""
        remote_ver = self._engine.handler_version(name)
        if name in self._handler_cache:
            cached_ver, cached_fn = self._handler_cache[name]
            if cached_ver == remote_ver:
                return cached_fn

        data = self._engine.load_handler(name)
        if not data:
            raise ValueError(f"handler '{name}' is not registered")

        # Auto-install missing dependencies
        self._ensure_deps(data["deps"])

        # Compile and execute
        ns: dict = {}
        exec(compile(data["source"], f"<handler:{name}>", "exec"), ns)
        fn = ns.get("handle")
        if fn is None:
            raise ValueError(f"handler '{name}' does not define a handle(params) function")

        self._handler_cache[name] = (data["version"], fn)
        log.info(f"Loaded handler '{name}' v{data['version']}")
        return fn

    # pip package name → import name mapping
    _IMPORT_MAP = {
        "beautifulsoup4": "bs4",
        "pillow": "PIL",
        "scikit-learn": "sklearn",
        "python-dateutil": "dateutil",
        "pyyaml": "yaml",
        "opencv-python": "cv2",
    }

    @staticmethod
    def _ensure_deps(deps: list[str]):
        for pkg in deps:
            import_name = Worker._IMPORT_MAP.get(pkg, pkg.replace("-", "_"))
            try:
                importlib.import_module(import_name)
            except ImportError:
                log.info(f"Installing dependency: {pkg}")
                subprocess.check_call(
                    [sys.executable, "-m", "pip", "install", "-q",
                     "--break-system-packages", pkg],
                    stdout=subprocess.DEVNULL,
                )

    # ── Delay Control ──

    def _do_delay(self):
        conf = self._engine.get_delay_config(self.name)
        if conf["min_delay"] > 0:
            self._engine.update_state(self.name, "waiting",
                                      last_task=self._last_task_id,
                                      handler=self._last_handler)
            self._interruptible_sleep(random.uniform(conf["min_delay"], conf["max_delay"]))
        # batch pause
        bs = conf["batch_size"]
        if bs > 0:
            count = self._engine.incr_batch(self.name)
            if count % bs == 0:
                log.info(f"Batch pause: {conf['batch_pause']}s (executed {count} tasks)")
                self._interruptible_sleep(conf["batch_pause"])

    def _interruptible_sleep(self, seconds: float):
        """Sleep in 1s intervals, checking _running each iteration."""
        end = time.time() + seconds
        while self._running and time.time() < end:
            time.sleep(min(1.0, end - time.time()))

    # ── Task Execution ──

    def _execute(self, msg: TaskMessage):
        self._last_task_id = msg.task_id
        self._last_handler = msg.handler
        self._engine.update_state(self.name, "running",
                                  last_task=msg.task_id, handler=msg.handler)
        try:
            fn = self._load_handler(msg.handler)
            result = fn(msg.params) or {}

            # ── Defer signals during result save ──
            old_sigint = signal.getsignal(signal.SIGINT)
            old_sigterm = signal.getsignal(signal.SIGTERM)
            _deferred_stop = False

            def _defer(signum, frame):
                nonlocal _deferred_stop
                _deferred_stop = True

            signal.signal(signal.SIGINT, _defer)
            signal.signal(signal.SIGTERM, _defer)
            try:
                self._engine.update_state(self.name, "ok",
                                          last_task=msg.task_id,
                                          count=len(result),
                                          handler=msg.handler)
                self._engine.save_result(msg.task_id, result)

                handler_data = self._engine.load_handler(msg.handler)
                display_fields = handler_data.get("display_fields", []) if handler_data else []
                if display_fields:
                    parts = [f"{f}={result.get(f)}" for f in display_fields if f in result]
                    detail = f"{msg.handler}: {', '.join(parts)}"
                else:
                    detail = f"{msg.handler}: {len(result)} fields"
                self._engine.log_event(self.name, msg.task_id, "ok", detail)
                self._engine.incr_stat("success")

                if self._on_success:
                    self._on_success(msg.task_id, msg.handler, msg.params, result)
            finally:
                signal.signal(signal.SIGINT, old_sigint)
                signal.signal(signal.SIGTERM, old_sigterm)
                if _deferred_stop:
                    log.info("Stop signal received during result save, stopping now...")
                    self._running = False

        except Exception as exc:
            error_str = str(exc)
            if msg.retries < msg.max_retries:
                msg.retries += 1
                self._engine.enqueue_delayed(msg, msg.retry_delay)
                self._engine.update_state(self.name, "retrying",
                                          last_task=msg.task_id, error=error_str,
                                          handler=msg.handler)
                self._engine.log_event(self.name, msg.task_id, "retrying",
                                       f"retry {msg.retries}/{msg.max_retries}: {error_str}")
                self._engine.incr_stat("retried")
                log.warning(f"Task {msg.task_id} retrying {msg.retries}/{msg.max_retries}: {error_str}")
            else:
                self._engine.update_state(self.name, "error",
                                          last_task=msg.task_id, error=error_str,
                                          handler=msg.handler)
                self._engine.log_event(self.name, msg.task_id, "error",
                                       f"max retries: {error_str}")
                self._engine.incr_stat("failed")
                log.error(f"Task {msg.task_id} failed: {error_str}")

                if self._on_failure:
                    self._on_failure(msg.task_id, msg.handler, msg.params, error_str)

    # ── Main Loop ──

    def run(self):
        """Start the Worker main loop (blocking)."""
        self._running = True

        # Signals can only be registered in the main thread
        import threading
        if threading.current_thread() is threading.main_thread():
            def _stop(signum, frame):
                log.info("Received stop signal, waiting for current task to finish...")
                self._running = False
            signal.signal(signal.SIGTERM, _stop)
            signal.signal(signal.SIGINT, _stop)

        log.info(f"Worker '{self.name}' started")
        self._engine.heartbeat(self.name)
        self._engine.update_state(self.name, "idle")

        while self._running:
            self._engine.heartbeat(self.name)

            # Check control signals
            ctrl = self._engine.get_control(self.name)
            if ctrl == "stop":
                log.info("Received stop signal")
                break
            if ctrl == "pause":
                self._engine.update_state(self.name, "paused")
                time.sleep(1)
                continue

            # Promote delayed queue
            self._engine.promote_delayed()

            # Fetch task
            msg = self._engine.dequeue()
            if msg is None:
                self._engine.update_state(self.name, "idle",
                                          last_task=self._last_task_id,
                                          handler=self._last_handler)
                continue

            self._execute(msg)
            self._do_delay()

        self._engine.update_state(self.name, "stopped")
        self._engine.clear_heartbeat(self.name)
        log.info(f"Worker '{self.name}' stopped")
