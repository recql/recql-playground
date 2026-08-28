"""Demo Postgres DDL for examples + CI — application-specific, not library.

Online RecQL plugins bind only to whatever engine YAML declares.
"""

from __future__ import annotations

SCHEMA_SQL = """
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS items (
  item_id TEXT PRIMARY KEY,
  attrs JSONB NOT NULL DEFAULT '{}',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  _derived_popular_rank DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS users (
  user_id TEXT PRIMARY KEY,
  attrs JSONB NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS interactions (
  user_id TEXT NOT NULL,
  item_id TEXT NOT NULL,
  label DOUBLE PRECISION,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (user_id, item_id, created_at)
);

CREATE TABLE IF NOT EXISTS text_embeddings (
  embedding_name TEXT NOT NULL,
  entity_id TEXT NOT NULL,
  embedding vector NOT NULL,
  PRIMARY KEY (embedding_name, entity_id)
);

CREATE TABLE IF NOT EXISTS als_user_embeddings (
  user_id TEXT PRIMARY KEY,
  embedding vector NOT NULL
);

CREATE TABLE IF NOT EXISTS als_item_embeddings (
  item_id TEXT PRIMARY KEY,
  embedding vector NOT NULL
);

CREATE TABLE IF NOT EXISTS models (
  name TEXT NOT NULL,
  policy_type TEXT,
  version TEXT NOT NULL DEFAULT 'v1',
  feature_spec JSONB,
  blob BYTEA,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (name, version)
);

CREATE INDEX IF NOT EXISTS items_popular_idx ON items (_derived_popular_rank);
CREATE INDEX IF NOT EXISTS items_created_idx ON items (created_at DESC);
"""

TEXTSEARCH_PG_TEXTSEARCH = """
DO $$
BEGIN
  CREATE EXTENSION IF NOT EXISTS pg_textsearch;
EXCEPTION WHEN OTHERS THEN
  RAISE NOTICE 'pg_textsearch not available; using tsvector fallback';
END $$;
"""

TEXTSEARCH_FALLBACK = """
ALTER TABLE items ADD COLUMN IF NOT EXISTS search_tsv tsvector;
CREATE INDEX IF NOT EXISTS items_search_tsv_idx ON items USING GIN (search_tsv);
"""


async def apply_demo_schema(conn, *, enable_pg_textsearch: bool | None = True) -> None:
    await conn.execute(SCHEMA_SQL)
    if enable_pg_textsearch is not False:
        await conn.execute(TEXTSEARCH_PG_TEXTSEARCH)
    await conn.execute(TEXTSEARCH_FALLBACK)
    from recql.catalog.bindings import PaginationKvBinding
    from recql_postgres.schema import ensure_operational_tables

    await ensure_operational_tables(conn, kv=PaginationKvBinding())
