"""Echo handler — Minimal example.

Register via CLI: tasklane register echo examples/echo_handler.py
"""


def handle(params: dict) -> dict:
    """Return params as-is, with processing timestamp."""
    import time
    time.sleep(0.5)
    return {"echo": params, "processed_at": time.strftime("%Y-%m-%d %H:%M:%S")}
