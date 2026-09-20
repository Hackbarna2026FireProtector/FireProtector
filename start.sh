#!/usr/bin/env bash
#
# The whole stack from one terminal: Postgres and the API in Docker, the UI in
# front of them, both halves' logs here.
#
#   ./start.sh                  everything up; loads the register on a first run
#   ./start.sh --prod           production build of the UI instead of the dev server
#   ./start.sh --setup          run the loader even when the register is already there
#   ./start.sh --setup -- --limit 10 --no-forests
#                               ... with everything after -- passed to setup_db.sh
#   ./start.sh --fire-data      build the fire-spread static tier even when it is there
#   ./start.sh --fire-data -- --res 30
#                               ... with everything after -- passed to setup_fire_data.sh
#   ./start.sh --no-fire-data   leave the tier alone and do not ask about it
#   ./start.sh --no-migrate     skip re-applying db/init/*.sql (~15 s faster)
#   ./start.sh --no-api-logs    leave the API container's log out of this terminal
#   ./start.sh --down           stop the containers when this script exits
#
# In order: check the tools, start Postgres, load both datasets if the database
# is empty (about 11 minutes, once), bring the API up on 5102, offer to build the
# fire-spread static tier if it is missing, then serve the UI on 5173 and stay in
# the foreground.
#
# Ctrl-C stops the UI. The containers are `restart: unless-stopped` and stay up,
# so the next start takes seconds -- pass --down to stop them too.
#
# Loading the data is backend/scripts/setup_db.sh's job and building the
# fire-spread tier is backend/scripts/setup_fire_data.sh's; both stay there. This
# script decides whether they need to run and adds the frontend half.

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
COMPOSE=(docker compose -f "$BACKEND_DIR/docker-compose.yml")
SETUP_DB="$BACKEND_DIR/scripts/setup_db.sh"
SETUP_FIRE_DATA="$BACKEND_DIR/scripts/setup_fire_data.sh"
# backend/data is bind-mounted into the API at /srv/data, and compose pins
# DATA_DIR under it, so the tier can be checked from the host with no container
# running. dem.tif is what the API itself tests for (fire_spread/router.py).
FIRE_TIER="$BACKEND_DIR/data/fire_spread/catalonia/dem.tif"

PG_USER="${POSTGRES_USER:-fireprotector}"
PG_DB="${POSTGRES_DB:-fireprotector}"
API_PORT="${API_PORT:-5102}"
UI_PORT=5173   # fixed in frontend/vite.config.ts; Vite picks the next free one if taken

# ---------------------------------------------------------------- helpers ---

info()  { printf '\033[1;34m==>\033[0m %s\n' "$*"; }
warn()  { printf '\033[1;33m warn\033[0m %s\n' "$*" >&2; }
die()   { printf '\033[1;31merror\033[0m %s\n' "$*" >&2; exit 1; }

psql_run() {
    "${COMPOSE[@]}" exec -T -e PGOPTIONS="-c client_min_messages=warning" db \
        psql -v ON_ERROR_STOP=1 -U "$PG_USER" -d "$PG_DB" -qtA "$@"
}

# Docker reports health per container; both have a healthcheck in compose.
wait_for_health() {
    local container="$1" label="$2" tries="${3:-60}" status=starting
    printf '    waiting for %s' "$label"
    for _ in $(seq 1 "$tries"); do
        status=$(docker inspect --format '{{.State.Health.Status}}' "$container" 2>/dev/null || echo starting)
        [[ "$status" == "healthy" ]] && break
        printf '.'; sleep 2
    done
    if [[ "$status" == "healthy" ]]; then echo " ok"; return 0; fi
    echo; return 1
}

port_in_use() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

