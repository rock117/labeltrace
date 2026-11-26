#!/bin/sh
set -e

echo "waiting for postgres..."
python - <<'PY'
import os, socket, time, urllib.parse

url = os.environ.get("DATABASE_URL", "")
# postgresql+psycopg2://user:pass@host:port/db
host, port = "postgres", 5432
try:
    rest = url.split("@", 1)[1]
    hostport = rest.split("/", 1)[0]
    if ":" in hostport:
        host, port_s = hostport.rsplit(":", 1)
        port = int(port_s)
    else:
        host = hostport
except Exception:
    pass

for i in range(60):
    try:
        with socket.create_connection((host, port), timeout=2):
            print(f"postgres ready at {host}:{port}")
            break
    except OSError:
        time.sleep(1)
else:
    raise SystemExit(f"postgres not reachable: {host}:{port}")
PY

echo "running migrations..."
alembic upgrade head

echo "starting api..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
