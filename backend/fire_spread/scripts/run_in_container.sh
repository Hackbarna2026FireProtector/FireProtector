#!/bin/bash
# container helper (run as root): sync venv into a persistent volume, then run a command as `fire`:
#   docker run --rm --shm-size=2g -v "$PWD:/app" -v fs-venv:/opt/venv2 --user root IMAGE bash scripts/run_in_container.sh pytest -m elmfire
#   ... bash scripts/run_in_container.sh fire_spread.cli --lat 41.59 --lon 1.83 --synthetic --constant-wind 9 270
set -e
cd /app
export UV_PROJECT_ENVIRONMENT=/opt/venv2
[ -x /opt/venv2/bin/python ] || { uv sync --frozen --python 3.12 -q; chown -R fire /opt/venv2; }
cmd="$1"; shift
exec su fire -c "cd /app; PATH=$PATH PYTHONPATH=/app /opt/venv2/bin/python -m $cmd $*"
