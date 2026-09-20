#!/bin/bash
# Hindcast several settings back to back; log to data/hindcast/batch.log. Run detached:
#   docker run -d --name hindcast --shm-size=2g -v "$PWD:/app" -v fs-venv:/opt/venv2 -e DATA_DIR=/app/data/catalonia \
#       fireprotector/fire-spread bash scripts/hindcast_batch.sh "--fuels mediterranean" "--fuels mediterranean --spotting"
cd /app
export PYTHONPATH=/app
mkdir -p data/hindcast
[ -f data/catalonia/agri.tif ] || /opt/venv2/bin/python scripts/prepare_static_data.py --steps agri >> data/hindcast/batch.log 2>&1
{
  for args in "$@"; do
    echo "== $args $(date -u +%FT%TZ)"
    /opt/venv2/bin/python scripts/hindcast.py --min-ha 100 --members 4 $args 2>&1 | grep --line-buffered -v 'Warn\|HTTP Request\|being appended'
  done
  echo "== done $(date -u +%FT%TZ)"
} >> data/hindcast/batch.log 2>&1
