"""Load a logical ``DemoCatalog`` into MariaDB 11.7+."""

from __future__ import annotations

import json
from typing import Any

from examples.generator.catalog import DemoCatalog, DemoEmbedding
from examples.generator.mariadb.schema import apply_demo_schema
from recql_mariadb.db import vec_literal


async def load_catalog(
    conn,
    catalog: DemoCatalog,
    *,
    engine_config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    await apply_demo_schema(
        conn, text_dims=catalog.text_dims, als_dims=catalog.als_dims
    )

    async with conn.cursor() as cur:
        for it in catalog.items:
            await cur.execute(
                """
                INSERT INTO items
                  (item_id, attrs, created_at, derived_popular_rank, search_text)
                VALUES (%s, %s, COALESCE(%s, CURRENT_TIMESTAMP(6)), %s, %s)
                ON DUPLICATE KEY UPDATE
                  attrs = VALUES(attrs),
                  created_at = VALUES(created_at),
                  derived_popular_rank = VALUES(derived_popular_rank),
                  search_text = VALUES(search_text)
                """,
                (
                    it.item_id,
                    json.dumps(it.attrs),
                    it.created_at,
                    it.popular_rank,
                    it.search_text,
                ),
            )

        for u in catalog.users:
            await cur.execute(
                """
                INSERT INTO users (user_id, attrs)
                VALUES (%s, %s)
                ON DUPLICATE KEY UPDATE attrs = VALUES(attrs)
                """,
                (u.user_id, json.dumps(u.attrs or {})),
            )

        for inter in catalog.interactions:
            await cur.execute(
                """
                INSERT INTO interactions (user_id, item_id, label, created_at)
                VALUES (%s, %s, %s, COALESCE(%s, CURRENT_TIMESTAMP(6)))
                ON DUPLICATE KEY UPDATE
                  label = VALUES(label),
                  created_at = VALUES(created_at)
                """,
                (inter.user_id, inter.item_id, inter.label, inter.created_at),
            )

        for emb in catalog.embeddings:
            await _insert_embedding(cur, emb)

        for model in catalog.models:
            await cur.execute(
                """
                INSERT INTO models (name, policy_type, version, feature_spec, `blob`)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                  `blob` = VALUES(`blob`),
                  feature_spec = VALUES(feature_spec),
                  policy_type = VALUES(policy_type)
                """,
                (
                    model.name,
                    model.policy_type,
                    model.version,
                    json.dumps(model.feature_spec),
                    model.blob,
                ),
            )
        await conn.commit()

    return {
        "backend": "mariadb",
        "items": len(catalog.items),
        "users": len(catalog.users),
        "interactions": len(catalog.interactions),
        "embeddings": len(catalog.embeddings),
        "models": len(catalog.models),
        "text_dims": catalog.text_dims,
        "als_dims": catalog.als_dims,
        **catalog.meta,
    }


async def _insert_embedding(cur, emb: DemoEmbedding) -> None:
    literal = vec_literal(emb.vector)
    if emb.embedding_name == "als" and emb.entity_type == "user":
        await cur.execute(
            """
            INSERT INTO als_user_embeddings (user_id, embedding)
            VALUES (%s, VEC_FromText(%s))
            ON DUPLICATE KEY UPDATE embedding = VALUES(embedding)
            """,
            (emb.entity_id, literal),
        )
        return
    if emb.embedding_name == "als" and emb.entity_type == "item":
        await cur.execute(
            """
            INSERT INTO als_item_embeddings (item_id, embedding)
            VALUES (%s, VEC_FromText(%s))
            ON DUPLICATE KEY UPDATE embedding = VALUES(embedding)
            """,
            (emb.entity_id, literal),
        )
        return
    await cur.execute(
        """
        INSERT INTO text_embeddings (embedding_name, entity_id, embedding)
        VALUES (%s, %s, VEC_FromText(%s))
        ON DUPLICATE KEY UPDATE embedding = VALUES(embedding)
        """,
        (emb.embedding_name, emb.entity_id, literal),
    )
