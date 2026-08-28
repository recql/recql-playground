# RecQL Playground Docker image: core + cli + all backends + generator/examples + menu UI
FROM python:3.12-slim-bookworm

RUN apt-get update && apt-get install -y --no-install-recommends \
      curl ca-certificates libgomp1 gcc g++ python3-dev \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy deps if available or install base python requirements
COPY pyproject.toml README.md ./
COPY examples ./examples
COPY docker/app ./docker/app

# Install dependencies
RUN pip install --no-cache-dir -U pip setuptools wheel \
 && pip install --no-cache-dir \
      asyncpg oracledb pymysql motor pymongo pymssql lightgbm sentence-transformers pyyaml msgspec \
 && pip install --no-cache-dir -e . --no-deps

# Sibling checkouts can be mounted at runtime into /deps
ENV PYTHONPATH=/app:/deps/core:/deps/cli:/deps/postgres:/deps/oracle:/deps/mariadb:/deps/mongodb:/deps/mssql \
    PYTHONUNBUFFERED=1 \
    RECQL_SEED=1 \
    RECQL_IN_CONTAINER=1

RUN chmod +x /app/docker/app/entrypoint.sh

ENTRYPOINT ["/app/docker/app/entrypoint.sh"]
CMD []
