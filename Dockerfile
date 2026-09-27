# ── Stage 1: build the Rust CFR engine (_cote_cfr) ──
FROM python:3.11-slim AS cfr-builder

RUN apt-get update && apt-get install -y --no-install-recommends \
        curl ca-certificates build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal
ENV PATH="/root/.cargo/bin:${PATH}"

RUN pip install --no-cache-dir "maturin>=1.7,<2.0"

WORKDIR /build
COPY cote_cfr/ ./cote_cfr/
RUN cd cote_cfr && maturin build --release --out /wheels

# ── Stage 2: runtime ──
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY --from=cfr-builder /wheels /wheels
RUN pip install --no-cache-dir /wheels/*.whl && rm -rf /wheels

COPY . .

RUN chmod +x entrypoint.sh

CMD ["./entrypoint.sh"]
