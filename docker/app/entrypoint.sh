#!/usr/bin/env bash
# RecQL container entrypoint: wait for DB → check seed status → Menu / CLI.
set -euo pipefail

BACKEND="${RECQL_BACKEND:-postgres}"
SEED="${RECQL_SEED:-auto}"
ENCODE="${RECQL_ENCODE:-st}"

# Install mounted deps if present
if [[ -d "/deps/core" ]]; then
  for pack in core cli postgres oracle mariadb mongodb mssql; do
    if [[ -f "/deps/${pack}/pyproject.toml" ]]; then
      rm -rf "/tmp/pack_${pack}"
      mkdir -p "/tmp/pack_${pack}"
      cp -a "/deps/${pack}"/. "/tmp/pack_${pack}"/ 2>/dev/null || true
      pip install -q --no-deps -e "/tmp/pack_${pack}" 2>/dev/null || true
    fi
  done
fi
if ! python -c "import aiomysql" >/dev/null 2>&1; then
  pip install -q aiomysql cryptography 2>/dev/null || true
fi
pip install -q --no-deps -e /app 2>/dev/null || true

case "$ENCODE" in
  st|sentence_transformers|hf|minilm)
    ENCODE_BACKEND=sentence_transformers
    if [[ -n "${RECQL_DIMS:-}" && "${RECQL_DIMS}" != "384" ]]; then
      echo "note: RECQL_ENCODE=st forces dims=384 (ignoring RECQL_DIMS=${RECQL_DIMS})" >&2
    fi
    DIMS=384
    ENGINE_SUFFIX=.st
    ;;
  fake|hash|"")
    ENCODE_BACKEND=fake
    DIMS="${RECQL_DIMS:-8}"
    ENGINE_SUFFIX=
    ;;
  *)
    echo "unknown RECQL_ENCODE=$ENCODE (use st|fake)" >&2
    exit 2
    ;;
esac

case "$BACKEND" in
  postgres|pg)
    BACKEND=postgres
    DATABASE="${RECQL_DATABASE:-${RECQL_PG_DSN:-postgres://recql:recql@postgres:5432/recql}}"
    ENGINE="/app/examples/generator/postgres/engine${ENGINE_SUFFIX}.yaml"
    CLI_BACKEND_ARGS=(--backend postgres)
    ;;
  oracle|ora|26ai)
    BACKEND=oracle
    DATABASE="${RECQL_DATABASE:-${RECQL_ORACLE_DSN:-oracle://recql:RecqlPass1@oracle:1521/FREEPDB1}}"
    ENGINE="/app/examples/generator/oracle/engine${ENGINE_SUFFIX}.yaml"
    CLI_BACKEND_ARGS=(--backend oracle)
    ;;
  mariadb|maria|mysql)
    BACKEND=mariadb
    DATABASE="${RECQL_DATABASE:-${RECQL_MARIADB_DSN:-mariadb://recql:recql@mariadb:3306/recql}}"
    ENGINE="/app/examples/generator/mariadb/engine${ENGINE_SUFFIX}.yaml"
    CLI_BACKEND_ARGS=(--backend mariadb)
    ;;
  mongodb|mongo)
    BACKEND=mongodb
    DATABASE="${RECQL_DATABASE:-${RECQL_MONGODB_DSN:-mongodb://mongodb:27017/recql?directConnection=true}}"
    ENGINE="/app/examples/generator/mongodb/engine${ENGINE_SUFFIX}.yaml"
    CLI_BACKEND_ARGS=(--backend mongodb)
    ;;
  mssql|sqlserver|tsql)
    BACKEND=mssql
    DATABASE="${RECQL_DATABASE:-${RECQL_MSSQL_DSN:-mssql://sa:RecqlTest1234!@mssql:1433/recql}}"
    ENGINE="/app/examples/generator/mssql/engine${ENGINE_SUFFIX}.yaml"
    CLI_BACKEND_ARGS=(--backend mssql)
    ;;
  federated|multi)
    BACKEND=federated
    DATABASE="${RECQL_DATABASE:-federated}"
    ENGINE="/app/examples/generator/federated/engine${ENGINE_SUFFIX}.yaml"
    CLI_BACKEND_ARGS=()
    ;;
  *)
    echo "unknown RECQL_BACKEND=$BACKEND (use postgres|oracle|mariadb|mongodb|mssql|federated)" >&2
    exit 2
    ;;
