# syntax=docker/dockerfile:1

# ── Stage 1: build the Rust CFR engine (_cote_cfr) ──
# Pinned by digest so a moving `python:3.11-slim` tag no longer invalidates the
# whole cfr-builder stage on every deploy. Bump deliberately when needed.
FROM python:3.11-slim@sha256:0dd364ba7e10242f07755449e3a3d0e35f9efd987952737b90def6709ab0c5ce AS cfr-builder

# Optional network overrides (defaults = upstream). For a locked-down/local build:
#   --build-arg DEBIAN_MIRROR=mirror.yandex.ru
#   --build-arg RUSTUP_DIST_SERVER=https://rsproxy.cn
#   --build-arg RUSTUP_UPDATE_ROOT=https://rsproxy.cn/rustup
#   --build-arg CARGO_MIRROR=sparse+https://rsproxy.cn/index/
#   --build-arg PIP_INDEX_URL=https://pypi.org/simple
ARG DEBIAN_MIRROR=""
ARG RUSTUP_DIST_SERVER="https://static.rust-lang.org"
ARG RUSTUP_UPDATE_ROOT="https://static.rust-lang.org/rustup"
ARG CARGO_MIRROR=""
ARG PIP_INDEX_URL=""

# apt over HTTPS: some networks throttle/reset large plain-HTTP transfers, which
# stalls `apt-get update` on the ~10MB Packages index. HTTPS is unaffected.
# Cache mount keeps the index/archives across builds; ForceIPv4 avoids Docker
# Desktop IPv6 stalls. DEBIAN_MIRROR is an optional mirror override.
RUN --mount=type=cache,target=/var/lib/apt,sharing=locked \
    --mount=type=cache,target=/var/cache/apt,sharing=locked \
    set -e; \
    printf 'Acquire::ForceIPv4 "true";\nAcquire::Retries "5";\n' > /etc/apt/apt.conf.d/99net; \
    for f in /etc/apt/sources.list /etc/apt/sources.list.d/debian.sources; do \
        if [ -f "$f" ]; then \
            sed -i 's|http://deb.debian.org|https://deb.debian.org|g; s|http://security.debian.org|https://security.debian.org|g' "$f"; \
            if [ -n "$DEBIAN_MIRROR" ]; then \
                sed -i "s|deb.debian.org|$DEBIAN_MIRROR|g; s|security.debian.org|$DEBIAN_MIRROR|g" "$f"; \
            fi; \
        fi; \
    done; \
    apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates build-essential

# Toolchain lives in cache mounts, so it survives layer invalidation between builds.
RUN --mount=type=cache,target=/root/.rustup \
    --mount=type=cache,target=/root/.cargo \
    export RUSTUP_DIST_SERVER="$RUSTUP_DIST_SERVER" RUSTUP_UPDATE_ROOT="$RUSTUP_UPDATE_ROOT"; \
    curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
ENV PATH="/root/.cargo/bin:${PATH}"

RUN --mount=type=cache,target=/root/.cache/pip \
    pip install ${PIP_INDEX_URL:+-i "$PIP_INDEX_URL"} "maturin>=1.7,<2.0"

WORKDIR /build
COPY cote_cfr/ ./cote_cfr/
RUN --mount=type=cache,target=/root/.rustup \
    --mount=type=cache,target=/root/.cargo \
    --mount=type=cache,target=/build/cote_cfr/target \
    if [ -n "$CARGO_MIRROR" ]; then \
        printf '[source.crates-io]\nreplace-with = "mirror"\n[source.mirror]\nregistry = "%s"\n' "$CARGO_MIRROR" > /root/.cargo/config.toml; \
    fi; \
    cd cote_cfr && maturin build --release --out /wheels

# ── Stage 2: runtime ──
FROM python:3.11-slim@sha256:0dd364ba7e10242f07755449e3a3d0e35f9efd987952737b90def6709ab0c5ce

ARG PIP_INDEX_URL=""

WORKDIR /app

COPY requirements.txt .
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install ${PIP_INDEX_URL:+-i "$PIP_INDEX_URL"} -r requirements.txt

COPY --from=cfr-builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

COPY . .

RUN chmod +x entrypoint.sh

CMD ["./entrypoint.sh"]
