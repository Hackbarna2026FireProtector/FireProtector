#!/usr/bin/env bash
#
# One-time setup for the FireProtector database.
#
#   scripts/setup_db.sh                     load everything still missing
#   scripts/setup_db.sh --limit 10          load only the 10 smallest pending
#   scripts/setup_db.sh --only solsona,olot load named municipalities
#   scripts/setup_db.sh --workers 8         parallelism (default 4)
#   scripts/setup_db.sh --reset             wipe the volume and start over
#
# Brings up a Postgres container, creates the `protection` schema, then loads
# the INSPIRE building register for Catalonia into protection.building_specs
# using extract_buildings.py.
#
# Safe to re-run: municipalities already loaded are skipped, so an interrupted
# run resumes where it stopped, and a finished one just starts the container.
#
# Each municipality is streamed straight from the open-data portal into the
# parser, so the 12 GB of source GML never lands on disk -- only one small CSV
# per municipality, deleted as soon as it is loaded.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE=(docker compose -f "$REPO_ROOT/docker-compose.yml")

BASE_URL="https://datacloud.ide.cat/geodades/inspire-edificis"
SLUG_MAP="$REPO_ROOT/municipality_slug_map.csv"
EXTRACTOR="$REPO_ROOT/extract_buildings.py"
IMPORT_DIR="$REPO_ROOT/db/import"
VENV="$REPO_ROOT/scripts/.venv"
PYTHON="$VENV/bin/python"
# Shared with the parallel workers via the environment; $$ only on first entry.
STATE_DIR="${STATE_DIR:-${TMPDIR:-/tmp}/fireprotector-load.$$}"

PG_USER="${POSTGRES_USER:-fireprotector}"
PG_DB="${POSTGRES_DB:-fireprotector}"
WORKERS="${WORKERS:-4}"

# ---------------------------------------------------------------- helpers ---

info()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m warn\033[0m %s\n' "$*" >&2; }
die()   { printf '\033[1;31merror\033[0m %s\n' "$*" >&2; exit 1; }

psql_run() {
    "${COMPOSE[@]}" exec -T -e PGOPTIONS="-c client_min_messages=warning" db \
        psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$PG_DB" -qtA "$@"
}

# ------------------------------------------------------ one municipality ----
# Invoked by xargs as a subprocess, one per municipality.

load_one() {
    local slug="$1" bytes="$2"
    local csv="$IMPORT_DIR/$slug.csv"

    # The slug reaches us from a remote directory listing and is interpolated
    # into SQL below, so accept only the shape real slugs have.
    if [[ ! "$slug" =~ ^[a-z0-9-]+$ ]]; then
        warn "skipping suspicious slug: $slug"
        echo "$slug" >> "$STATE_DIR/failed"
        return 0
    fi

    if ! curl -fsS --retry 3 --retry-delay 2 --max-time 3600 \
              "$BASE_URL/inspire-edificis-$slug-etrs89-geo.gml" \
         | "$PYTHON" "$EXTRACTOR" /dev/stdin > "$csv" 2> "$STATE_DIR/$slug.err"
    then
        warn "$slug: download or parse failed -- $(tail -1 "$STATE_DIR/$slug.err" 2>/dev/null)"
        rm -f "$csv"
        echo "$slug" >> "$STATE_DIR/failed"
        return 0
    fi
    rm -f "$STATE_DIR/$slug.err"
    chmod 644 "$csv"

    # Staging table + insert + bookkeeping in one transaction, so a municipality
    # is either fully loaded and logged, or not logged at all.
    local rows
    if ! rows=$(psql_run <<SQL
BEGIN;
CREATE TEMP TABLE stage (
    building        text,
    building_type   text,
    latitude        double precision,
    longitude       double precision,
    municipality_id text
) ON COMMIT DROP;
COPY stage FROM '/import/$slug.csv' WITH (FORMAT csv, HEADER true);
INSERT INTO protection.building_specs
    (building, building_type, latitude, longitude, municipality_id)
SELECT building, building_type, latitude, longitude, municipality_id FROM stage
ON CONFLICT (building) DO NOTHING;
INSERT INTO protection.load_log (slug, n_rows, gml_bytes)
VALUES ('$slug', (SELECT count(*) FROM stage), $bytes)
ON CONFLICT (slug) DO UPDATE
    SET n_rows = EXCLUDED.n_rows, gml_bytes = EXCLUDED.gml_bytes, loaded_at = now();
COMMIT;
SELECT n_rows FROM protection.load_log WHERE slug = '$slug';
SQL
    ); then
        warn "$slug: load failed"
        rm -f "$csv"
        echo "$slug" >> "$STATE_DIR/failed"
        return 0
    fi

    rm -f "$csv"

    # mkdir is atomic, so workers take turns and the counter never repeats.
    local n
    while ! mkdir "$STATE_DIR/lock" 2>/dev/null; do sleep 0.02; done
    n=$(( $(cat "$STATE_DIR/count" 2>/dev/null || echo 0) + 1 ))
    echo "$n" > "$STATE_DIR/count"
    rmdir "$STATE_DIR/lock"
    printf '[%4d/%4d] %-34s %9s buildings\n' "$n" "${TOTAL:-0}" "$slug" "$(echo "$rows" | tail -1)"
}

# Re-entry point for the parallel workers.
if [[ "${1:-}" == "--load-one" ]]; then
    load_one "$2" "$3"
    exit 0
fi

# --------------------------------------------------------------- options ----

RESET=0
LIMIT=0
ONLY=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --workers) WORKERS="$2"; shift 2 ;;
        --limit)   LIMIT="$2"; shift 2 ;;
        --only)    ONLY="$2"; shift 2 ;;
        --reset)   RESET=1; shift ;;
        -h|--help)
            sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
            exit 0 ;;
        *) die "unknown option: $1 (try --help)" ;;
    esac
