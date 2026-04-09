"""Distributed computation demo — calculate Pi using Monte Carlo method.

Master splits the work into chunks, each Worker runs a random sampling batch,
results are aggregated to estimate Pi.

Usage:
    1. Start worker(s):  tasklane --redis redis://localhost:6379/2 worker --name w1
    2. Run this script:  python examples/distributed_pi.py
"""

import time
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")

from tasklane import Master

# ── Handler: Monte Carlo Pi estimation (runs on Worker) ──

def monte_carlo_pi(params: dict) -> dict:
    """Sample random points, count how many fall inside the unit circle."""
    import random
    n = params.get("samples", 100000)
    seed = params.get("seed", None)
    if seed is not None:
        random.seed(seed)
    inside = 0
    for _ in range(n):
        x, y = random.random(), random.random()
        if x * x + y * y <= 1.0:
            inside += 1
    return {"inside": inside, "total": n}


def main():
    redis_url = "redis://localhost:6379/2"
    master = Master(redis_url=redis_url)

    # Register handler
    master.register_handler("monte_carlo_pi", monte_carlo_pi)
    print("Handler 'monte_carlo_pi' registered.\n")

    # Split into 20 chunks, 500k samples each = 10M total
    chunks = 20
    samples_per_chunk = 500_000
    total_samples = chunks * samples_per_chunk

    print(f"Submitting {chunks} tasks, {samples_per_chunk} samples each ({total_samples:,} total)...")
    task_ids = []
    for i in range(chunks):
        tid = master.submit("monte_carlo_pi", {
            "samples": samples_per_chunk,
            "seed": i * 1000,
        })
        task_ids.append(tid)
    print(f"Submitted {len(task_ids)} tasks.\n")

    # Wait and collect results
    print("Waiting for results...")
    collected = {}
    timeout = 300  # 5 min max
    start = time.time()

    while len(collected) < chunks and (time.time() - start) < timeout:
        for tid in task_ids:
            if tid in collected:
                continue
            result = master.get_result(tid)
            if result is not None:
                collected[tid] = result
                print(f"  [{len(collected)}/{chunks}] task {tid}: "
                      f"inside={result['inside']}, total={result['total']}")
        if len(collected) < chunks:
            time.sleep(1)

    if len(collected) < chunks:
        print(f"\nTimeout! Only got {len(collected)}/{chunks} results.")
        return

    # Aggregate
    total_inside = sum(r["inside"] for r in collected.values())
    total_n = sum(r["total"] for r in collected.values())
    pi_estimate = 4.0 * total_inside / total_n
    elapsed = time.time() - start

    print(f"\n{'='*40}")
    print(f"  Total samples:  {total_n:,}")
    print(f"  Inside circle:  {total_inside:,}")
    print(f"  Pi estimate:    {pi_estimate:.8f}")
    print(f"  Actual Pi:      3.14159265...")
    print(f"  Error:          {abs(pi_estimate - 3.14159265):,.8f}")
    print(f"  Time:           {elapsed:.1f}s")
    print(f"{'='*40}")


if __name__ == "__main__":
    main()