esac

if [[ -n "${RECQL_ENGINE:-}" && "${RECQL_ENGINE}" != "$ENGINE" ]]; then
  echo "note: ignoring RECQL_ENGINE=${RECQL_ENGINE} (using ${ENGINE} for encode=${ENCODE})" >&2
fi

wait_for_postgres() {
  python - <<'PY'
import asyncio, os, sys
dsn = os.environ.get("RECQL_PG_DSN") or "postgres://recql:recql@postgres:5432/recql"
if os.environ.get("RECQL_BACKEND") == "postgres":
    dsn = os.environ.get("RECQL_DATABASE") or dsn
async def main():
    import asyncpg
    for i in range(60):
        try:
            c = await asyncpg.connect(dsn, timeout=2)
            await c.close()
            print(f"postgres ready ({dsn.split('@')[-1]})", flush=True)
            return
        except Exception as e:
            print(f"waiting for postgres… ({i+1}/60) {e}", flush=True)
            await asyncio.sleep(2)
    sys.exit(1)
asyncio.run(main())
PY
}

wait_for_oracle() {
  python - <<'PY'
import asyncio, os, sys
dsn = os.environ.get("RECQL_ORACLE_DSN") or "oracle://recql:RecqlPass1@oracle:1521/FREEPDB1"
if os.environ.get("RECQL_BACKEND") == "oracle":
    dsn = os.environ.get("RECQL_DATABASE") or dsn
async def main():
    import oracledb
    from recql_oracle.connect import parse_oracle_dsn
    user, password, easy = parse_oracle_dsn(dsn)
    for i in range(90):
        try:
            conn = await oracledb.connect_async(user=user, password=password, dsn=easy)
            await conn.close()
            print(f"oracle ready ({easy})", flush=True)
            return
        except Exception as e:
            print(f"waiting for oracle… ({i+1}/90) {e}", flush=True)
            await asyncio.sleep(5)
    sys.exit(1)
asyncio.run(main())
PY
}

wait_for_mariadb() {
  python - <<'PY'
import asyncio, os, sys
dsn = os.environ.get("RECQL_MARIADB_DSN") or "mariadb://recql:recql@mariadb:3306/recql"
if os.environ.get("RECQL_BACKEND") == "mariadb":
    dsn = os.environ.get("RECQL_DATABASE") or dsn
async def main():
    try:
        from recql_mariadb.db import create_pool
        for i in range(60):
            try:
                pool = await create_pool(dsn, minsize=1, maxsize=1)
                async with pool.acquire() as conn:
                    async with conn.cursor() as cur:
                        await cur.execute("SELECT 1")
                pool.close()
                await pool.wait_closed()
                print(f"mariadb ready ({dsn.split('@')[-1]})", flush=True)
                return
            except Exception as e:
                print(f"waiting for mariadb… ({i+1}/60) {e}", flush=True)
                await asyncio.sleep(2)
    except ImportError:
        import pymysql
        from urllib.parse import urlparse
        u = urlparse(dsn.replace("mariadb://", "mysql://"))
        for i in range(60):
            try:
                conn = pymysql.connect(
                    host=u.hostname or "127.0.0.1",
                    port=u.port or 3306,
                    user=u.username or "recql",
                    password=u.password or "recql",
                    database=u.path.lstrip("/") or "recql",
                )
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
                conn.close()
                print(f"mariadb ready ({u.hostname}:{u.port})", flush=True)
                return
            except Exception as e:
                print(f"waiting for mariadb… ({i+1}/60) {e}", flush=True)
                await asyncio.sleep(2)
    sys.exit(1)
asyncio.run(main())
PY
}

wait_for_mongodb() {
  python - <<'PY'
import asyncio, os, sys
dsn = os.environ.get("RECQL_MONGODB_DSN") or "mongodb://mongodb:27017/recql?directConnection=true"
if os.environ.get("RECQL_BACKEND") == "mongodb":
    dsn = os.environ.get("RECQL_DATABASE") or dsn
async def main():
    from recql_mongodb.db import create_client
    for i in range(60):
        try:
            client, db = await create_client(dsn)
            await db.command("ping")
            client.close()
            print(f"mongodb ready ({dsn})", flush=True)
            return
        except Exception as e:
            print(f"waiting for mongodb… ({i+1}/60) {e}", flush=True)
            await asyncio.sleep(2)
    sys.exit(1)
asyncio.run(main())
PY
}

