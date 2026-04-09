"""TaskLane — Constants, defaults, and Redis key schema."""

import os

# ── Redis ──
REDIS_URL = os.environ.get("TASKLANE_REDIS_URL", "redis://localhost:6379/0")
NAMESPACE = os.environ.get("TASKLANE_NS", "tl")

# ── Delay control ──
MIN_DELAY = 1.0
MAX_DELAY = 3.0
BATCH_SIZE = 0       # 0 = batch pause disabled
BATCH_PAUSE = 0.0

# ── Retry ──
RETRY_MAX = 3
RETRY_DELAY = 60     # seconds

# ── Worker ──
HEARTBEAT_TTL = 60        # Heartbeat expiry in seconds
WORKER_STATE_TTL = 86400  # Worker state retained for 1 day
RESULT_TTL = 604800       # Task result retained for 7 days
EVENT_MAX = 1000          # Event log max entries
BRPOP_TIMEOUT = 5         # BRPOP timeout in seconds


def key(*parts: str, ns: str = "") -> str:
    """Build a Redis key, e.g. key("queue", "default") -> "tl:queue:default"."""
    return ":".join([ns or NAMESPACE] + list(parts))