# Only the loader needs Python on the host: it parses the GML with lxml and
# shapely, which want a newer one than the `python3` first on PATH often is --
# an Anaconda or system python3 is the usual culprit. setup_db.sh builds its
# virtualenv from whatever it finds, so without this the failure lands halfway
# through building that virtualenv, with a pip resolver error to read.
check_loader_python() {
    local venv="$BACKEND_DIR/scripts/.venv" candidate
    command -v python3 >/dev/null || die "python3 is not installed; the loader needs Python 3.11+."

    # A half-built virtualenv is worse than none: setup_db.sh sees the
    # interpreter, skips rebuilding, and every municipality then fails to parse.
    if [[ -x "$venv/bin/python" ]] && ! "$venv/bin/python" -c 'import lxml, shapely' 2>/dev/null; then
        warn "scripts/.venv cannot import lxml/shapely -- an earlier run left it half-built."
        warn "Delete it so it is rebuilt:  rm -rf $venv"
    fi

    python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' && return 0

    warn "python3 is $(python3 -V 2>&1 | cut -d" " -f2) at $(command -v python3), too old for the"
    warn "loader's lxml and shapely. The README asks for Python 3.11+."
    for candidate in python3.13 python3.12 python3.11; do
        if command -v "$candidate" >/dev/null; then
            warn "A newer one is installed. Re-run with it first on PATH:"
            warn "    PATH=\"$(dirname "$(command -v "$candidate")")\":\$PATH ./start.sh"
            break
        fi
    done
    die "the data loader cannot run with this python3."
}

# --------------------------------------------------------------- options ----

PROD=0
FORCE_SETUP=0
FIRE_DATA=ask   # ask | force | skip
MIGRATE=1
API_LOGS=1
DOWN_ON_EXIT=0
PASS_ARGS=()
while [[ $# -gt 0 ]]; do
    case "$1" in
        --prod)          PROD=1; shift ;;
        --setup)         FORCE_SETUP=1; shift ;;
        --fire-data)     FIRE_DATA=force; shift ;;
        --no-fire-data)  FIRE_DATA=skip; shift ;;
        --no-migrate)    MIGRATE=0; shift ;;
        --no-api-logs)   API_LOGS=0; shift ;;
        --down)          DOWN_ON_EXIT=1; shift ;;
        --)              shift; PASS_ARGS=("$@"); break ;;
        -h|--help)
            # The header block above, minus the shebang: one place to keep the
            # usage, rather than a line range that drifts when it is edited.
            awk 'NR == 1 { next } /^#/ { sub(/^# ?/, ""); print; next } { exit }' "${BASH_SOURCE[0]}"
            exit 0 ;;
        *) die "unknown option: $1 (try --help)" ;;
    esac
done