wait_for_mssql() {
  python - <<'PY'
import asyncio, os, sys
dsn = os.environ.get("RECQL_MSSQL_DSN") or "mssql://sa:RecqlTest1234!@mssql:1433/recql"
if os.environ.get("RECQL_BACKEND") == "mssql":
    dsn = os.environ.get("RECQL_DATABASE") or dsn
async def main():
    from recql_mssql.db import create_pool
    for i in range(60):
        try:
            pool = await create_pool(dsn, min_size=1, max_size=1)
            conn = await pool.acquire()
            cursor = conn.cursor()
            cursor.execute("SELECT 1")
            cursor.close()
            await pool.release(conn)
            await pool.close()
            print(f"mssql ready ({dsn.split('@')[-1]})", flush=True)
            return
        except Exception as e:
            print(f"waiting for mssql… ({i+1}/60) {e}", flush=True)
            await asyncio.sleep(2)
    sys.exit(1)
asyncio.run(main())
PY
}

export RECQL_DATABASE="$DATABASE"
export RECQL_ENGINE="$ENGINE"
export RECQL_ENCODE="$ENCODE"
export RECQL_DIMS="$DIMS"

if [[ "$BACKEND" == "postgres" ]]; then
  wait_for_postgres
elif [[ "$BACKEND" == "oracle" ]]; then
  wait_for_oracle
elif [[ "$BACKEND" == "mariadb" ]]; then
  wait_for_mariadb
elif [[ "$BACKEND" == "mongodb" ]]; then
  wait_for_mongodb
elif [[ "$BACKEND" == "mssql" ]]; then
  wait_for_mssql
elif [[ "$BACKEND" == "federated" ]]; then
  wait_for_postgres
  wait_for_oracle
  wait_for_mariadb
fi

# Check if DB is already seeded
seed_one_backend() {
  local b="$1"
  local dsn="$2"
  local already_seeded=0
  if python -m examples.generator.check_seeded --backend "$b" --database "$dsn" --dims "$DIMS" >/dev/null 2>&1; then
    already_seeded=1
  fi
  if [[ "$SEED" == "force" || ( "$already_seeded" == "0" && "$SEED" != "0" && "$SEED" != "false" && "$SEED" != "no" ) ]]; then
    echo "seeding $b (encode=$ENCODE_BACKEND, dims=$DIMS) …"
    python -m examples.generator.run \
      --backend "$b" \
      --database "$dsn" \
      --encode-backend "$ENCODE_BACKEND" \
      --dims "$DIMS"
  else
    echo "database $b is already seeded (${DIMS}-d) — skipping seed"
  fi
}

if [[ "$BACKEND" == "federated" ]]; then
  seed_one_backend postgres "postgres://recql:recql@postgres:5432/recql"
  seed_one_backend oracle "oracle://recql:RecqlPass1@oracle:1521/FREEPDB1"
  seed_one_backend mariadb "mariadb://recql:recql@mariadb:3306/recql"
else
  seed_one_backend "$BACKEND" "$DATABASE"
fi

CLI_MOD="recql_cli"
if ! python -c "import recql_cli" >/dev/null 2>&1; then
  if python -c "import recql.cli" >/dev/null 2>&1; then
    CLI_MOD="recql.cli"
  fi
fi

# If no args or --menu, launch menu UI
if [[ "$#" -eq 0 || "${1:-}" == "--menu" ]]; then
  exec python -m examples.menu
fi

# If direct shell command given, execute directly
if [[ "${1:-}" == "python" || "${1:-}" == "bash" || "${1:-}" == "sh" || "${1:-}" == "pytest" || "${1:-}" == "recql" ]]; then
  exec "$@"
fi

if [[ "$BACKEND" == "federated" ]]; then
  exec python -m "$CLI_MOD" \
    --engine "$ENGINE" \
    "$@"
fi

exec python -m "$CLI_MOD" \
  --database "$DATABASE" \
  "${CLI_BACKEND_ARGS[@]}" \
  --engine "$ENGINE" \
  "$@"
