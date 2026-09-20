# Permanent deployment

The supported permanent deployment is a read-only Docker Compose service behind
an HTTPS reverse proxy. The application image contains the source, pinned Python
dependencies, frozen release manifest, completion model, final audit and universe
reconciliation. Large raw exchange evidence and historical caches remain outside
Git and are mounted read-only from durable host storage.

## Persistent evidence layout

Copy the validated local `data/` tree to `/srv/stock-ranking/data` and the
validated `research/` tree to `/srv/stock-ranking/research`. Preserve file names,
accepted-state pointers and hashes. Do not rebuild or edit the accepted snapshot
in place. Updates must create a new candidate snapshot, validate it, and only then
atomically replace the accepted-state pointer using the existing data-state code.

Create `.env` from `.env.example`, then deploy:

```sh
docker compose build --pull
docker compose up -d
docker compose ps
curl --fail http://127.0.0.1:8765/api/health
```

The container runs as an unprivileged user, drops Linux capabilities, uses a
read-only root filesystem, and mounts evidence read-only. Both automatic refresh
and the refresh API are disabled. Scheduled refresh should run as a separate,
single-writer maintenance job against a staging copy. Promotion is allowed only
after the normal acceptance checks and release verification succeed.

The reverse proxy should terminate TLS, forward to port 8765, impose request and
connection limits, and monitor `/api/health`. A non-200 readiness response means
the mounted evidence does not match the frozen release and the instance must not
receive traffic.
