"""TaskLane Minimal Example — Master + Worker in-process demo.

Usage: python examples/demo.py
Prerequisite: Redis running on localhost:6379
"""

import threading
import time
import logging

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(name)s] %(message)s")

from tasklane import Master, Worker


# ── Define handler functions ──

def echo(params: dict) -> dict:
    """Simple echo handler: returns params as-is."""
    import time as _t
    _t.sleep(0.5)  # Simulate a time-consuming operation
    return {"echo": params, "processed_at": _t.strftime("%H:%M:%S")}


def add(params: dict) -> dict:
    """Addition handler."""
    a = params.get("a", 0)
    b = params.get("b", 0)
    return {"result": a + b}


def main():
    redis_url = "redis://localhost:6379/2"

    master = Master(redis_url=redis_url)

    # 1. Register handlers (code is distributed via Redis)
    master.register_handler("echo", echo)
    master.register_handler("add", add)
    print(f"Registered handlers: {[h['name'] for h in master.list_handlers()]}")

    # 2. Start Worker (background thread)
    worker = Worker(redis_url=redis_url, name="demo-worker")

    @worker.on_success
    def on_ok(task_id, handler, params, result):
        print(f"  ✓ {task_id} ({handler}): {result}")

    @worker.on_failure
    def on_fail(task_id, handler, params, error):
        print(f"  ✗ {task_id} ({handler}): {error}")

    t = threading.Thread(target=worker.run, daemon=True)
    t.start()
    time.sleep(1)  # Wait for worker to be ready

    # 3. Submit tasks
    print("\nSubmitting tasks...")
    master.submit("echo", {"msg": "hello tasklane"})
    master.submit("echo", {"msg": "second task"})
    master.submit("add", {"a": 10, "b": 20})

    # 4. Wait for execution to complete
    time.sleep(10)

    # 5. View stats
    stats = master.get_stats()
    print(f"\nStats: {stats}")
    print(f"Workers: {master.get_workers()}")

    # Stop worker
    master.stop(worker="demo-worker")
    time.sleep(2)
    print("Done.")


if __name__ == "__main__":
    main()