done

# -------------------------------------------------------------- preflight ---

info "Checking prerequisites"
command -v docker >/dev/null || die "docker is not installed."
docker info >/dev/null 2>&1 || die "the Docker daemon is not running -- start Docker Desktop and re-run."
command -v curl >/dev/null   || die "curl is not installed."
command -v python3 >/dev/null || die "python3 is not installed."
[[ -f "$EXTRACTOR" ]] || die "missing $EXTRACTOR"
[[ -f "$SLUG_MAP" ]]  || die "missing $SLUG_MAP (extract_buildings.py needs it beside itself)"

if [[ ! -x "$PYTHON" ]]; then
    info "Creating loader virtualenv at scripts/.venv"
    python3 -m venv "$VENV"
    "$VENV/bin/pip" install --quiet --upgrade pip
    "$VENV/bin/pip" install --quiet -r "$REPO_ROOT/scripts/requirements.txt"
fi

mkdir -p "$IMPORT_DIR" "$STATE_DIR"
trap 'rm -rf "$STATE_DIR"' EXIT

# A full load needs roughly 2.5 GB for the database plus WAL and checkpoint
# headroom. The GML itself is streamed and never stored.
FREE_GB=$(df -g "$REPO_ROOT" | awk 'NR==2 {print $4}')
if [[ "${FREE_GB:-99}" -lt 5 ]]; then
    warn "only ${FREE_GB} GB free on this disk; a full load needs about 5 GB of headroom."
    warn "Use --limit/--only to load a subset, or free some space first."
    read -r -p "Continue anyway? [y/N] " reply
    [[ "$reply" == "y" || "$reply" == "Y" ]] || die "aborted."
fi

# ------------------------------------------------------------- container ----

if [[ "$RESET" == "1" ]]; then
    warn "--reset deletes the database volume and every row in it."
    read -r -p "Type 'reset' to confirm: " reply
    [[ "$reply" == "reset" ]] || die "aborted."
    "${COMPOSE[@]}" down -v
fi

info "Starting Postgres (${POSTGRES_PORT:-5432})"
"${COMPOSE[@]}" up -d db

printf '    waiting for health'
for _ in $(seq 1 60); do
    status=$(docker inspect --format '{{.State.Health.Status}}' fireprotector-db 2>/dev/null || echo starting)
    [[ "$status" == "healthy" ]] && break
    printf '.'; sleep 2
done
[[ "${status:-}" == "healthy" ]] || { echo; die "database did not become healthy; see: ${COMPOSE[*]} logs db"; }
echo " ok"

# Idempotent, so this also upgrades a volume created before a schema change.
info "Applying schema (protection.building_specs)"
psql_run -f - < "$REPO_ROOT/db/init/01_schema.sql" >/dev/null

# ------------------------------------------------------------- work list ----

