#!/usr/bin/env bash
# RecQL container entrypoint: wait for DB → optional seed → CLI.
set -euo pipefail

BACKEND="${RECQL_BACKEND:-postgres}"
SEED="${RECQL_SEED:-1}"
ENCODE="${RECQL_ENCODE:-st}"

case "$ENCODE" in
  st|sentence_transformers|hf|minilm)
    ENCODE_BACKEND=sentence_transformers
    # MiniLM is always 384 — ignore stale RECQL_DIMS=8 from old .env files
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
  *)
    echo "unknown RECQL_BACKEND=$BACKEND (use postgres|oracle|mariadb)" >&2
    exit 2
    ;;
esac

# Seed + query must share the same engine (dims + encode_backend).
# Ignore a pinned RECQL_ENGINE that disagrees with RECQL_ENCODE (compose footgun).
if [[ -n "${RECQL_ENGINE:-}" && "${RECQL_ENGINE}" != "$ENGINE" ]]; then
  echo "note: ignoring RECQL_ENGINE=${RECQL_ENGINE} (using ${ENGINE} for encode=${ENCODE})" >&2
fi

wait_for_postgres() {
  python - <<'PY'
import asyncio, os, sys
dsn = os.environ.get("RECQL_DATABASE") or os.environ.get("RECQL_PG_DSN") or "postgres://recql:recql@postgres:5432/recql"
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
dsn = os.environ.get("RECQL_DATABASE") or os.environ.get("RECQL_ORACLE_DSN") or "oracle://recql:RecqlPass1@oracle:1521/FREEPDB1"
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
dsn = os.environ.get("RECQL_DATABASE") or os.environ.get("RECQL_MARIADB_DSN") or "mariadb://recql:recql@mariadb:3306/recql"
async def main():
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
else
  wait_for_mariadb
fi

# When SEED=0, still re-seed if DB embedding dims disagree with engine (8 vs 384).
NEED_SEED=0
if [[ "$SEED" != "1" && "$SEED" != "true" && "$SEED" != "yes" ]]; then
  if [[ "$BACKEND" == "postgres" ]]; then
    if ! python -m examples.generator.check_dims; then
      echo "auto re-seeding to fix embedding dimension mismatch …" >&2
      NEED_SEED=1
    fi
  fi
fi

if [[ "$SEED" == "1" || "$SEED" == "true" || "$SEED" == "yes" || "$NEED_SEED" == "1" ]]; then
  echo "seeding $BACKEND encode=$ENCODE_BACKEND dims=$DIMS engine=$ENGINE …"
  python -m examples.generator.run \
    --backend "$BACKEND" \
    --database "$DATABASE" \
    --encode-backend "$ENCODE_BACKEND" \
    --dims "$DIMS"
fi

echo "cli encode=$ENCODE_BACKEND dims=$DIMS engine=$ENGINE"

# No args → REPL; otherwise forward to recql.cli
if [[ "$#" -eq 0 ]]; then
  exec python -m recql.cli \
    --database "$DATABASE" \
    "${CLI_BACKEND_ARGS[@]}" \
    --engine "$ENGINE" \
    --repl
fi

exec python -m recql.cli \
  --database "$DATABASE" \
  "${CLI_BACKEND_ARGS[@]}" \
  --engine "$ENGINE" \
  "$@"
