# daffy / scrooge

Ships and manages log messages stored in DuckDB databases. Two console scripts built from
one repo:

- **daffy** (`src/daffy/`) — a process wrapper. Tees a child's stdout/stderr to the console
  *and* buffers each line in a local DuckDB, batch-shipping to scrooge.
- **scrooge** (`src/scrooge/`) — the aggregator. Runs a DuckDB Quack server that daffy
  instances `ATTACH` and `INSERT` into; ages older logs out to per-service Parquet files.

## Tooling

- The project is managed with `uv`. Run everything through it: `uv run daffy ...`,
  `uv run scrooge ...`, `uv run pytest`.
- `just check` runs the gate: `ruff check` + `pyright` + `pytest`. Keep all three green —
  `just check` must pass before a change is done. (`just lint`, `just fmt`, `just typecheck`,
  `just test` run them individually.)
- Requires Python ≥ 3.12.

## Why Python (not Go)

Transport is the DuckDB Quack remote protocol, which needs DuckDB ≥ 1.5.3. The Go driver is
stuck at 1.4.1, so this is Python. Don't try to port the transport to Go.

## Do not add OpenTelemetry

CyVerse DE dropped otel. Use stdlib `logging`; don't add otel deps or instrumentation.

## Conventions specific to this repo

- **The `logs` schema is canonical in `daffy/schema.py`.** `COLUMNS` drives every
  `INSERT`/`SELECT` in both daffy and scrooge. If you change columns or their order, update
  `COLUMNS` and `CREATE_LOGS_TABLE` together — nothing else hard-codes the list.
- **SQL that can't be parameterized uses `daffy.sql.sql_literal`.** A few statements take no
  bind parameters — `ATTACH` URIs, `COPY ... TO` paths, `CALL quack_serve(...)`. Use the
  shared `sql_literal` helper for those; don't hand-roll quote-doubling, and prefer `?`
  placeholders everywhere a bind parameter is accepted.
- **DuckDB connections are not thread-safe.** `LogStore` and `ScroogeServer` each serialize
  *all* Python access through a single `threading.Lock`. The shipper's background flush
  thread and scrooge's sweep/monitor threads rely on this — any new DB access must go through
  the existing lock, not a second connection. (The embedded Quack server runs its own threads
  against the same database; that concurrency is Quack's to manage, not ours.)
- **Config is env-first with CLI-flag fallback** (`daffy/config.py`, `scrooge/config.py`).
  Env wins so secrets (the Scrooge token) don't show up in `ps aux`. Add new settings to the
  `build_config` for the relevant binary and expose both an env var and a flag.

## Gotchas

- **daffy's default `local_db` is `:memory:`.** Buffered-but-unshipped rows are lost if the
  process exits while scrooge is unreachable. Set `DAFFY_LOCAL_DB` to a file to survive
  restarts. This is intentional (best-effort logging), but keep it in mind.
- **Tests stand up a real Quack server** on a free localhost port (the `scrooge` fixture in
  `tests/conftest.py`). The shipper/monitor/server tests need loopback networking and the
  bundled `quack` extension to load.

## Local state (gitignored, don't commit)

`*.duckdb`, `*.duckdb.wal`, and `./scrooge/` are runtime artifacts produced by running the
binaries locally. They're gitignored; don't add them or stray debug scripts to the repo.