info "Fetching the municipality list from datacloud.ide.cat"
curl -fsS --retry 3 --max-time 120 "$BASE_URL/" > "$STATE_DIR/listing.html" \
    || die "could not reach $BASE_URL"

psql_run -c "SELECT slug FROM protection.load_log" > "$STATE_DIR/loaded.txt"

python3 - "$STATE_DIR/listing.html" "$SLUG_MAP" "$STATE_DIR/loaded.txt" "$ONLY" "$LIMIT" \
    > "$STATE_DIR/work.txt" <<'PY'
import csv, re, sys

listing, slug_map, loaded_file, only, limit = sys.argv[1:6]

html = open(listing, encoding="utf-8", errors="replace").read()
# Rows look like:  <bytes> <A HREF=".../inspire-edificis-<slug>-etrs89-geo.gml">
sizes = {
    slug: int(size)
    for size, slug in re.findall(
        r'>\s*(\d+)\s*<A HREF="[^"]*?/inspire-edificis-([^"/]+?)-etrs89-geo\.gml"', html
    )
}

# extract_buildings.py looks the municipality's INE code up by slug, so a slug
# missing from the map would crash it. Skip those instead.
known = {r["slug"] for r in csv.DictReader(open(slug_map, encoding="utf-8"))}
loaded = {line.strip() for line in open(loaded_file) if line.strip()}

pending = sorted(set(sizes) & known - loaded, key=lambda s: sizes[s])

if only:
    wanted = {s.strip() for s in only.split(",") if s.strip()}
    unmatched = wanted - set(sizes)
    if unmatched:
        print(f"note: --only named unknown slug(s): {', '.join(sorted(unmatched))}",
              file=sys.stderr)
    pending = [s for s in pending if s in wanted]
if limit and int(limit) > 0:
    pending = pending[: int(limit)]

for slug in pending:
    print(slug, sizes[slug])

unknown = sorted(set(sizes) - known)
if unknown:
    print(f"note: {len(unknown)} file(s) have no entry in the slug map and were "
          f"skipped: {', '.join(unknown[:5])}", file=sys.stderr)
PY

TOTAL=$(wc -l < "$STATE_DIR/work.txt" | tr -d ' ')
ALREADY=$(wc -l < "$STATE_DIR/loaded.txt" | tr -d ' ')
export TOTAL STATE_DIR IMPORT_DIR PYTHON EXTRACTOR BASE_URL PG_USER PG_DB REPO_ROOT

if [[ "$TOTAL" -eq 0 ]]; then
    info "Nothing to load -- all $ALREADY municipalities are already in the database."
else
    info "Loading $TOTAL municipalities ($ALREADY already done), $WORKERS at a time"
    START=$(date +%s)
    # Smallest first, so progress is visible early and a failure surfaces fast.
    xargs -P "$WORKERS" -n 2 "$REPO_ROOT/scripts/setup_db.sh" --load-one < "$STATE_DIR/work.txt"
    info "Finished in $(( ($(date +%s) - START) / 60 ))m $(( ($(date +%s) - START) % 60 ))s"
fi

# --------------------------------------------------------------- summary ----

if [[ -f "$STATE_DIR/failed" ]]; then
    n_failed=$(wc -l < "$STATE_DIR/failed" | tr -d ' ')
    warn "$n_failed municipalities failed: $(paste -sd, - < "$STATE_DIR/failed" | cut -c1-200)"
    warn "Re-run this script to retry just those."
fi

info "Database summary"
psql_run -c "
SELECT 'buildings      ' || to_char(count(*), 'FM999,999,999') FROM protection.building_specs
UNION ALL
SELECT 'municipalities ' || to_char(count(*), 'FM999,999') FROM protection.load_log
UNION ALL
SELECT 'table size     ' || pg_size_pretty(pg_total_relation_size('protection.building_specs'))
UNION ALL
SELECT 'database size  ' || pg_size_pretty(pg_database_size(current_database()));
" | sed 's/^/    /'

cat <<EOF

Connection string for backend/.env:
    DATABASE_URL=postgresql://$PG_USER:${POSTGRES_PASSWORD:-fireprotector}@localhost:${POSTGRES_PORT:-5432}/$PG_DB
    BUILDING_SPECS_TABLE=protection.building_specs

Start the API:
    cd backend && .venv/bin/uvicorn app.main:app --reload
EOF