# Everything after -- belongs to one of the two long jobs, named by the flag that
# asked for it. Both at once has no unambiguous reading, so it is refused rather
# than guessed at.
SETUP_ARGS=()
FIRE_ARGS=()
if [[ "$FIRE_DATA" == "force" && "$FORCE_SETUP" == "1" && ${#PASS_ARGS[@]} -gt 0 ]]; then
    die "arguments after -- go to one job, but both --setup and --fire-data were given. Run them separately."
elif [[ "$FIRE_DATA" == "force" ]]; then
    FIRE_ARGS=("${PASS_ARGS[@]+"${PASS_ARGS[@]}"}")
else
    SETUP_ARGS=("${PASS_ARGS[@]+"${PASS_ARGS[@]}"}")
    # Arguments for the loader are only read when the loader runs.
    if [[ ${#SETUP_ARGS[@]} -gt 0 && "$FORCE_SETUP" == "0" ]]; then
        warn "arguments after -- are passed to setup_db.sh, which only runs on a first"
        warn "load or with --setup. They will be ignored if the data is already there."
        warn "For the fire-spread tier they need --fire-data."
    fi
fi

# --------------------------------------------------------------- shutdown ---

LOGS_PID=""
BACKEND_UP=0
UI_STARTED=0

cleanup() {
    local code=$?
    trap - EXIT INT TERM

    if [[ -n "$LOGS_PID" ]]; then
        kill "$LOGS_PID" 2>/dev/null || true
        wait "$LOGS_PID" 2>/dev/null || true
    fi

    if [[ "$BACKEND_UP" == "1" && "$DOWN_ON_EXIT" == "1" ]]; then
        printf '\n'
        info "Stopping the containers (--down)"
        "${COMPOSE[@]}" down
    elif [[ "$UI_STARTED" == "1" ]]; then
        printf '\n'
        info "The UI is stopped. Postgres and the API are still running:"
        printf '    %s logs -f api\n' "docker compose -f backend/docker-compose.yml"
        printf '    %s down\n' "docker compose -f backend/docker-compose.yml"
    fi
    exit "$code"
}
trap cleanup EXIT INT TERM

# -------------------------------------------------------------- preflight ---

info "Checking prerequisites"
command -v docker >/dev/null || die "docker is not installed."
docker info >/dev/null 2>&1 || die "the Docker daemon is not running -- start Docker Desktop and re-run."
command -v node >/dev/null   || die "node is not installed; the UI needs Node 20+."
command -v npm >/dev/null    || die "npm is not installed; the UI needs Node 20+."
[[ -x "$SETUP_DB" ]] || die "missing $SETUP_DB"
[[ -x "$SETUP_FIRE_DATA" ]] || die "missing $SETUP_FIRE_DATA"
[[ -f "$FRONTEND_DIR/package.json" ]] || die "missing $FRONTEND_DIR/package.json"

NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
[[ "$NODE_MAJOR" -ge 20 ]] || die "Node $(node -v) is too old; the UI needs Node 20+."

[[ -f "$BACKEND_DIR/.env" ]] || \
    info "No backend/.env -- the app runs off the recorded bundles in backend/data/bundles/."

# The UI proxies to 5102 because the asset-register contract fixes that port.
# API_PORT moves the published port, so the proxy has to be told.
if [[ "$API_PORT" != "5102" && -z "${BACKEND_URL:-}" ]]; then
    export BACKEND_URL="http://localhost:$API_PORT"
    info "API_PORT=$API_PORT, so the UI proxies to $BACKEND_URL"
fi

# --------------------------------------------------------------- backend ----

NEEDS_SETUP="$FORCE_SETUP"

if [[ "$NEEDS_SETUP" == "0" ]]; then
    info "Starting Postgres on port ${POSTGRES_PORT:-5432}"
    "${COMPOSE[@]}" up -d db
    wait_for_health fireprotector-db "the database" \
        || die "the database did not become healthy; see: ${COMPOSE[*]} logs db"

    # An empty load_log means nothing has been loaded yet -- as does a missing
    # table, on a volume that has never had the schema applied.
    LOADED="$(psql_run -c 'SELECT count(*) FROM protection.load_log' 2>/dev/null | tail -1 || true)"
    [[ "$LOADED" =~ ^[0-9]+$ ]] || LOADED=0

    if [[ "$LOADED" -eq 0 ]]; then
        info "The database is empty -- running the first-time load. This takes about"
        info "11 minutes for 4.27M assets; it is resumable, so a re-run picks up where"
        info "it stopped."
        NEEDS_SETUP=1
    else
        info "$LOADED municipalities already loaded"
    fi
fi

if [[ "$NEEDS_SETUP" == "1" ]]; then
    check_loader_python
    # setup_db.sh does the rest itself: schema, both datasets, then the API.
    "$SETUP_DB" "${SETUP_ARGS[@]+"${SETUP_ARGS[@]}"}" \
        || die "setup_db.sh failed -- see the error above. It is resumable: fix that and re-run."
    BACKEND_UP=1
else
    if [[ "$MIGRATE" == "1" ]]; then
        # Idempotent, and how an existing volume picks up a schema change that
        # arrived with a git pull -- the container only runs db/init on first
        # boot. Costs ~15 s; --no-migrate skips it.
        info "Applying schema (db/init/*.sql)"
        for schema_file in "$BACKEND_DIR"/db/init/*.sql; do
            psql_run -f - < "$schema_file" >/dev/null
        done
    fi

    info "Building and starting the API on port $API_PORT"
    "${COMPOSE[@]}" up -d --build api
    BACKEND_UP=1
    wait_for_health fireprotector-api "the API" \
        || warn "the API is not healthy yet; check: ${COMPOSE[*]} logs api"
fi

# ------------------------------------------------------- fire-spread tier ---
#
# The Catalonia-wide rasters GET /fire/arrival-grid simulates on. Genuinely
# optional -- without them that one route answers 503 and the recorded bundles
# still drive the whole UI -- but 3 GB and 10-30 minutes is not something to
# start behind someone's back, so a normal run asks. It comes after the backend
# block because setup_fire_data.sh runs inside the API image, which is built
# there.

build_fire_tier() {
    info "Building the fire-spread static tier (~3 GB, 10-30 minutes, once)"
    "$SETUP_FIRE_DATA" "${FIRE_ARGS[@]+"${FIRE_ARGS[@]}"}" \
        || die "setup_fire_data.sh failed -- see the error above. It is re-runnable: downloads already on disk are reused."
    # The route tests for the tier per request, so this only brings the startup
    # log and /health into step with what is now on disk.
    info "Restarting the API so it picks the tier up"
    "${COMPOSE[@]}" up -d api
    wait_for_health fireprotector-api "the API" \
        || warn "the API is not healthy yet; check: ${COMPOSE[*]} logs api"
}

if [[ "$FIRE_DATA" == "force" ]]; then
    build_fire_tier
elif [[ -f "$FIRE_TIER" ]]; then
    info "Fire-spread static tier is present -- new ignitions can be simulated"
elif [[ "$FIRE_DATA" == "skip" ]]; then
    warn "no fire-spread static tier (--no-fire-data): GET /fire/arrival-grid"
    warn "answers 503. The recorded scenarios still work."
elif [[ -t 0 ]]; then
    # Interactive only: piped into a shell or run from CI this would hang, so
    # that case falls through to the warning below.
    info "No fire-spread static tier."
    printf '    GET /fire/arrival-grid answers 503 until it is built (~3 GB,\n'
    printf '    10-30 minutes, once). The recorded scenarios work either way.\n\n'
    FIRE_REPLY=""
    read -r -p "    Build it now? [y/N] " FIRE_REPLY || FIRE_REPLY=""
    printf '\n'
    if [[ "$FIRE_REPLY" =~ ^[Yy]$ ]]; then
        build_fire_tier
    else
        info "Skipped -- build it later with ./start.sh --fire-data"
    fi
else
    warn "no fire-spread static tier: new ignitions cannot be simulated and"
    warn "GET /fire/arrival-grid answers 503. The recorded scenarios still work."
    warn "Build it once with ./start.sh --fire-data (~3 GB, 10-30 min)."
fi

# -------------------------------------------------------------- frontend ----

cd "$FRONTEND_DIR"

# npm writes node_modules/.package-lock.json on every install, so comparing it
# against the lockfile catches a dependency change without reinstalling blindly.
if [[ ! -d node_modules ]]; then
    info "Installing UI dependencies"
    if [[ -f package-lock.json ]]; then npm ci; else npm install; fi
elif [[ package-lock.json -nt node_modules/.package-lock.json ]]; then
    info "package-lock.json is newer than the last install -- updating"
    npm install
else
    info "UI dependencies are up to date"
fi

if [[ "$API_LOGS" == "1" ]]; then
    # Only the lines from here on, dimmed and tagged, so the API's log and
    # Vite's share this terminal legibly. The docker CLI is the job we kill on
    # the way out; the tagger exits when its pipe closes.
    "${COMPOSE[@]}" logs -f --tail=0 api \
        > >(while IFS= read -r line; do printf '\033[2m[api]\033[0m %s\n' "$line"; done) 2>&1 &
    LOGS_PID=$!
fi

# Printed once the UI is about to serve, so the URLs are not on screen while a
# production build is still running.
banner() {
    if port_in_use "$UI_PORT"; then
        warn "port $UI_PORT is already in use; Vite will serve on the next free port it prints below."
    fi
    cat <<EOF

  UI        http://localhost:$UI_PORT
  API docs  http://localhost:$API_PORT/docs
  Scenarios http://localhost:$API_PORT/api/scenarios

  A scenario with no recorded bundle simulates live, which takes two to four
  minutes on first view. Ctrl-C stops the UI.

EOF
}

if [[ "$PROD" == "1" ]]; then
    info "Building the UI (typecheck + production build)"
    npm run build
    banner
    info "Serving the production build on $UI_PORT"
    UI_STARTED=1
    npm run preview || true
else
    banner
    info "Starting the Vite dev server on $UI_PORT"
    UI_STARTED=1
    npm run dev || true
fi
