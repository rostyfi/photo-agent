FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

# Install build dependencies for pillow-heif, SQLite compilation, and sqlite-vec
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        libheif-dev \
        gcc \
        g++ \
        make \
        wget \
        autoconf \
        libtool \
        python3-dev \
    && rm -rf /var/lib/apt/lists/*

# Download and compile SQLite with extension loading support
RUN wget https://www.sqlite.org/2024/sqlite-autoconf-3450100.tar.gz \
    && tar -xzf sqlite-autoconf-3450100.tar.gz \
    && cd sqlite-autoconf-3450100 \
    && ./configure --enable-load-extension \
    && make \
    && make install \
    && cd .. \
    && rm -rf sqlite-autoconf-3450100 sqlite-autoconf-3450100.tar.gz

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

COPY requirements.txt .

# Install requirements (sqlite-vec is a HARD REQUIREMENT for vector search)
# Note: We use the system sqlite3 module which will link against our custom-compiled
# SQLite with extension loading support. We do NOT use pysqlite3-binary as it doesn't
# support extension loading which is required by sqlite-vec.
# sqlite-vec provides pre-built manylinux wheels for x86_64, so we can install directly
RUN uv pip install --system --no-cache -r requirements.txt

# Final stage
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
# Configurable application port (override with: --build-arg DASH_PORT=<port>)
ARG DASH_PORT=8050
ENV LOCAL_PHOTO_AGENT_DASH_HOST=0.0.0.0
ENV LOCAL_PHOTO_AGENT_DASH_PORT=${DASH_PORT}

WORKDIR /app

# Install runtime dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        curl \
        libheif1 \
        libgomp1 \
        libblas3 \
        liblapack3 \
        libopenblas0 \
    && rm -rf /var/lib/apt/lists/*

# Copy SQLite with extension support from builder (replaces system SQLite)
COPY --from=builder /usr/local/bin/sqlite3 /usr/local/bin/sqlite3
COPY --from=builder /usr/local/lib/libsqlite3.so* /usr/local/lib/

# Copy Python packages from builder
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Ensure the system can find our custom SQLite libraries and system BLAS libraries
# On Debian, libblas.so.3 and other system libs are in /usr/lib/x86_64-linux-gnu
ENV LD_LIBRARY_PATH=/usr/local/lib:/usr/lib/x86_64-linux-gnu:/usr/lib:${LD_LIBRARY_PATH}

COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

COPY . .

EXPOSE ${DASH_PORT}

CMD ["/entrypoint.sh"]
