"""TaskLane Master — Handler registration, task submission, monitoring, and control."""

from __future__ import annotations

import inspect
import re
import textwrap

from .core import RedisEngine, TaskMessage
from . import config as C


class Master:
    """Master interface: register handlers, submit tasks, monitor workers, adjust config dynamically."""

    def __init__(self, redis_url: str = "", namespace: str = ""):
        self._engine = RedisEngine(redis_url, namespace)

    # ── Handler Management ──

    def register_handler(self, name: str, func_or_source,
                         deps: list[str] | None = None,
                         display_fields: list[str] | None = None) -> int:
        """Register a handler.

        func_or_source: A Python function object or a source code string.
        Function objects will have their source extracted automatically,
        with the entry point renamed to handle(params).
        display_fields: List of result keys to display on the Dashboard.
        Returns the version number.
        """
        if callable(func_or_source):
            source = self._extract_source(func_or_source)
        else:
            source = func_or_source
        return self._engine.save_handler(name, source, deps, display_fields)

    @staticmethod
    def _extract_source(func) -> str:
        source = textwrap.dedent(inspect.getsource(func))
        # Strip decorator lines
        lines = source.split("\n")
        start = 0
        for i, line in enumerate(lines):
            if line.strip().startswith("def "):
                start = i
                break
        source = "\n".join(lines[start:])
        # Rename the original function name to handle
        source = re.sub(r"^def\s+\w+\s*\(", "def handle(", source, count=1)
        return source

    def register_handler_from_file(self, name: str, filepath: str,
                                   deps: list[str] | None = None,
                                   display_fields: list[str] | None = None) -> int:
        """Register a handler from a .py file. The file must define a handle(params) function."""
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        return self._engine.save_handler(name, source, deps, display_fields)

    def list_handlers(self) -> list[dict]:
        return self._engine.list_handlers()

    def remove_handler(self, name: str):
        self._engine.remove_handler(name)

    # ── Task Submission ──

    def submit(self, handler: str, params: dict | None = None,
               max_retries: int = C.RETRY_MAX,
               retry_delay: float = C.RETRY_DELAY) -> str:
        msg = TaskMessage(handler=handler, params=params or {},
                          max_retries=max_retries, retry_delay=retry_delay)
        self._engine.enqueue(msg)
        return msg.task_id

    def submit_bulk(self, handler: str, params_list: list[dict],
                    max_retries: int = C.RETRY_MAX,
                    retry_delay: float = C.RETRY_DELAY) -> list[str]:
        ids = []
        for params in params_list:
            ids.append(self.submit(handler, params, max_retries, retry_delay))
        return ids

    # ── Config ──

    def set_task_config(self, **kwargs):
        self._engine.set_task_config(**kwargs)

    def get_task_config(self) -> dict:
        return self._engine.get_task_config()

    def set_delay(self, worker: str = "", **kwargs):
        self._engine.set_delay_config(worker=worker, **kwargs)

    def get_delay(self, worker: str = "") -> dict:
        return self._engine.get_delay_config(worker)

    def del_delay(self, worker: str):
        self._engine.del_delay_config(worker)

    # ── Monitoring ──

    def get_workers(self) -> list[dict]:
        return self._engine.get_workers()

    def get_events(self, limit: int = 50) -> list[dict]:
        return self._engine.get_events(limit)

    def get_stats(self) -> dict:
        return self._engine.get_stats()

    def get_result(self, task_id: str) -> dict | None:
        return self._engine.get_result(task_id)

    def pop_result(self, timeout: int = 5) -> dict | None:
        """Pop one result from the result queue (BRPOP). Returns {"task_id": ..., "result": ...} or None."""
        return self._engine.pop_result(timeout)

    def collect_results(self, task_ids: list[str], timeout: float = 300,
                        poll_interval: float = 1.0) -> dict[str, dict]:
        """Wait and collect results for a list of task IDs.

        Returns a dict mapping task_id -> result for all completed tasks.
        Raises TimeoutError if not all results are collected within timeout.
        """
        import time
        collected: dict[str, dict] = {}
        start = time.time()
        remaining = set(task_ids)

        while remaining and (time.time() - start) < timeout:
            for tid in list(remaining):
                r = self._engine.get_result(tid)
                if r is not None:
                    collected[tid] = r
                    remaining.discard(tid)
            if remaining:
                time.sleep(poll_interval)

        if remaining:
            raise TimeoutError(
                f"Timed out waiting for {len(remaining)}/{len(task_ids)} results"
            )
        return collected

    def queue_len(self) -> int:
        return self._engine.queue_len()

    # ── Control ──

    def pause(self, worker: str = ""):
        if worker:
            self._engine.set_control(worker, "pause")
        else:
            for w in self._engine.get_workers():
                self._engine.set_control(w["name"], "pause")

    def resume(self, worker: str = ""):
        if worker:
            self._engine.clear_control(worker)
        else:
            for w in self._engine.get_workers():
                self._engine.clear_control(w["name"])

    def stop(self, worker: str = ""):
        if worker:
            self._engine.set_control(worker, "stop")
        else:
            for w in self._engine.get_workers():
                self._engine.set_control(w["name"], "stop")

    def purge(self) -> int:
        return self._engine.queue_purge()
