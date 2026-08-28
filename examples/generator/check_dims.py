"""Check Postgres embedding column dims vs engine YAML (demo stack)."""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from typing import Any

from recql.catalog import load_engine_catalog


async def pg_column_dims(dsn: str, table: str, column: str = "embedding") -> int | None:
    import asyncpg

    conn = await asyncpg.connect(dsn, timeout=5)
    try:
        row = await conn.fetchrow(
            """
            SELECT a.atttypmod AS typmod
            FROM pg_attribute a
            JOIN pg_class c ON c.oid = a.attrelid
            JOIN pg_namespace n ON n.oid = c.relnamespace
            WHERE c.relname = $1
              AND a.attname = $2
              AND NOT a.attisdropped
            LIMIT 1
            """,
            table,
            column,
        )
        if row is None or row["typmod"] is None or int(row["typmod"]) < 1:
            return None
        return int(row["typmod"])
    finally:
        await conn.close()


def _table_from_store_cfg(cfg: dict[str, Any]) -> str | None:
    if not isinstance(cfg, dict):
        return None
    if cfg.get("table"):
        return str(cfg["table"])
    if cfg.get("name"):
        return str(cfg["name"])
    return None


def _tables_for_store_group(store_cfg: dict[str, Any], dims: int) -> dict[str, int]:
    out: dict[str, int] = {}
    if "user" in store_cfg or "item" in store_cfg:
        for plane in ("user", "item"):
            block = store_cfg.get(plane)
            if isinstance(block, dict):
                table = _table_from_store_cfg(block)
                if table:
                    out[table] = int(dims)
        return out
    table = _table_from_store_cfg(store_cfg)
    if table:
        out[table] = int(dims)
    return out


def _expected_dims() -> dict[str, int]:
    engine = os.environ.get("RECQL_ENGINE")
    if not engine or not Path(engine).exists():
        encode = os.environ.get("RECQL_ENCODE", "st")
        st = encode in ("st", "sentence_transformers", "hf", "minilm")
        text = int(os.environ.get("RECQL_DIMS", "384" if st else "8"))
        als = 32 if text > 32 else text
        return {
            "text_embeddings": text,
            "als_user_embeddings": als,
            "als_item_embeddings": als,
        }

    raw = load_engine_catalog(Path(engine)).raw
    index = raw.get("index") or {}
    stores = index.get("embedding_stores") or {}
    specs = index.get("embeddings") or []
    out: dict[str, int] = {}
    for spec in specs:
        if not isinstance(spec, dict):
            continue
        name = spec.get("name")
        dims = spec.get("dims")
        if name is None or dims is None:
            continue
        store_key = spec.get("store") or name
        store_cfg = stores.get(store_key) or stores.get(name) or {}
        inline = spec.get("stores")
        if isinstance(inline, dict):
            store_cfg = inline
        out.update(_tables_for_store_group(store_cfg, int(dims)))
    if out:
        return out
    text = int(os.environ.get("RECQL_DIMS", "384"))
    als = min(32, text) if text > 32 else text
    return {
        "text_embeddings": text,
        "als_user_embeddings": als,
        "als_item_embeddings": als,
    }


async def main() -> int:
    dsn = os.environ.get("RECQL_DATABASE") or os.environ.get(
        "RECQL_PG_DSN", "postgres://recql:recql@postgres:5432/recql"
    )
    expected = _expected_dims()
    mismatches: list[str] = []
    for table, want in expected.items():
        try:
            actual = await pg_column_dims(dsn, table)
        except Exception as exc:
            print(f"could not read {table}.embedding dims: {exc}", file=sys.stderr)
            return 0
        if actual is None:
            mismatches.append(f"{table} missing or unbounded (expected {want}-d)")
        elif actual != want:
            mismatches.append(f"{table} is {actual}-d but engine expects {want}-d")
    if mismatches:
        for msg in mismatches:
            print(msg, file=sys.stderr)
        print(
            f"(RECQL_ENCODE={os.environ.get('RECQL_ENCODE', '?')})",
            file=sys.stderr,
        )
        print("re-seed once: make seed   or   make repl   (omit SEED=0)", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
