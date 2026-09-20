# Fire-spread service: ELMFIRE (pinned) + FastAPI pipeline.
FROM ubuntu:24.04
ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update -y && apt-get install --no-install-recommends -y \
        bc build-essential ca-certificates csvkit gdal-bin gfortran git jq \
        libgdal-dev libopenmpi-dev openmpi-bin pigz python3 python3-pip \
        unzip wget zip && \
    rm -rf /var/lib/apt/lists/*

# --- ELMFIRE (pinned) --------------------------------------------------------
# Pinned to a main-branch commit: the last tag (2025.0717) predates barriers, GAUSSIAN
# perturbations, the UMD spotting model and the percent-unit fuel-moisture perturbation
# that the pipeline relies on (docs call this line "2025.1002").
ARG ELMFIRE_VER=cbf924a7bce2023105ab498fc255a8925e410646
# Upstream bug (still on main): C is a pointer into the burned-cell linked list and is
# uninitialised on the first call, so `IF (ASSOCIATED(C)) DEALLOCATE(C)` aborts with
# "free(): invalid pointer" under glibc 2.39 / gfortran 13. The intent is to hand a null
# node to SURFACE_SPREAD_RATE, which NULLIFY does.
RUN git clone --filter=blob:none https://github.com/lautenberger/elmfire /opt/elmfire && \
    git -C /opt/elmfire checkout --quiet ${ELMFIRE_VER} && \
    sed -i 's/IF (ASSOCIATED(C)) DEALLOCATE(C)/NULLIFY(C)/' /opt/elmfire/build/source/elmfire_level_set.f90 && \
    grep -q 'NULLIFY(C)' /opt/elmfire/build/source/elmfire_level_set.f90 && \
    # Second upstream bug: the barrier raster is read by one rank and only its *header* is
    # broadcast (unlike the other rasters, it is never placed in MPI shared memory), so with
    # more than one rank CHECK_BARRIER_BREACH dereferences a null pointer (SIGSEGV).
    # Allocate on the other ranks and broadcast the data after the header.
    sed -i 's|^   IF (USE_BARRIERS) CALL MPI_BCAST_RASTER_HEADER(BARRIER_WIDTH, PARALLEL_IO_RANK(41), .FALSE.)$|   IF (USE_BARRIERS) THEN\n      CALL MPI_BCAST_RASTER_HEADER(BARRIER_WIDTH, PARALLEL_IO_RANK(41), .FALSE.)\n      IF (.NOT. ASSOCIATED(BARRIER_WIDTH%R4)) ALLOCATE(BARRIER_WIDTH%R4(1:BARRIER_WIDTH%NCOLS,1:BARRIER_WIDTH%NROWS,1:1))\n      CALL MPI_BCAST(BARRIER_WIDTH%R4, BARRIER_WIDTH%NCOLS*BARRIER_WIDTH%NROWS, MPI_REAL, PARALLEL_IO_RANK(41), MPI_COMM_WORLD, IERR)\n   ENDIF|' /opt/elmfire/build/source/elmfire_io.f90 && \
    grep -q 'MPI_BCAST(BARRIER_WIDTH%R4' /opt/elmfire/build/source/elmfire_io.f90 && \
    cd /opt/elmfire/build/linux && ./make_gnu.sh && \
    rm -rf /opt/elmfire/.git
ENV ELMFIRE_VER=${ELMFIRE_VER} \
    ELMFIRE_BASE_DIR=/opt/elmfire \
    ELMFIRE_INSTALL_DIR=/opt/elmfire/build/linux/bin \
    PATH=/opt/elmfire/build/linux/bin:$PATH

# --- Python -------------------------------------------------------------------
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /uvx /bin/
ENV UV_PYTHON_INSTALL_DIR=/opt/python UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv
RUN useradd -m -u 1000 fire 2>/dev/null || useradd -m fire
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv python install 3.12 && uv sync --frozen --no-dev --python 3.12 && chown -R fire:fire /opt/venv
COPY --chown=fire:fire . .
RUN mkdir -p /app/data && chown -R fire:fire /app
ENV PATH=/opt/venv/bin:$PATH \
    DATA_DIR=/app/data/catalonia \
    RUNS_DIR=/app/data/runs \
    ELMFIRE_NPROC=4
USER fire
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
