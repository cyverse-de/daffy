# daffy

Ships and manages log messages stored in DuckDB databases. Provides a process wrapper
(`daffy`) and an aggregator service (`scrooge`).

Logs are transported with the DuckDB [Quack remote protocol](https://duckdb.org/docs/current/quack/overview):
Scrooge runs a Quack server and daffy instances `ATTACH` it and ship rows as plain SQL
`INSERT`s. Quack requires DuckDB ≥ 1.5.3, which the Python `duckdb` package provides (the
Go driver is still on 1.4.1), so this project is implemented in Python (managed with `uv`).

## Running with uv

The project is managed with [uv](https://docs.astral.sh/uv/). Install dependencies once:

```
uv sync
```

Both commands are exposed as project scripts, so run them through uv (no manual venv
activation needed):

```
uv run daffy --help
uv run scrooge --help
```

`uv run` is used in the examples below; in a built container image `daffy`/`scrooge` are
the entrypoints, so you pass just their arguments.

## daffy

`daffy` wraps any process, teeing its stdout/stderr to the console (so `kubectl logs` and
similar still work) **and** recording each line to a local DuckDB buffer. The buffer is
bounded: lines accrue until a size threshold (or interval) triggers a batch flush to
Scrooge, after which the flushed rows are deleted locally. If Scrooge is unreachable the
rows are retained and retried; if the buffer exceeds its cap the oldest rows are dropped.

```
uv run daffy --service my-svc \
      --scrooge-uri quack:scrooge-host:9494 \
      -- my-server --port 8080
```

Everything after `--` is the wrapped command and its arguments.

Configuration is resolved env-first with CLI-flag fallback: `SERVICE_NAME`,
`DAFFY_LOCAL_DB`, `POD_NAME`, `NODE_NAME`, `SCROOGE_URI`, `SCROOGE_TOKEN`,
`DAFFY_FLUSH_BYTES`, `DAFFY_FLUSH_INTERVAL`, `DAFFY_MAX_BUFFER_BYTES`. With no
`SCROOGE_URI`, daffy logs locally only (no shipping).

## Scrooge — the log aggregator/hoarding service

Scrooge aggregates the logs shipped to it by individual daffy instances. It keeps a
configurable number of logs per service in its local DuckDB; when a service exceeds the
threshold, the oldest log-days are written to Parquet files and removed from the live
table.

The Parquet archive is rooted at `SCROOGE_STORAGE_DIR` (default `./scrooge`). Each service
gets its own lower-cased directory, and each file is named like
`2026-06-22-001_service-name.parquet` (date plus a per-day sequence number), e.g.
`./scrooge/my-service/2026-06-22-001_my-service.parquet`. This makes logs searchable by
service and date, with multiple files per date as volume requires.

Scrooge only aggregates and serves the logs it knows about — it never queries the live
daffy instances. Clients query over Quack: `ATTACH` Scrooge and `SELECT` from the
`all_logs` view, which transparently unions the live table and the Parquet archive.

```
uv run scrooge --storage-dir ./scrooge --quack-port 9494 --token my-shared-token
```

Configuration (env-first): `SCROOGE_DB`, `SCROOGE_STORAGE_DIR`, `SCROOGE_QUACK_HOST`,
`SCROOGE_QUACK_PORT`, `SCROOGE_TOKEN`, `SCROOGE_RETENTION_ROWS`, `SCROOGE_SWEEP_INTERVAL`.
Set a fixed `--token`/`SCROOGE_TOKEN` so daffy instances can be provisioned with it;
otherwise `quack_serve` issues a random token at each boot.

## Local end-to-end example

In one terminal, start Scrooge with a shared token:

```
SCROOGE_TOKEN=dev-token uv run scrooge --storage-dir ./scrooge --quack-port 9494
```

In another, wrap a command and ship its output:

```
SCROOGE_TOKEN=dev-token uv run daffy --service demo \
      --scrooge-uri quack:127.0.0.1:9494 \
      -- sh -c 'for i in $(seq 1 20); do echo "line $i"; done'
```

Query the aggregated logs over Quack (live rows plus the Parquet archive):

```
uv run python - <<'PY'
import duckdb
c = duckdb.connect(); c.execute("LOAD quack")
c.execute("ATTACH 'quack:127.0.0.1:9494' AS scrooge (TOKEN 'dev-token')")
print(c.execute("SELECT count(*) FROM scrooge.all_logs").fetchone()[0])
PY
```

## Development

```
uv sync                  # install dependencies (or: just install)
uv run ruff check .      # lint
uv run ruff format .     # format
uv run pyright           # type-check
uv run pytest            # tests
```

The `Justfile` wraps these: `just check` runs ruff + pyright + pytest, and
`just build-daffy-image` / `just build-scrooge-image` build the container images.
