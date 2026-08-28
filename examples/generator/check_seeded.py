"""Check whether a database backend is already seeded and has matching dims."""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from typing import Any


async def is_postgres_seeded(dsn: str, dims: int) -> bool:
    import asyncpg
    from examples.generator.check_dims import pg_column_dims

    try:
        conn = await asyncpg.connect(dsn, timeout=3)
    except Exception:
        return False
    try:
        row = await conn.fetchrow(
            "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name = 'items') AS ex"
        )
        if not row or not row["ex"]:
            return False
        count = await conn.fetchval("SELECT COUNT(*) FROM items")
        if not count or count == 0:
            return False
        # Verify embedding dims
        actual_dims = await pg_column_dims(dsn, "text_embeddings")
        if actual_dims is not None and actual_dims != int(dims):
            return False
        return True
    except Exception:
        return False
    finally:
        await conn.close()


async def is_mssql_seeded(dsn: str, dims: int) -> bool:
    from recql_mssql.db import create_pool, fetch_one

    try:
        pool = await create_pool(dsn, min_size=1, max_size=1)
    except Exception:
        return False
    try:
        row = await fetch_one(
            pool,
            "SELECT COUNT(*) AS cnt FROM items",
        )
        if row and int(row.get("cnt") or 0) > 0:
            return True
        return False
    except Exception:
        return False
    finally:
        await pool.close()


async def is_mongodb_seeded(dsn: str, dims: int) -> bool:
    from recql_mongodb.db import create_client

    try:
        client, db = await create_client(dsn)
    except Exception:
        return False
    try:
        names = await db.list_collection_names()
        if "items" not in names:
            return False
        count = await db.items.count_documents({})
        return count > 0
    except Exception:
        return False
    finally:
        client.close()


async def is_mariadb_seeded(dsn: str, dims: int) -> bool:
    from recql_mariadb.db import create_pool

    try:
        pool = await create_pool(dsn, minsize=1, maxsize=1)
    except Exception:
        return False
    try:
        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute(
                    "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema = DATABASE() AND table_name = 'items'"
                )
                r = await cur.fetchone()
                if not r or r[0] == 0:
                    return False
                await cur.execute("SELECT COUNT(*) FROM items")
                cnt = await cur.fetchone()
                return bool(cnt and cnt[0] > 0)
    except Exception:
        return False
    finally:
        pool.close()
        await pool.wait_closed()


async def is_oracle_seeded(dsn: str, dims: int) -> bool:
    import oracledb
    from recql_oracle.connect import parse_oracle_dsn

    user, password, easy = parse_oracle_dsn(dsn)
    try:
        conn = await oracledb.connect_async(user=user, password=password, dsn=easy)
    except Exception:
        return False
    try:
        async with conn.cursor() as cur:
            await cur.execute(
                "SELECT COUNT(*) FROM user_tables WHERE table_name = 'ITEMS'"
            )
            r = await cur.fetchone()
            if not r or r[0] == 0:
                return False
            await cur.execute("SELECT COUNT(*) FROM items")
            cnt = await cur.fetchone()
            return bool(cnt and cnt[0] > 0)
    except Exception:
        return False
    finally:
        await conn.close()


async def is_seeded(backend: str, dsn: str, dims: int = 384) -> bool:
    bk = backend.lower()
    if bk in ("postgres", "pg", "postgresql"):
        return await is_postgres_seeded(dsn, dims)
    if bk in ("mssql", "sqlserver", "tsql"):
        return await is_mssql_seeded(dsn, dims)
    if bk in ("mongodb", "mongo"):
        return await is_mongodb_seeded(dsn, dims)
    if bk in ("mariadb", "mysql", "maria"):
        return await is_mariadb_seeded(dsn, dims)
    if bk in ("oracle", "ora", "23ai", "26ai"):
        return await is_oracle_seeded(dsn, dims)
    return False


async def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description="Check if a database is seeded")
    p.add_argument("--backend", default=os.environ.get("RECQL_BACKEND", "postgres"))
    p.add_argument("--database", default=os.environ.get("RECQL_DATABASE", ""))
    p.add_argument("--dims", type=int, default=int(os.environ.get("RECQL_DIMS", "384")))
    args = p.parse_args(argv)

    if not args.database:
        return 1

    seeded = await is_seeded(args.backend, args.database, args.dims)
    if seeded:
        print("seeded")
        return 0
    else:
        print("unseeded")
        return 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
