# Changelog

## v0.3.0 (2026-04-15)

### Features

- **Per-worker stats**: Each worker now tracks its own success/retried/failed counts via `chictr:wstats:{worker}` Redis keys. Dashboard worker table shows Completed and Speed columns.
- **Dashboard UI redesign**: Cleaner layout with badge-style status indicators, compact panels, grid-2 layout for handlers/delay and event log.

---

## v0.2.1 (2026-04-14)

### Fixes

- **pip install from git fails on old setuptools**: Added `setup.cfg` with name/version for compatibility with setuptools < 61 which cannot read `[project]` from `pyproject.toml`.

---

## v0.2.0 (2026-04-10)

### Features

- **Readable task IDs**: Task IDs are now generated from params (e.g. `5-a1b2c3`, `12345-a1b2c3`) instead of random hex. Falls back to random when params are empty.
- **Per-worker delay config**: Each worker can have its own delay settings independent of the global config. Dashboard shows delay column with Set/Reset buttons per worker.
- **Clear event log**: Added "Clear" button on dashboard to purge event history.
- **Reset stats**: Added "Reset Stats" button on dashboard to zero out success/failed/retried counters.
- **Result queue**: Added real-time result consumption via Redis List BRPOP (`pop_result`), enabling Master scripts to process results as they arrive.
- **CLI: subcommand-level --redis/--ns**: `--redis` and `--ns` are now specified after the subcommand (e.g. `tasklane worker --redis ... --ns ...`).
- **Dashboard speed & ETA**: Queue card shows estimated time remaining, Success card shows processing speed (2-minute sliding window average).

### Improvements

- **Interruptible delay**: Worker delay periods use 1-second interval sleep, allowing graceful shutdown during wait.
- **Signal deferral during result save**: SIGINT/SIGTERM are deferred while saving results to Redis, preventing data loss. Signals are honored immediately after save completes.
- **Dependency install optimization**: Added pip package name to import name mapping (`_IMPORT_MAP`) so packages like `beautifulsoup4` are checked via `import bs4` instead of reinstalling every time. Added `--break-system-packages` flag for pip install.

### API

- `POST /api/events/clear` — Clear all event logs
- `POST /api/stats/clear` — Reset execution stats
- `GET /api/delay/<worker>` — Get worker-specific delay config
- `POST /api/delay/<worker>` — Set worker-specific delay config
- `DELETE /api/delay/<worker>` — Reset worker to global delay config

### Fixes

- **CLI --redis/--ns not working before subcommand**: Global `--redis`/`--ns` flags were silently ignored due to argparse subcommand namespace override. Moved to subcommand-level args.
- **Worker reinstalling deps every task**: `beautifulsoup4`, `pillow`, `scikit-learn` etc. were detected as missing because pip package name differs from import name. Added `_IMPORT_MAP` lookup.
- **Worker not stoppable during delay**: `time.sleep()` blocked the entire delay period. Replaced with 1-second interval loop checking `_running` flag.
- **Data loss on worker stop during result save**: SIGINT/SIGTERM during Redis write could leave results unsaved. Signals are now deferred until save completes.
- **pip install failing in system Python**: Added `--break-system-packages` flag to pip install command.

---

## v0.1.0 (2026-04-09)

Initial release.

- Redis-based distributed task queue with dynamic handler code distribution
- Worker with BRPOP loop, handler caching, auto-dependency install
- Master API for handler registration, task submission, monitoring
- Web dashboard with real-time overview, worker control, delay config
- CLI with subcommands: worker, dashboard, submit, register, handlers, set-delay, monitor, pause, resume, purge
- Retry with configurable max retries and delay
- Batch pause support
- Event logging and execution stats
