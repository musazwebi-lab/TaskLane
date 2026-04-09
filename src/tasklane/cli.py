"""TaskLane CLI entry point.

Global flags --redis and --ns go before the subcommand.

Usage:
    tasklane --redis redis://host:6379/0 worker --name w1
    tasklane --redis redis://host:6379/0 dashboard --port 5000
    tasklane --redis redis://host:6379/0 submit handler_name '{"key": "value"}'
    tasklane --redis redis://host:6379/0 register handler_name ./handler.py
    tasklane --redis redis://host:6379/0 handlers
    tasklane --redis redis://host:6379/0 remove-handler handler_name
    tasklane --redis redis://host:6379/0 set-delay --min 5 --max 10
    tasklane --redis redis://host:6379/0 monitor
    tasklane --redis redis://host:6379/0 pause [--worker w1]
    tasklane --redis redis://host:6379/0 resume [--worker w1]
    tasklane --redis redis://host:6379/0 purge
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import time


def cmd_worker(args):
    from .worker import Worker
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(name)s] %(message)s")
    w = Worker(redis_url=args.redis, namespace=args.ns, name=args.name)
    w.run()


def cmd_dashboard(args):
    from .dashboard import create_app
    app = create_app(args.redis, args.ns)
    print(f"TaskLane Dashboard: http://localhost:{args.port}")
    app.run(host=args.host, port=args.port, debug=False)


def cmd_submit(args):
    from .master import Master
    m = Master(redis_url=args.redis, namespace=args.ns)
    params = json.loads(args.params) if args.params else {}
    tid = m.submit(args.handler, params)
    print(f"Submitted: {tid}")


def cmd_register(args):
    from .master import Master
    m = Master(redis_url=args.redis, namespace=args.ns)
    deps = [d.strip() for d in args.deps.split(",") if d.strip()] if args.deps else []
    ver = m.register_handler_from_file(args.name, args.file, deps=deps)
    print(f"Registered handler '{args.name}' v{ver}")


def cmd_handlers(args):
    from .master import Master
    m = Master(redis_url=args.redis, namespace=args.ns)
    for h in m.list_handlers():
        print(f"  {h['name']}  v{h['version']}  deps={h['deps']}  {h['updated']}")


def cmd_remove_handler(args):
    from .master import Master
    m = Master(redis_url=args.redis, namespace=args.ns)
    m.remove_handler(args.name)
    print(f"Removed handler '{args.name}'")


def cmd_set_delay(args):
    from .master import Master
    m = Master(redis_url=args.redis, namespace=args.ns)
    kwargs = {}
    if args.min is not None: kwargs["min_delay"] = args.min
    if args.max is not None: kwargs["max_delay"] = args.max
    if args.batch_size is not None: kwargs["batch_size"] = args.batch_size
    if args.batch_pause is not None: kwargs["batch_pause"] = args.batch_pause
    if not kwargs:
        conf = m.get_delay(args.worker or "")
        for k, v in conf.items():
            print(f"  {k} = {v}")
        return
    m.set_delay(worker=args.worker or "", **kwargs)
    print("Delay config updated")


def cmd_monitor(args):
    from .master import Master
    m = Master(redis_url=args.redis, namespace=args.ns)
    print("Monitoring... (Ctrl+C to exit)")
    try:
        while True:
            stats = m.get_stats()
            qlen = m.queue_len()
            workers = m.get_workers()
            alive = sum(1 for w in workers if w.get("alive"))
            print(f"\r[{time.strftime('%H:%M:%S')}] "
                  f"queue={qlen} workers={alive}/{len(workers)} "
                  f"success={stats.get('success',0)} "
                  f"failed={stats.get('failed',0)} "
                  f"retried={stats.get('retried',0)}",
                  end="", flush=True)
            time.sleep(5)
    except KeyboardInterrupt:
        print("\nMonitoring ended")


def cmd_pause(args):
    from .master import Master
    m = Master(redis_url=args.redis, namespace=args.ns)
    m.pause(args.worker or "")
    print(f"Paused {'worker: ' + args.worker if args.worker else 'all workers'}")


def cmd_resume(args):
    from .master import Master
    m = Master(redis_url=args.redis, namespace=args.ns)
    m.resume(args.worker or "")
    print(f"Resumed {'worker: ' + args.worker if args.worker else 'all workers'}")


def cmd_purge(args):
    from .master import Master
    m = Master(redis_url=args.redis, namespace=args.ns)
    n = m.purge()
    print(f"Purged {n} tasks")


def main():
    parser = argparse.ArgumentParser(prog="tasklane",
                                     description="TaskLane distributed task dispatching framework")
    parser.add_argument("--redis", default="", help="Redis URL")
    parser.add_argument("--ns", default="", help="Namespace")
    sub = parser.add_subparsers(dest="cmd")

    # worker
    p = sub.add_parser("worker", help="Start a Worker")
    p.add_argument("--name", default="worker", help="Worker name")

    # dashboard
    p = sub.add_parser("dashboard", help="Start the Web Dashboard")
    p.add_argument("--host", default="0.0.0.0")
    p.add_argument("--port", type=int, default=5000)

    # submit
    p = sub.add_parser("submit", help="Submit a task")
    p.add_argument("handler", help="Handler name")
    p.add_argument("params", nargs="?", default="{}", help="Params JSON")

    # register
    p = sub.add_parser("register", help="Register a Handler")
    p.add_argument("name", help="Handler name")
    p.add_argument("file", help="Python source file path")
    p.add_argument("--deps", default="", help="Dependencies, comma-separated")

    # handlers
    sub.add_parser("handlers", help="List all Handlers")

    # remove-handler
    p = sub.add_parser("remove-handler", help="Remove a Handler")
    p.add_argument("name", help="Handler name")

    # set-delay
    p = sub.add_parser("set-delay", help="Set delay parameters")
    p.add_argument("--worker", default="", help="Target Worker (empty = global)")
    p.add_argument("--min", type=float, default=None)
    p.add_argument("--max", type=float, default=None)
    p.add_argument("--batch-size", type=int, default=None)
    p.add_argument("--batch-pause", type=float, default=None)

    # monitor
    sub.add_parser("monitor", help="Real-time monitoring")

    # pause / resume / purge
    p = sub.add_parser("pause", help="Pause Worker")
    p.add_argument("--worker", default="")
    p = sub.add_parser("resume", help="Resume Worker")
    p.add_argument("--worker", default="")
    sub.add_parser("purge", help="Purge queue")

    args = parser.parse_args()
    cmds = {
        "worker": cmd_worker, "dashboard": cmd_dashboard,
        "submit": cmd_submit, "register": cmd_register,
        "handlers": cmd_handlers, "remove-handler": cmd_remove_handler,
        "set-delay": cmd_set_delay, "monitor": cmd_monitor,
        "pause": cmd_pause, "resume": cmd_resume, "purge": cmd_purge,
    }
    fn = cmds.get(args.cmd)
    if fn:
        fn(args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
