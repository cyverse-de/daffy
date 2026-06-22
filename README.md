# daffy

Ships and manages log messages stored in DuckDB databases. Provides a process wrapper
(`daffy`) and an aggregator service (`scrooge`).

Logs are transported with the DuckDB [Quack remote protocol](https://duckdb.org/docs/current/quack/overview):
Scrooge runs a Quack server and daffy instances `ATTACH` it and ship rows as plain SQL
`INSERT`s. Quack requires DuckDB ≥ 1.5.3, which the Python `duckdb` package provides (the
Go driver is still on 1.4.1), so this project is implemented in Python (managed with `uv`).

## daffy

`daffy` wraps any process, teeing its stdout/stderr to the console (so `kubectl logs` and
similar still work) **and** recording each line to a local DuckDB buffer. The buffer is
bounded: lines accrue until a size threshold (or interval) triggers a batch flush to
Scrooge, after which the flushed rows are deleted locally. If Scrooge is unreachable the
rows are retained and retried; if the buffer exceeds its cap the oldest rows are dropped.

```
daffy --service my-svc \
      --scrooge-uri quack:scrooge-host:9494 \
      -- my-server --port 8080
```

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
scrooge --storage-dir ./scrooge --quack-port 9494
```

Configuration (env-first): `SCROOGE_DB`, `SCROOGE_STORAGE_DIR`, `SCROOGE_QUACK_HOST`,
`SCROOGE_QUACK_PORT`, `SCROOGE_TOKEN`, `SCROOGE_RETENTION_ROWS`, `SCROOGE_SWEEP_INTERVAL`.

## Development

```
just install     # uv sync
just check       # ruff + pyright + pytest
just test
```

Container images: `just build-daffy-image` and `just build-scrooge-image`.
