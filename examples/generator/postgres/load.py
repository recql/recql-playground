"""Load a logical ``DemoCatalog`` into Postgres (DDL + upserts + indexes)."""

from __future__ import annotations

import json
from typing import Any

from examples.generator.catalog import DemoCatalog, DemoEmbedding
from examples.generator.postgres.schema import apply_demo_schema
from recql.artifacts import ArtifactPin, config_hash, register_artifact
from recql.encode import vector_literal


async def load_catalog(
    conn,
    catalog: DemoCatalog,
    *,
    enable_pg_textsearch: bool | None = True,
    engine_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply Postgres demo schema and insert everything from ``catalog``."""
    await apply_demo_schema(conn, enable_pg_textsearch=enable_pg_textsearch)
    await _ensure_embedding_tables(conn, text_dims=catalog.text_dims, als_dims=catalog.als_dims)

    for it in catalog.items:
        await conn.execute(
            """
            INSERT INTO items (item_id, attrs, created_at, _derived_popular_rank, search_tsv)
            VALUES ($1, $2::jsonb, $3, $4, to_tsvector('english', $5))
            ON CONFLICT (item_id) DO UPDATE SET
              attrs = EXCLUDED.attrs,
              created_at = EXCLUDED.created_at,
              _derived_popular_rank = EXCLUDED._derived_popular_rank,
              search_tsv = EXCLUDED.search_tsv
            """,
            it.item_id,
            json.dumps(it.attrs),
            it.created_at,
            it.popular_rank,
            it.search_text,
        )

    for u in catalog.users:
        await conn.execute(
            """
            INSERT INTO users (user_id, attrs) VALUES ($1, $2::jsonb)
            ON CONFLICT (user_id) DO NOTHING
            """,
            u.user_id,
            json.dumps(u.attrs or {}),
        )

    for inter in catalog.interactions:
        await conn.execute(
            """
            INSERT INTO interactions (user_id, item_id, label, created_at)
            VALUES ($1, $2, $3, COALESCE($4, now()))
            ON CONFLICT DO NOTHING
            """,
            inter.user_id,
            inter.item_id,
            inter.label,
            inter.created_at,
        )

    for emb in catalog.embeddings:
        await _insert_embedding(conn, emb)

    for model in catalog.models:
        await conn.execute(
            """
            INSERT INTO models (name, policy_type, version, feature_spec, blob)
            VALUES ($1, $2, $3, $4::jsonb, $5)
            ON CONFLICT (name, version) DO UPDATE SET
              blob = EXCLUDED.blob,
              feature_spec = EXCLUDED.feature_spec,
              policy_type = EXCLUDED.policy_type
            """,
            model.name,
            model.policy_type,
            model.version,
            json.dumps(model.feature_spec),
            model.blob,
        )
        chash = config_hash(
            engine_config or {"name": model.name, "version": model.version, "backend": "postgres"}
        )
        await register_artifact(
            conn,
            ArtifactPin(
                kind="model",
                name=model.name,
                version=model.version,
                dims=int((model.feature_spec or {}).get("dims") or catalog.text_dims),
                config_hash=chash,
                feature_spec=model.feature_spec,
            ),
        )

    if any(e.embedding_name == "als" for e in catalog.embeddings):
        chash = config_hash(
            engine_config or {"embedding_name": "als", "dims": catalog.als_dims}
        )
        await register_artifact(
            conn,
            ArtifactPin(
                kind="embedding",
                name="als",
                version="v1",
                dims=catalog.als_dims,
                config_hash=chash,
                feature_spec={"dims": catalog.als_dims},
            ),
        )

    await _ensure_hnsw_indexes(conn)
    return {
        "backend": "postgres",
        "items": len(catalog.items),
        "users": len(catalog.users),
        "interactions": len(catalog.interactions),
        "embeddings": len(catalog.embeddings),
        "models": len(catalog.models),
        "text_dims": catalog.text_dims,
        "als_dims": catalog.als_dims,
        **catalog.meta,
    }


async def _insert_embedding(conn, emb: DemoEmbedding) -> None:
    literal = vector_literal(emb.vector)
    if emb.embedding_name == "als" and emb.entity_type == "user":
        await conn.execute(
            """
            INSERT INTO als_user_embeddings (user_id, embedding)
            VALUES ($1, $2::vector)
            ON CONFLICT (user_id) DO UPDATE SET embedding = EXCLUDED.embedding
            """,
            emb.entity_id,
            literal,
        )
        return
    if emb.embedding_name == "als" and emb.entity_type == "item":
        await conn.execute(
            """
            INSERT INTO als_item_embeddings (item_id, embedding)
            VALUES ($1, $2::vector)
            ON CONFLICT (item_id) DO UPDATE SET embedding = EXCLUDED.embedding
            """,
            emb.entity_id,
            literal,
        )
        return
    await conn.execute(
        """
        INSERT INTO text_embeddings (embedding_name, entity_id, embedding)
        VALUES ($1, $2, $3::vector)
        ON CONFLICT (embedding_name, entity_id)
        DO UPDATE SET embedding = EXCLUDED.embedding
        """,
        emb.embedding_name,
        emb.entity_id,
        literal,
    )


async def _ensure_embedding_tables(conn, *, text_dims: int, als_dims: int) -> None:
    """Pin vector column widths and clear rows before re-insert."""
    await conn.execute("DROP INDEX IF EXISTS text_embeddings_hnsw")
    await conn.execute("DROP INDEX IF EXISTS als_user_embeddings_hnsw")
    await conn.execute("DROP INDEX IF EXISTS als_item_embeddings_hnsw")
    await conn.execute("DROP INDEX IF EXISTS als_embeddings_hnsw")
    await conn.execute("DROP TABLE IF EXISTS embeddings CASCADE")
    await conn.execute("DROP TABLE IF EXISTS als_embeddings CASCADE")
    await conn.execute("TRUNCATE TABLE text_embeddings")
    await conn.execute("TRUNCATE TABLE als_user_embeddings")
    await conn.execute("TRUNCATE TABLE als_item_embeddings")
    await conn.execute(
        f"""
        ALTER TABLE text_embeddings
          ALTER COLUMN embedding TYPE vector({int(text_dims)})
        """
    )
    await conn.execute(
        f"""
        ALTER TABLE als_user_embeddings
          ALTER COLUMN embedding TYPE vector({int(als_dims)})
        """
    )
    await conn.execute(
        f"""
        ALTER TABLE als_item_embeddings
          ALTER COLUMN embedding TYPE vector({int(als_dims)})
        """
    )


async def _ensure_hnsw_indexes(conn) -> None:
    for table in ("text_embeddings", "als_user_embeddings", "als_item_embeddings"):
        await conn.execute(
            f"""
            DO $$
            BEGIN
              CREATE INDEX IF NOT EXISTS {table}_hnsw
                ON {table} USING hnsw (embedding vector_cosine_ops);
            EXCEPTION WHEN OTHERS THEN
              RAISE NOTICE 'hnsw index skipped for {table}: %', SQLERRM;
            END $$;
            """
        )
